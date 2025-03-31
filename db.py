# stalcraft_bot/db.py

from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME

client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]

users_collection = db["users"]
tracked_items = db["tracked_items"]
processed_lots = db["processed_lots"]
