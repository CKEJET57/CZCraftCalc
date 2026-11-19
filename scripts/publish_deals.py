"""Почасовая агрегация сделок и публикация в отдельную Git-ветку.

Исходные database/history/deals/*.jsonl открываются только на чтение.
Локальная очередь: database/publish/queue/deals/YYYY/MM/DD/HH.jsonl.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from config import DB_DIR, LOCAL_TIMEZONE

HISTORY_DEALS_DIR = DB_DIR / "history" / "deals"
PUBLISH_DIR = DB_DIR / "publish"
QUEUE_DIR = PUBLISH_DIR / "queue" / "deals"
STATE_FILE = PUBLISH_DIR / "state.json"
SCHEMA_VERSION = 1
KEEP_DAYS = 30
API_ROOT = "https://api.github.com"


class PublishError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {message}", flush=True)


def parse_deal_time(value) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            stamp = float(value)
            if stamp > 10_000_000_000:
                stamp /= 1000
            return datetime.fromtimestamp(stamp, tz=timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def load_and_group(now: datetime, tz: ZoneInfo) -> dict:
    """Читает сделки за последние 30 дней; исходные файлы не меняет."""
    grouped = defaultdict(lambda: defaultdict(list))
    cutoff = now.astimezone(timezone.utc) - timedelta(days=KEEP_DAYS)
    current_hour = now.astimezone(tz).replace(minute=0, second=0, microsecond=0)
    if not HISTORY_DEALS_DIR.exists():
        raise PublishError(f"Каталог исходных сделок не найден: {HISTORY_DEALS_DIR}")

    for source in sorted(HISTORY_DEALS_DIR.glob("*.jsonl")):
        item_id = source.stem
        if not item_id or any(c in item_id for c in "/\\"):
            log(f"Пропуск файла с некорректным itemId: {source.name}")
            continue
        with source.open("r", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                try:
                    deal = json.loads(line)
                except json.JSONDecodeError:
                    log(f"Некорректный JSON пропущен: {source.name}:{line_no}")
                    continue
                dt = parse_deal_time(deal.get("time"))
                if dt is None or dt < cutoff:
                    continue
                local_dt = dt.astimezone(tz)
                hour = local_dt.replace(minute=0, second=0, microsecond=0)
                if hour >= current_hour:
                    continue
                try:
                    amount = int(deal.get("amount", 0))
                    price = float(deal.get("price", 0))
                    unit = float(deal.get("unit", price / amount if amount else 0))
                except (TypeError, ValueError, ZeroDivisionError):
                    continue
                if amount <= 0 or price <= 0 or unit <= 0:
                    continue
                grouped[hour][item_id].append({"amount": amount, "price": price, "unit": unit})
    return grouped


def aggregate_hour(hour: datetime, items: dict) -> str:
    rows = []
    for item_id in sorted(items):
        deals = items[item_id]
        total_amount = sum(d["amount"] for d in deals)
        turnover = sum(d["price"] for d in deals)
        units = [d["unit"] for d in deals]
        rows.append({
            "schema_version": SCHEMA_VERSION,
            "item": item_id,
            "hour": hour.isoformat(),
            "deals": len(deals),
            "amount": total_amount,
            "turnover": round(turnover, 6),
            "min_unit": round(min(units), 6),
            "max_unit": round(max(units), 6),
            "avg_unit": round(turnover / total_amount, 6),
            "median_unit": round(statistics.median(units), 6),
        })
    return "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"schema_version": SCHEMA_VERSION, "published": {}}
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if state.get("schema_version") != SCHEMA_VERSION:
            raise PublishError("Несовместимая версия database/publish/state.json")
        state.setdefault("published", {})
        return state
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"Не удалось прочитать состояние публикации: {exc}") from exc


def save_state(state: dict) -> None:
    atomic_write(STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2) + "\n")


class GitHubPublisher:
    def __init__(self, token: str, repository: str, branch: str, base_branch: str):
        self.repository = repository
        self.branch = branch
        self.base_branch = base_branch
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self.root = f"{API_ROOT}/repos/{repository}"

    def request(self, method: str, path: str, **kwargs):
        response = self.session.request(method, self.root + path, timeout=45, **kwargs)
        if response.status_code >= 400:
            raise PublishError(
                f"GitHub API {method} {path}: HTTP {response.status_code}: {response.text[:1000]}"
            )
        return response.json() if response.content else {}

    def ensure_branch(self) -> str:
        ref_path = f"/git/ref/heads/{self.branch}"
        response = self.session.get(self.root + ref_path, timeout=30)
        if response.status_code == 200:
            return response.json()["object"]["sha"]
        if response.status_code != 404:
            raise PublishError(
                f"Не удалось проверить ветку {self.branch}: HTTP {response.status_code} {response.text[:500]}"
            )
        base = self.request("GET", f"/git/ref/heads/{self.base_branch}")
        created = self.request("POST", "/git/refs", json={
            "ref": f"refs/heads/{self.branch}", "sha": base["object"]["sha"],
        })
        log(f"Создана ветка {self.branch} от {self.base_branch}")
        return created["object"]["sha"]

    def publish_files(self, files: dict[str, str]) -> int:
        if not files:
            return 0
        parent_sha = self.ensure_branch()
        commit = self.request("GET", f"/git/commits/{parent_sha}")
        base_tree = commit["tree"]["sha"]
        remote_tree = self.request("GET", f"/git/trees/{base_tree}", params={"recursive": "1"})
        if remote_tree.get("truncated"):
            raise PublishError("Git-дерево ветки слишком большое для безопасной проверки")
        existing = {
            entry["path"]: entry["sha"]
            for entry in remote_tree.get("tree", [])
            if entry.get("type") == "blob"
        }
        changes = []
        for path, content in sorted(files.items()):
            blob = self.request("POST", "/git/blobs", json={
                "content": content, "encoding": "utf-8",
            })
            if existing.get(path) == blob["sha"]:
                continue
            changes.append({
                "path": path, "mode": "100644", "type": "blob", "sha": blob["sha"],
            })
        if not changes:
            log("GitHub уже содержит актуальные агрегаты; новый коммит не нужен")
            return 0
        tree = self.request("POST", "/git/trees", json={
            "base_tree": base_tree, "tree": changes,
        })
        new_commit = self.request("POST", "/git/commits", json={
            "message": "Опубликовать почасовые агрегаты сделок",
            "tree": tree["sha"], "parents": [parent_sha],
        })
        self.request("PATCH", f"/git/refs/heads/{self.branch}", json={
            "sha": new_commit["sha"], "force": False,
        })
        log(f"Опубликовано файлов: {len(changes)}, commit={new_commit['sha'][:12]}")
        return len(changes)


def queue_path(hour: datetime) -> Path:
    return QUEUE_DIR / hour.strftime("%Y/%m/%d/%H.jsonl")


def remote_path(hour: datetime) -> str:
    return "deals/" + hour.strftime("%Y/%m/%d/%H.jsonl")


def cleanup_queue(state: dict, now: datetime) -> int:
    """Удаляет только опубликованные локальные агрегаты старше 30 дней."""
    cutoff = now - timedelta(days=KEEP_DAYS)
    removed = 0
    if not QUEUE_DIR.exists():
        return 0
    tz = ZoneInfo(LOCAL_TIMEZONE)
    for path in QUEUE_DIR.rglob("*.jsonl"):
        try:
            relative = path.relative_to(QUEUE_DIR).as_posix()
            hour = datetime.strptime(relative, "%Y/%m/%d/%H.jsonl").replace(tzinfo=tz)
            if hour < cutoff and hour.isoformat() in state["published"]:
                path.unlink()
                removed += 1
        except (ValueError, OSError):
            continue
    return removed


def run(dry_run: bool = False) -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "CKEJET57/CZCraftCalc").strip()
    branch = os.environ.get("GITHUB_DATA_BRANCH", "market-data").strip()
    base_branch = os.environ.get("GITHUB_BASE_BRANCH", "feature/monorepo").strip()
    if not token:
        raise PublishError("Не задан GITHUB_TOKEN в окружении/.env")
    if not repository or not branch or not base_branch:
        raise PublishError("Некорректные GITHUB_REPOSITORY / GITHUB_DATA_BRANCH / GITHUB_BASE_BRANCH")

    tz = ZoneInfo(LOCAL_TIMEZONE)
    now = datetime.now(tz)
    state = load_state()
    grouped = load_and_group(now, tz)
    files: dict[str, str] = {}
    pending_state = dict(state.get("published", {}))

    for hour, items in sorted(grouped.items()):
        content = aggregate_hour(hour, items)
        key = hour.isoformat()
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if not dry_run:
            atomic_write(queue_path(hour), content)
        if pending_state.get(key) != digest:
            files[remote_path(hour)] = content
            pending_state[key] = digest

    # Повторяем отправку очереди, если предыдущий push не удался, а исходная
    # сделка уже вышла за пределы локального 30-дневного окна.
    if not dry_run and QUEUE_DIR.exists():
        for queued in sorted(QUEUE_DIR.rglob("*.jsonl")):
            try:
                relative = queued.relative_to(QUEUE_DIR).as_posix()
                hour = datetime.strptime(relative, "%Y/%m/%d/%H.jsonl").replace(tzinfo=tz)
            except ValueError:
                continue
            key = hour.isoformat()
            if key in pending_state:
                continue
            content = queued.read_text(encoding="utf-8")
            if content.strip():
                files[remote_path(hour)] = content
                pending_state[key] = hashlib.sha256(content.encode("utf-8")).hexdigest()

    log(f"Завершённых часовых интервалов в локальной истории: {len(grouped)}")
    if dry_run:
        log(f"dry-run: файлов на публикацию: {len(files)}; исходные deals не изменялись")
        return 0

    publisher = GitHubPublisher(token, repository, branch, base_branch)
    changed = publisher.publish_files(files)
    state["published"] = pending_state
    state["last_success_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    removed = cleanup_queue(state, now)
    log(f"Готово: обновлено файлов={changed}, удалено локальных агрегатов старше 30 дней={removed}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Почасовая агрегация и публикация сделок в Git")
    parser.add_argument("--dry-run", action="store_true", help="Подготовить агрегаты без отправки в GitHub")
    args = parser.parse_args()
    try:
        return run(dry_run=args.dry_run)
    except (PublishError, requests.RequestException, OSError) as exc:
        log(f"ОШИБКА публикации: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
