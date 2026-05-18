from dotenv import load_dotenv
from pymongo import MongoClient
import os

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")

if not MONGO_URL:
	raise RuntimeError("MONGO_URL is not set in .env")

client = MongoClient(MONGO_URL)

db = client["food_ai_agent_db"]

# -------------------------
# CONVERSATION MEMORY
# -------------------------
conversation_collection = db["conversations"]

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

session_collection = db["sessions"]