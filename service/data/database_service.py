import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")

if not MONGO_URL:
    raise RuntimeError("MONGO_URL is not set in .env")

_client = None
_db = None


def get_client():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URL)
    return _client


def get_db():
    global _db
    if _db is None:
        _db = get_client()["food_ai_agent_db"]
    return _db


class LazyDatabase:
    def __getitem__(self, name):
        return LazyCollection(name)

    def __getattr__(self, name):
        return getattr(get_db(), name)


class LazyCollection:
    def __init__(self, name):
        self.name = name

    @property
    def collection(self):
        return get_db()[self.name]

    def __getattr__(self, name):
        return getattr(self.collection, name)


client = None
db = LazyDatabase()

# Source-of-truth restaurant and food catalog.
restaurant_collection = LazyCollection("restaurants")
food_item_collection = LazyCollection("food_items")
food_item_variation_collection = LazyCollection("food_item_variations")
food_item_extra_collection = LazyCollection("food_item_extras")

# Legacy menu collection kept readable during migration.
menu_collection = LazyCollection("menus")

# Long-term user memory and behavior signals.
user_profile_collection = LazyCollection("user_profiles")
user_preference_collection = LazyCollection("user_preferences")
user_food_interaction_collection = LazyCollection("user_food_interactions")

# AI chat memory.
ai_conversation_collection = LazyCollection("ai_conversations")
ai_message_collection = LazyCollection("ai_messages")

# AI order drafting and finalized orders.
ai_cart_session_collection = LazyCollection("ai_cart_sessions")
orders_collection = LazyCollection("orders")

# Existing/legacy collections kept for compatibility with older modules.
conversation_collection = LazyCollection("conversations")
chat_session_collection = LazyCollection("chat_sessions")
option_collection = LazyCollection("options")
state_collection = LazyCollection("states")
restaurant_requests_collection = LazyCollection("restaurant_requests")
session_collection = LazyCollection("sessions")
