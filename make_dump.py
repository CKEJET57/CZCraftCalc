#!/usr/bin/env python3
"""
Собирает текстовые файлы проекта в один project_dump.txt.
Запуск из корня: python make_dump.py
"""
from pathlib import Path
import sys

OUTPUT_NAME = "project_dump.txt"

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
    # "env" убран — слишком широко
}

# ВАЖНО: запятая после элемента — это кортеж из одного элемента
EXCLUDE_PATH_PARTS: set[tuple[str, ...]] = {
    ("history",),
    # ("data", "cache"),
}

MAX_FILE_BYTES = 2 * 1024 * 1024


def should_skip_dir(rel_parts: tuple[str, ...]) -> bool:
    if any(part in EXCLUDE_DIRS for part in rel_parts):
        return True
    for seq in EXCLUDE_PATH_PARTS:
        n = len(seq)
        for i in range(len(rel_parts) - n + 1):
            if rel_parts[i:i + n] == seq:   # tuple == tuple — теперь работает
                return True
    return False


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
            rel = path.relative_to(root).as_posix()
            out.write(f"\n\n=== {rel} ===\n\n")
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                content = f"[не удалось прочитать: {e}]"
            out.write(content)
            print(f"[{i}/{len(files)}] {rel}")

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\nГотово. Файлов: {len(files)}, размер: {size_mb:.2f} МБ")


if __name__ == "__main__":
    main()