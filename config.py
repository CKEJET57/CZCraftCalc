"""
config.py — единственная точка чтения настроек и секретов.
В проде значения из .env, здесь — захардкожены для простоты.
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