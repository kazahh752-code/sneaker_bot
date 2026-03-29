import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PORT = int(os.getenv("PORT", 5001))
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "sneakers.db"))

# Яндекс.Маркет партнёрский API (получить на https://partner.market.yandex.ru)
# Если нет токена — оставь пустым, будет работать только WB
YANDEX_MARKET_TOKEN = os.getenv("YANDEX_MARKET_TOKEN", "")
YANDEX_CAMPAIGN_ID = os.getenv("YANDEX_CAMPAIGN_ID", "")

DEFAULT_MAX_PRICE = 4000
CHECK_INTERVAL_HOURS = 2

SIZES = ["44.5", "45", "45.5"]

# Топ-10 беговых брендов
BRANDS = [
    "ASICS", "New Balance", "Nike", "Adidas",
    "Saucony", "Brooks", "Mizuno", "Hoka", "Puma", "Reebok",
]

# Задержка между запросами к WB (сек) — чтобы не получать 429
WB_REQUEST_DELAY = 4

HEADERS_WB = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
}
