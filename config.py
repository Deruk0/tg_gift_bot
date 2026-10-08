"""
Конфигурация бота — загрузка всех переменных окружения из .env
"""
import json
import os

from dotenv import load_dotenv

load_dotenv()

# ── Telegram Bot ───────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.environ["BOT_TOKEN"]

# ── Telethon userbot ───────────────────────────────────────────────────────────
API_ID: int = int(os.environ["API_ID"])
API_HASH: str = os.environ["API_HASH"]
TELETHON_SESSION: str = os.getenv("TELETHON_SESSION", "userbot")
TELETHON_STRING_SESSION: str = os.getenv("TELETHON_STRING_SESSION", "").strip()
TELEGRAM_PROXY: str = os.getenv("TELEGRAM_PROXY", "").strip()

# ── Промокоды: {"КОД": количество_дней} ───────────────────────────────────────
# Значение 0 = навсегда (подписка до 9999-12-31)
DEFAULT_PROMO_CODES: dict[str, int] = {"FOREVER": 0}
_env_promo_codes = os.getenv("PROMO_CODES", "{}").strip()
try:
    PROMO_CODES: dict[str, int] = {**DEFAULT_PROMO_CODES, **json.loads(_env_promo_codes or "{}")}
except json.JSONDecodeError:
    PROMO_CODES = DEFAULT_PROMO_CODES.copy()

# ── Цены подписок в Telegram Stars ────────────────────────────────────────────
SUBSCRIPTION_MONTHLY_STARS: int = 25
SUBSCRIPTION_YEARLY_STARS: int = 200

# ── Бесплатный лимит поисков (навсегда) ───────────────────────────────────────
FREE_SEARCHES_LIMIT: int = 3

# ── Максимум узлов в одном графе (защита от перегрузки) ───────────────────────
MAX_NODES_PER_GRAPH: int = 500

# ── ID администратора бота ────────────────────────────────────────────────────
ADMIN_USER_ID: int = 6908507355

# ── GiftGraph Web (сервис постоянного хостинга графов) ─────────────────────────
GIFTGRAPH_WEB_URL: str = os.getenv("GIFTGRAPH_WEB_URL", "https://giftgraph-miniapp.vercel.app").rstrip("/")
GIFTGRAPH_WEB_API_URL: str = os.getenv("GIFTGRAPH_WEB_API_URL", GIFTGRAPH_WEB_URL).rstrip("/")
GIFTGRAPH_WEB_SECRET: str = os.getenv("GIFTGRAPH_WEB_SECRET", "").strip()
