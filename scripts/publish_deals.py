"""Почасовая агрегация сделок в исходном формате JSONL и публикация в Git."""
from __future__ import annotations

import argparse
import base64
import fcntl
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
LOCK_FILE = PUBLISH_DIR / "publish.lock"
KEEP_DAYS = 30
SCHEMA_VERSION = 1
API_ROOT = "https://api.github.com"


class PublishError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {message}", flush=True)


def parse_time(value) -> datetime | None:
    try:
        if isinstance(value, (int, float)):
            stamp = float(value)
            if stamp > 10_000_000_000:
                stamp /= 1000
            return datetime.fromtimestamp(stamp, timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


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


def read_source_deals(now: datetime, tz: ZoneInfo) -> dict[str, dict[datetime, list[dict]]]:
    """Читает неизменяемые исходные JSONL; группирует только завершённые часы."""
    if not HISTORY_DEALS_DIR.exists():
        raise PublishError(f"Не найден каталог исходных сделок: {HISTORY_DEALS_DIR}")
    cutoff = now.astimezone(timezone.utc) - timedelta(days=KEEP_DAYS)
    current_hour = now.astimezone(tz).replace(minute=0, second=0, microsecond=0)
    result = defaultdict(lambda: defaultdict(list))
    for path in sorted(HISTORY_DEALS_DIR.glob("*.jsonl")):
        item_id = path.stem
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    deal = json.loads(line)
                    dt = parse_time(deal.get("time"))
                    if dt is None or dt < cutoff:
                        continue
                    hour = dt.astimezone(tz).replace(minute=0, second=0, microsecond=0)
                    if hour >= current_hour:
                        continue
                    amount = int(deal["amount"])
                    price = float(deal["price"])
                    unit = float(deal.get("unit", price / amount))
                    if amount <= 0 or price <= 0 or unit <= 0:
                        continue
                except (json.JSONDecodeError, KeyError, TypeError, ValueError, ZeroDivisionError):
                    log(f"Пропуск некорректной строки {path.name}:{line_number}")
                    continue
                result[item_id][hour].append({"amount": amount, "price": price, "unit": unit})
    return result


def aggregate_item(item_id: str, hourly: dict[datetime, list[dict]], generated_at: str) -> str:
    rows = []
    for hour, deals in sorted(hourly.items()):
        units = [d["unit"] for d in deals]
        amount = sum(d["amount"] for d in deals)
        turnover = sum(d["price"] for d in deals)
        rows.append({
            "item": item_id,
            "hour": hour.isoformat(),
            "deals": len(deals),
            "amount": amount,
            "turnover": round(turnover, 6),
            "min_unit": round(min(units), 6),
            "max_unit": round(max(units), 6),
            "avg_unit": round(turnover / amount, 6),
            "median_unit": round(statistics.median(units), 6),
            "source_records": len(deals),
            "aggregated_at": generated_at,
        })
    return "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows)


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"schema_version": SCHEMA_VERSION, "published": {}}
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if state.get("schema_version") != SCHEMA_VERSION:
            raise PublishError("Несовместимая версия состояния database/publish/state.json")
        state.setdefault("published", {})
        return state
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"Не удалось прочитать состояние публикации: {exc}") from exc


