# stalcraft_bot/config.py

import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = "stalcraft_bot"

# Путь к JSON с товарами
ITEMS_PATH = os.getenv("ITEMS_PATH", "./items")

# Сталкрафт API
API_BASE_URL = "https://eapi.stalcraft.net"
AUTH_URL = "https://exbo.net/oauth/token"
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
