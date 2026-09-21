import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
PORT = int(os.getenv("PORT", "10000"))

DB_PATH = os.getenv("DB_PATH", "data/prices.db")

DEFAULT_STORES = {
    "SystemService": 25,
    "Darian": 5,
    "Hilok": 25,
    "Ezviz": 20,  # Diler narxidan -20% (asosiy); display'da -15% ham alohida ko'rsatiladi
    "MUS": 0,     # Skidka yo'q, faqat filial/hamkor/price ko'rsatiladi
    "KSS": 25,
}

# Special store behavior
EZVIZ_SECONDARY_DISCOUNT = 15  # Ezviz uchun ikkinchi variant

MAX_MODELS_PER_REQUEST = 60
FUZZY_THRESHOLD = 75

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi (.env yoki Render env vars)")
