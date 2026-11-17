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


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action == "stats_metadata":
        return _stats_metadata()
    if action == "search_character":
        return _search_character(payload)
    return _error("unknown_action", "Неизвестная команда desktop bridge.")


def main() -> int:
    # Tauri передаёт JSON в UTF-8. Читаем байты напрямую, чтобы системная
    # кодировка консоли Windows не искажала кириллицу во входном запросе.
    raw_line = sys.stdin.buffer.readline()
    try:
        line = raw_line.decode("utf-8")
    except UnicodeDecodeError as exc:
        result = _error("invalid_encoding", f"Входной запрос должен быть в UTF-8: {exc}")
        output = json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\\n"
        sys.stdout.buffer.write(output.encode("ascii"))
        sys.stdout.flush()
        return 0
    if not line:
        result = _error("empty_request", "Не получена команда.")
        output = json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\\n"
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
    output = json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\\n"
    sys.stdout.buffer.write(output.encode("ascii"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
