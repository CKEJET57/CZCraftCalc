"""
storage/downloader.py — загрузка базы данных с GitHub.

Стратегия:
  - Файлы (listing.json и т.д.) — через raw.githubusercontent.com.
  - Папки (icons/, items/) — через `git sparse-checkout` (без API rate limit).
  - Опционально: если задан GITHUB_TOKEN, можно использовать Trees API.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests

from config import DB_DIR, DB_BASE_URL, DB_REQUIRED_FILES, DB_REQUIRED_DIRS


# ─── GitHub репозиторий ───
REPO_OWNER = "EXBO-Studio"
REPO_NAME = "stalzone-database"
REPO_BRANCH = "main"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}"


def _download_file(url: str, dest: Path) -> None:
    """Скачивает один файл (создаёт родительские папки)."""
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)


def _download_folder_via_git(folder_name: str) -> None:
    """
    Скачивает папку `ru/{folder_name}/` из репозитория с помощью
    `git sparse-checkout`. Не использует API GitHub.
    """
    print(f"[DB] Скачивание папки {folder_name}/ через git sparse-checkout...")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            # 1. Инициализация репозитория
            subprocess.run(
                ["git", "init"],
                cwd=tmp_path, check=True, capture_output=True,
            )
            # 2. Добавление remote
            subprocess.run(
                ["git", "remote", "add", "origin", REPO_URL],
                cwd=tmp_path, check=True, capture_output=True,
            )
            # 3. Включаем sparse-checkout и указываем нужную папку
            subprocess.run(
                ["git", "config", "core.sparseCheckout", "true"],
                cwd=tmp_path, check=True, capture_output=True,
            )
            sparse_file = tmp_path / ".git" / "info" / "sparse-checkout"
            sparse_file.parent.mkdir(parents=True, exist_ok=True)
            sparse_file.write_text(f"ru/{folder_name}/\n")

            # 4. Загружаем только нужную ветку (без истории)
            subprocess.run(
                ["git", "pull", "--depth=1", "origin", REPO_BRANCH],
                cwd=tmp_path, check=True, capture_output=True,
            )

            # 5. Копируем скачанную папку в database/
            src = tmp_path / "ru" / folder_name
            if not src.exists():
                raise FileNotFoundError(
                    f"Папка ru/{folder_name}/ не найдена в репозитории"
                )
            dest = DB_DIR / folder_name
            if dest.exists():
                shutil.rmtree(dest)   # перезаписываем, если что-то осталось
            shutil.copytree(src, dest)
            print(f"[DB] ✓ {folder_name}/ готова")

        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"git ошибка при скачивании {folder_name}/: {e.stderr.decode()[:300]}"
            )


def ensure_database_files() -> None:
    """
    Проверяет наличие файлов и папок. Скачивает недостающее.

    - Файл отсутствует → скачиваем через raw.githubusercontent.com.
    - Папка отсутствует → скачиваем целиком через git sparse-checkout.
    - Папка уже есть → содержимое НЕ проверяется.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)

    missing_files = [f for f in DB_REQUIRED_FILES if not (DB_DIR / f).exists()]
    missing_dirs = [d for d in DB_REQUIRED_DIRS if not (DB_DIR / d).exists()]

    if not missing_files and not missing_dirs:
        return

    print(f"[DB] Первый запуск: нужно скачать "
          f"{len(missing_files)} файлов и {len(missing_dirs)} папок")

    # 1. Файлы
    for f in missing_files:
        url = f"{DB_BASE_URL}/{f}"
        print(f"[DB] Скачивание {f}...")
        try:
            _download_file(url, DB_DIR / f)
            size_kb = (DB_DIR / f).stat().st_size / 1024
            print(f"[DB] ✓ {f} ({size_kb:.1f} КБ)")
        except Exception as e:
            raise SystemExit(f"Не удалось скачать {f}: {e}")

    # 2. Папки (через git sparse-checkout)
    for d in missing_dirs:
        try:
            _download_folder_via_git(d)
        except Exception as e:
            raise SystemExit(
                f"Не удалось скачать папку {d}/: {e}\n"
                f"Попробуйте удалить database/{d}/ и перезапустить."
            )

    print("[DB] ✓ База данных готова к работе")