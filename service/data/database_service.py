from dotenv import load_dotenv
from pymongo import MongoClient
import os

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")
MONGO_AVAILABLE = False
MONGO_ERROR = None


class _FallbackCursor(list):
    def limit(self, *_args, **_kwargs):
        return self

    def skip(self, *_args, **_kwargs):
        return self

    def sort(self, *_args, **_kwargs):
        return self


class _FallbackCollection:
    def __init__(self, name):
        self.name = name

    def find_one(self, *args, **kwargs):
        return None

    def find(self, *args, **kwargs):
        return _FallbackCursor()

    def insert_one(self, document):
        return type("InsertResult", (), {"inserted_id": None})()

    def insert_many(self, documents):
        return type("InsertManyResult", (), {"inserted_ids": []})()

    def update_one(self, *args, **kwargs):
        return type("UpdateResult", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})()

    def update_many(self, *args, **kwargs):
        return type("UpdateResult", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})()

    def delete_one(self, *args, **kwargs):
        return type("DeleteResult", (), {"deleted_count": 0})()

    def delete_many(self, *args, **kwargs):
        return type("DeleteResult", (), {"deleted_count": 0})()

    def aggregate(self, *args, **kwargs):
        return _FallbackCursor()

    def count_documents(self, *args, **kwargs):
        return 0

    def distinct(self, *args, **kwargs):
        return []


class _FallbackDatabase:
    def __getitem__(self, name):
        return _FallbackCollection(name)


if not MONGO_URL:
    MONGO_ERROR = "MONGO_URL is not set in .env"
    client = None
    db = _FallbackDatabase()
else:
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=2000)
        client.admin.command("ping")
        db = client["food_ai_agent_db"]
        MONGO_AVAILABLE = True
    except Exception as exc:
        MONGO_ERROR = str(exc)
        client = None
        db = _FallbackDatabase()

# -------------------------
# CONVERSATION MEMORY
# -------------------------
conversation_collection = db["conversations"]
chat_session_collection = db["chat_sessions"]

# -------------------------
# USER PROFILE
# -------------------------
user_profile_collection = db["user_profiles"]

# -------------------------
# RESTAURANTS
# -------------------------
restaurant_collection = db["restaurants"]

# -------------------------
# MENUS
# -------------------------
menu_collection = db["menus"]

# -------------------------
# OPTIONS MEMORY (A/B/C)
# -------------------------
option_collection = db["options"]

# -------------------------
# USER STATE
# -------------------------
state_collection = db["states"]

# -------------------------
# CART + ORDERS
# -------------------------
orders_collection = db["orders"]

# -------------------------
# RESTAURANT REQUESTS
# -------------------------
restaurant_requests_collection = db["restaurant_requests"]

session_collection = db["sessions"]
