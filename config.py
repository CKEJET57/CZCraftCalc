"""
config.py — единственная точка чтения настроек и секретов.

Приоритет источников:
  1. Переменные окружения (os.environ)
  2. Файл .env (загружается через python-dotenv, если установлен)
  3. Дефолты в этом файле (для не-секретных значений)

Секреты (CLIENT_SECRET) — только через env/.env.
"""

import os
from pathlib import Path

# ─── загрузка .env, если установлен python-dotenv ───
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    # python-dotenv не установлен — читаем только os.environ
    pass


def _require(name: str, hint: str = "") -> str:
    """Возвращает env-переменную или падает с понятным сообщением."""
    value = os.environ.get(name, "").strip()
    if not value:
        msg = f"Переменная окружения {name} не задана."
        if hint:
            msg += f"\n{hint}"
        raise SystemExit(msg)
    return value


# ─── OAuth ───
CLIENT_ID = os.environ.get("STALCRAFT_CLIENT_ID", "694")
CLIENT_SECRET = _require(
    "STALCRAFT_CLIENT_SECRET",
    "Создайте .env на основе .env.example и укажите секрет OAuth-приложения.",
)
OAUTH_URL = os.environ.get("STALCRAFT_OAUTH_URL", "https://exbo.net/oauth/token")

# ─── API ───
EAPI_BASE = os.environ.get("STALCRAFT_EAPI_BASE", "https://eapi.stalcraft.net")

# ─── дефолты ───
DEFAULT_REGION = os.environ.get("STALCRAFT_REGION", "RU")
DEFAULT_LOTS_LIMIT = 200

# ─── пути ───
BASE_DIR = Path(__file__).parent
DB_DIR = BASE_DIR / "database"
LISTING_FILE = DB_DIR / "listing.json"
LISTING_CRAFT_FILE = DB_DIR / "listing_craft.json"
HIDEOUT_FILE = DB_DIR / "hideout_recipes.json"

# ─── официальная база данных ───
DB_BASE_URL = "https://raw.githubusercontent.com/EXBO-Studio/stalzone-database/main/ru"

# Файлы, которые нужно скачать, если их нет
DB_REQUIRED_FILES = [
    "achievements.json",
    "barter_recipes.json",
    "hideout_recipes.json",
    "listing.json",
    "stats.json"
]

# Папки, которые нужно создать, если их нет 
# (внутренности не проверяем, как вы и просили)
DB_REQUIRED_DIRS = [
    "icons",
    "items"
]

# ─── энергия (через покупку "Батарей холодного синтеза") ───
ENERGY_ITEM_ID = "401j"
ENERGY_PER_ITEM = 5000.0

# ─── категории, которые не показывать в топах/списках ───
# furniture    = «Функциональные объекты»
# decorative   = «Декоративная мебель»
EXCLUDED_TOP_CATEGORIES = frozenset({"furniture", "decorative"})

# ─── часовой пояс для отображения дат (IANA name) ───
# Москва: Europe/Moscow, Екатеринбург: Asia/Yekaterinburg,
# Калининград: Europe/Kaliningrad, Новосибирск: Asia/Novosibirsk
LOCAL_TIMEZONE = os.environ.get("STALCRAFT_TIMEZONE", "Europe/Moscow")