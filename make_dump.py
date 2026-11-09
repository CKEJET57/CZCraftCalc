#!/usr/bin/env python3
"""
Собирает текстовые файлы проекта в один project_dump.txt.
Запуск из корня: python make_dump.py

Для файлов из папки database/ записывается не весь JSON,
а только первые DATABASE_SAMPLE_ITEMS элементов каждого списка —
чтобы дамп оставался компактным.
"""
from pathlib import Path
import json
import sys

OUTPUT_NAME = "project_dump.txt"

# сколько элементов каждого списка из database/ показывать в дампе
DATABASE_SAMPLE_ITEMS = 3

EXTENSIONS = {
    ".py", ".md", ".txt", ".json", ".toml", ".cfg", ".ini",
    ".yml", ".yaml", ".sql", ".html", ".css", ".js", ".ts",
}

# файлы без расширения / dotfiles, которые всё равно нужны
INCLUDE_NAMES = {
    ".env", ".env.example", ".env.local", ".env.dev", ".env.prod",
    ".gitignore", ".dockerignore", ".editorconfig", ".flake8",
    "Dockerfile", "dockerfile",
    "Makefile", "makefile",
    "LICENSE", "LICENSE.txt", "LICENSE.md",
}

EXCLUDE_DIRS = {
    ".venv", "venv", "__pycache__",
    ".git", ".idea", ".vscode",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", "dist", "build",
}

# ВАЖНО: запятая после элемента — это кортеж из одного элемента
EXCLUDE_PATH_PARTS: set[tuple[str, ...]] = {
    ("history",),
}

MAX_FILE_BYTES = 2 * 1024 * 1024


def should_skip_dir(rel_parts: tuple[str, ...]) -> bool:
    if any(part in EXCLUDE_DIRS for part in rel_parts):
        return True
    for seq in EXCLUDE_PATH_PARTS:
        n = len(seq)
        for i in range(len(rel_parts) - n + 1):
            if rel_parts[i:i + n] == seq:
                return True
    return False


def is_database_file(rel_parts: tuple[str, ...]) -> bool:
    """True для файлов внутри database/ (по полному пути rel.parts)."""
    return bool(rel_parts) and rel_parts[0] == "database"


def _truncate_json_lists(data, sample_size: int):
    """
    Обрезает все списки верхнего уровня (или списки-значения в dict)
    до sample_size элементов.

    Возвращает (truncated_data, notes), где notes — список пометок
    вида «<путь>: N из M» для каждого обрезанного списка.
    """
    notes: list[str] = []

    def trunc(lst: list, label: str) -> list:
        if len(lst) > sample_size:
            notes.append(f"{label}: {sample_size} из {len(lst)}")
            return lst[:sample_size]
        return lst

    if isinstance(data, list):
        return trunc(data, "root"), notes
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[key] = trunc(value, key) if isinstance(value, list) else value
        return result, notes
    return data, notes


def format_database_content(text: str) -> str:
    """
    Для файлов из database/: если содержимое — валидный JSON,
    обрезает все списки до DATABASE_SAMPLE_ITEMS и возвращает
    pretty-printed JSON с пометкой о том, что было обрезано.
    Иначе возвращает исходный текст.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text  # не JSON — оставляем как есть

    truncated, notes = _truncate_json_lists(data, DATABASE_SAMPLE_ITEMS)
    if not notes:
        return text  # обрезать нечего (файл уже маленький)

    body = json.dumps(truncated, ensure_ascii=False, indent=2)
    note_line = "  [truncated: " + "; ".join(notes) + "]"
    return note_line + "\n" + body


def collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    try:
        it = root.rglob("*", recurse_symlinks=True)   # Py 3.13+
    except TypeError:
        it = root.rglob("*")                          # Py <= 3.12

    for path in it:
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        rel_parts = rel.parts[:-1]
        if should_skip_dir(rel_parts):
            continue
        if path == root / OUTPUT_NAME:                # не включать сам себя
            continue
        name_ok = path.name in INCLUDE_NAMES
        ext_ok = path.suffix.lower() in EXTENSIONS
        if not (name_ok or ext_ok):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                print(f"[skip: large] {rel}", file=sys.stderr)
                continue
        except OSError:
            continue
        files.append(path)

    files.sort(key=lambda p: p.relative_to(root).as_posix().lower())
    return files


def main() -> None:
    root = Path(__file__).resolve().parent
    out_path = root / OUTPUT_NAME

    files = collect_files(root)
    if not files:
        print("Не найдено подходящих файлов.")
        return

    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        for i, path in enumerate(files, 1):
            rel = path.relative_to(root)
            rel_str = rel.as_posix()
            out.write(f"\n\n=== {rel_str} ===\n\n")
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                content = f"[не удалось прочитать: {e}]"

            # для JSON из database/ — только несколько элементов каждого списка
            if is_database_file(rel.parts) and path.suffix.lower() == ".json":
                content = format_database_content(content)

            out.write(content)
            print(f"[{i}/{len(files)}] {rel_str}")

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\nГотово. Файлов: {len(files)}, размер: {size_mb:.2f} МБ")


if __name__ == "__main__":
    main()