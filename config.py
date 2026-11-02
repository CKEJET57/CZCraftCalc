"""
config.py — единственная точка чтения настроек и секретов.
"""

from pathlib import Path

# --- OAuth ---
CLIENT_ID = "694"
CLIENT_SECRET = "J0Ce0earBrRPLJqDEvgmESNdEzircEJDquonsthP"
OAUTH_URL = "https://exbo.net/oauth/token"

# --- API ---
EAPI_BASE = "https://eapi.stalcraft.net"

# --- дефолты ---
DEFAULT_REGION = "RU"
DEFAULT_LOTS_LIMIT = 200

# --- пути ---
BASE_DIR = Path(__file__).parent
DB_DIR = BASE_DIR / "database"
LISTING_FILE = DB_DIR / "listing.json"
EXCLUSIONS_FILE = DB_DIR / "exclusions.json"

# --- энергия (учёт через покупку "Батарей холодного синтеза" на аукционе) ---
ENERGY_ITEM_ID = "401j"
ENERGY_PER_ITEM = 5000.0

# --- категории, которые не показывать в топах/списках ---
# furniture    = «Функциональные объекты»
# decorative   = «Декоративная мебель»
EXCLUDED_TOP_CATEGORIES = frozenset({"furniture", "decorative"})