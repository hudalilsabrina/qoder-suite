import os
import sys
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Config file resolution
CONFIG_FILE = BASE_DIR / "config.toml"

_config = {}

def _load_config():
    global _config
    if _config:
        return _config
    if CONFIG_FILE.exists():
        try:
            if sys.version_info >= (3, 11):
                import tomllib
                with open(CONFIG_FILE, "rb") as f:
                    _config = tomllib.load(f)
            else:
                import tomli
                with open(CONFIG_FILE, "rb") as f:
                    _config = tomli.load(f)
        except Exception as e:
            print(f"[!] Warning: failed to parse config.toml: {e}")
            _config = {}
    return _config

def get_cfg(section, key, default=None):
    cfg = _load_config()
    return cfg.get(section, {}).get(key, default)

# Global settings
TEMPIK_BASE = os.getenv("TEMPIK_BASE", get_cfg("api", "tempmail_base", "https://mail.xentranetwork.me/api"))
QODER_BASE = "https://qoder.com"
# Referral code -> signup DENGAN referral dapat "free Pro trial + 300 Credits".
# Tanpa referral = free tier biasa (trial rate ~0.8%).
REFERRAL_CODE = os.getenv("QODER_REFERRAL_CODE", get_cfg("qoder", "referral_code", ""))
NINE_ROUTER_URL = os.getenv("NINEROUTER_URL", get_cfg("router", "url", "http://localhost:20127/dashboard/providers/qoder"))
NINE_ROUTER_PASS = os.getenv("NINEROUTER_PASS", get_cfg("router", "password", "Arinata123#"))

HEADLESS = os.getenv("QODER_HEADLESS", str(get_cfg("general", "headless", True))).lower() in ("true", "1", "yes")
CAPTCHA_ATTEMPTS = int(os.getenv("CAPTCHA_ATTEMPTS", get_cfg("general", "captcha_attempts", 5)))
CALLBACK_WAIT_MS = int(os.getenv("CALLBACK_WAIT_MS", get_cfg("general", "callback_wait_ms", 5000)))

# Notifikasi (opsional): set QODER_WEBHOOK_URL untuk menerima ringkasan batch.
# Kompatibel dengan Slack/Discord/Telegram gateway atau endpoint HTTP apa pun.
WEBHOOK_URL = os.getenv("QODER_WEBHOOK_URL", get_cfg("notify", "webhook_url", ""))

# Logging JSON terstruktur (opsional): set QODER_JSON_LOG=1 atau [logging] json = true
JSON_LOG = os.getenv("QODER_JSON_LOG", str(get_cfg("logging", "json", False))).lower() in ("true", "1", "yes")

DATA_DIR = BASE_DIR / "data"
LOG_FILE = DATA_DIR / "app.log"
ACCOUNTS_JSONL = DATA_DIR / "accounts.jsonl"
OUTPUT_TXT = BASE_DIR / "accounts.txt"
INPUT_LOGIN_TXT = BASE_DIR / "input_login.txt"
