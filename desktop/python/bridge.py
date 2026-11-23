"""Одноразовый JSON-lines мост между Tauri и существующим Python Core.

Вход: одна JSON-строка в stdin.
Выход: одна JSON-строка в stdout.
Диагностика и посторонний вывод направляются в stderr.
"""
from __future__ import annotations

import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


def _stats_metadata() -> dict[str, Any]:
    import requests

    stats_file = ROOT / "database" / "stats.json"
    if not stats_file.exists():
        url = (
            "https://raw.githubusercontent.com/"
            "EXBO-Studio/stalzone-database/main/ru/stats.json"
        )
        response = requests.get(url, timeout=(10, 30))
        response.raise_for_status()
        stats_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = stats_file.with_suffix(".json.tmp")
        temporary.write_bytes(response.content)
        temporary.replace(stats_file)

    data = json.loads(stats_file.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return _error("invalid_database", "Файл database/stats.json имеет неверный формат.")
    return {"ok": True, "data": data}


def _search_character(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    region = str(payload.get("region") or "RU").strip().upper()

    if not name:
        return _error("validation", "Укажите ник персонажа.")
    if len(name) > 64:
        return _error("validation", "Ник персонажа слишком длинный.")
    if not re.fullmatch(r"[A-Z]{2,5}", region):
        return _error("validation", "Некорректный код региона.")

    # Импорт выполняется только для операции поиска: чтение локального
    # справочника не требует OAuth-секрета.
    from api.auth import fetch_token
    from api.characters import fetch_character_profile

    token_data = fetch_token()
    profile = fetch_character_profile(token_data["access_token"], region, name)
    if profile is None:
        return _error(
            "not_found",
            f"Персонаж «{name}» не найден в регионе {region}.",
        )
    return {"ok": True, "data": profile}


def _desktop_api(action: str, payload: dict[str, Any]) -> Any:
    """Вызывает общие прикладные операции без запуска HTTP-сервера.

    Перед обращением к справочникам подготавливает локальные файлы database.
    """
    if action == "sync_market_data":
        from services.market_data import sync_market_data
        return sync_market_data()
    if action == "market_data_status":
        from services.market_data import market_data_status
        return market_data_status()

    from storage.downloader import ensure_database_files

    ensure_database_files()

    # Все рыночные операции Desktop принудительно работают офлайн.
    payload = {**payload, "use_local_data": True}

    from services.app_state import get_state
    from services.application import (
        batch_operation, history_operation, recipe_operation,
    )
    from services.market_analysis import analyze_market
    from services.top_items import get_top_items
    from services import catalog

    state = get_state()
    if action == "items":
        return catalog.list_items(state,
            lang=str(payload.get("lang") or "ru"),
            q=payload.get("q"),
            craftable=bool(payload.get("craftable", False)),
        )
    if action == "categories":
        return catalog.list_categories(state,lang=str(payload.get("lang") or "ru"))
    if action == "item_details":
        result = catalog.get_item_details(state,
            str(payload.get("item_id") or ""), lang=str(payload.get("lang") or "ru")
        )
        icon_url = result.get("icon_url")
        if icon_url and icon_url.startswith("/api/static/"):
            import base64
            from config import DB_DIR
            relative = icon_url.removeprefix("/api/static/")
            icon_path = (DB_DIR / relative).resolve()
            if icon_path.is_file() and icon_path.is_relative_to(DB_DIR.resolve()):
                suffix = icon_path.suffix.lower()
                mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix, "application/octet-stream")
                result["icon_url"] = f"data:{mime};base64," + base64.b64encode(icon_path.read_bytes()).decode("ascii")
            else:
                result["icon_url"] = None
        return result
    if action == "item_variants":
        return catalog.get_item_variants(state,
            str(payload.get("item_id") or ""), lang=str(payload.get("lang") or "ru")
        )
    if action == "recipe":
        return recipe_operation(state, payload)
    if action == "batch":
        return batch_operation(state, payload)
    if action == "history":
        result = history_operation(state, payload)
        if result is None:
            raise ValueError(f"Нет истории для {payload.get('item_id')}")
        return result
    if action == "top_items":
        result = get_top_items(state, limit=int(payload.get("limit") or 100))
        # В Tauri нет HTTP backend, поэтому локальные иконки отдаём как data URI.
        import base64
        from config import DB_DIR
        for row in result.get("items", []):
            icon_url = row.get("icon_url")
            if not icon_url or not icon_url.startswith("/api/static/"):
                continue
            relative = icon_url.removeprefix("/api/static/")
            icon_path = (DB_DIR / relative).resolve()
            if not icon_path.is_file() or not icon_path.is_relative_to(DB_DIR.resolve()):
                row["icon_url"] = None
                continue
            suffix = icon_path.suffix.lower()
            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }.get(suffix, "application/octet-stream")
            encoded = base64.b64encode(icon_path.read_bytes()).decode("ascii")
            row["icon_url"] = f"data:{mime};base64,{encoded}"
        return result
    if action == "market_analysis":
        return analyze_market(
            str(payload.get("item_id") or ""), int(payload.get("days") or 7)
        )
    if action == "health":
        return catalog.health()
    raise ValueError(f"Неизвестная desktop-команда: {action}")


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action == "stats_metadata":
        return _stats_metadata()
    if action == "search_character":
        return _search_character(payload)
    if action in {
        "health", "items", "categories", "item_details", "item_variants",
        "recipe", "batch", "history", "market_analysis", "top_items",
        "sync_market_data", "market_data_status",
    }:
        try:
            action_payload = payload.get("payload")
            if not isinstance(action_payload, dict):
                action_payload = payload
            return {"ok": True, "data": _desktop_api(str(action), action_payload)}
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            if detail is not None:
                message = str(detail)
            else:
                message = f"{type(exc).__name__}: {exc}"
            return _error("backend_error", message)
    return _error("unknown_action", "Неизвестная команда desktop bridge.")


def main() -> int:
    # Tauri передаёт JSON в UTF-8. Читаем байты напрямую, чтобы системная
    # кодировка консоли Windows не искажала кириллицу во входном запросе.
    raw_line = sys.stdin.buffer.readline()
    try:
        line = raw_line.decode("utf-8")
    except UnicodeDecodeError as exc:
        result = _error("invalid_encoding", f"Входной запрос должен быть в UTF-8: {exc}")
        output = json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n"
        sys.stdout.buffer.write(output.encode("ascii"))
        sys.stdout.flush()
        return 0
    if not line:
        result = _error("empty_request", "Не получена команда.")
        output = json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n"
        sys.stdout.buffer.write(output.encode("ascii"))
        return 0

    try:
        payload = json.loads(line)
        if not isinstance(payload, dict):
            result = _error("invalid_request", "Ожидался JSON-объект.")
        else:
            # Любой print из библиотек не должен ломать IPC-протокол.
            with redirect_stdout(sys.stderr):
                result = dispatch(payload)
    except SystemExit as exc:
        message = str(exc) or "Не удалось инициализировать Python backend."
        result = _error("configuration", message)
    except Exception as exc:
        result = _error("backend_error", f"{type(exc).__name__}: {exc}")

    # ASCII JSON не зависит от кодовой страницы Windows; Rust восстановит Unicode.
    output = json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n"
    sys.stdout.buffer.write(output.encode("ascii"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