def save_state(state: dict) -> None:
    atomic_write(STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def queue_file(item_id: str) -> Path:
    return QUEUE_DIR / f"{item_id}.jsonl"


def merge_hourly(existing: str, fresh: str) -> str:
    """Обновляет часы по ключу hour, сохраняя все более старые часы."""
    by_hour = {}
    for content in (existing, fresh):
        for line in content.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            by_hour[row["hour"]] = row
    return "".join(
        json.dumps(by_hour[key], ensure_ascii=False, separators=(",", ":")) + "\n"
        for key in sorted(by_hour)
    )


class GitHubPublisher:
    def __init__(self, token: str, repository: str, branch: str, base_branch: str):
        self.repository = repository
        self.branch = branch
        self.base_branch = base_branch
        self.root = f"{API_ROOT}/repos/{repository}"
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def request(self, method: str, path: str, **kwargs):
        response = self.session.request(method, self.root + path, timeout=60, **kwargs)
        if response.status_code >= 400:
            raise PublishError(f"GitHub API {method} {path}: HTTP {response.status_code}: {response.text[:800]}")
        return response.json() if response.content else {}

    def branch_head(self) -> str:
        return self.request("GET", f"/git/ref/heads/{self.branch}")["object"]["sha"]

    def read_item(self, item_id: str) -> str:
        path = f"database/history/deals/{item_id}.jsonl"
        response = self.session.get(
            self.root + f"/contents/{path}",
            params={"ref": self.branch}, timeout=45,
        )
        if response.status_code == 404:
            return ""
        if response.status_code >= 400:
            raise PublishError(f"Не удалось прочитать {path}: HTTP {response.status_code}")
        payload = response.json()
        if payload.get("encoding") != "base64":
            raise PublishError(f"Неожиданный формат GitHub Contents для {path}")
        return base64.b64decode(payload["content"]).decode("utf-8")

    def publish(self, item_contents: dict[str, str]) -> int:
        if not item_contents:
            return 0
        parent_sha = self.branch_head()
        commit = self.request("GET", f"/git/commits/{parent_sha}")
        base_tree = commit["tree"]["sha"]
        changes = []
        for item_id, fresh in sorted(item_contents.items()):
            path = f"database/history/deals/{item_id}.jsonl"
            merged = merge_hourly(self.read_item(item_id), fresh)
            blob = self.request("POST", "/git/blobs", json={
                "content": base64.b64encode(merged.encode("utf-8")).decode("ascii"),
                "encoding": "base64",
            })
            changes.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        tree = self.request("POST", "/git/trees", json={
            "base_tree": base_tree, "tree": changes,
        })
        commit = self.request("POST", "/git/commits", json={
            "message": "Опубликовать почасовые агрегаты сделок",
            "tree": tree["sha"], "parents": [parent_sha],
        })
        # Не force-push: если ветка изменилась параллельно, следующий запуск повторит операцию.
        self.request("PATCH", f"/git/refs/heads/{self.branch}", json={
            "sha": commit["sha"], "force": False,
        })
        log(f"Опубликовано файлов предметов: {len(changes)}; commit={commit['sha'][:12]}")
        return len(changes)


def cleanup_queue(state: dict, now: datetime) -> int:
    """Очищает только опубликованные строки агрегатов старше 30 дней."""
    cutoff = now.astimezone(timezone.utc) - timedelta(days=KEEP_DAYS)
    removed = 0
    if not QUEUE_DIR.exists():
        return removed
    for path in QUEUE_DIR.glob("*.jsonl"):
        try:
            content = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            # Если локальный файл отличается от последней успешно опубликованной
            # версии, не удаляем его: он может содержать ещё не отправленные данные.
            if state.get("published", {}).get(path.stem) != digest:
                continue
            keep = []
            for line in content.splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                hour = parse_time(row.get("hour"))
                if hour is None or hour >= cutoff:
                    keep.append(line)
                else:
                    removed += 1
            if keep:
                atomic_write(path, "\\n".join(keep) + "\\n")
            else:
                path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            continue
    return removed

def run(dry_run: bool = False) -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "CKEJET57/CZCraftCalc").strip()
    branch = os.environ.get("GITHUB_DATA_BRANCH", "market-data").strip()
    base_branch = os.environ.get("GITHUB_BASE_BRANCH", "feature/monorepo").strip()
    if not token and not dry_run:
        raise PublishError("Не задан GITHUB_TOKEN в .env")
    tz = ZoneInfo(LOCAL_TIMEZONE)
    now = datetime.now(tz)
    generated_at = datetime.now(timezone.utc).isoformat()
    source = read_source_deals(now, tz)
    fresh = {item: aggregate_item(item, hours, generated_at) for item, hours in source.items()}
    log(f"Предметов с завершёнными часовыми интервалами: {len(fresh)}")
    if dry_run:
        log("dry-run: GitHub и исходные файлы не изменялись")
        return 0

    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    for item_id, content in fresh.items():
        atomic_write(queue_file(item_id), content)

    publisher = GitHubPublisher(token, repository, branch, base_branch)
    changed = publisher.publish(fresh)

    published = state.setdefault("published", {})
    for item_id, content in fresh.items():
        published[item_id] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    state["last_success_at"] = datetime.now(timezone.utc).isoformat()
    state["last_published_items"] = changed
    save_state(state)
    removed = cleanup_queue(state, now)
    log(f"Готово: файлов={changed}; строк агрегатов в локальной очереди старше 30 дней очищено={removed}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Почасовая агрегация сделок в исходном JSONL-формате")
    parser.add_argument("--dry-run", action="store_true", help="Проверить чтение и агрегацию без GitHub")
    args = parser.parse_args()
    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("Публикация уже выполняется; второй запуск завершён")
            return 0
        try:
            return run(dry_run=args.dry_run)
        except (PublishError, requests.RequestException, OSError) as exc:
            log(f"ОШИБКА публикации: {exc}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
