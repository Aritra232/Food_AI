import math
import re
from datetime import datetime
from uuid import uuid4

from bson import ObjectId

from service.data.database_service import (
    food_item_collection,
    food_item_extra_collection,
    food_item_variation_collection,
    menu_collection,
    restaurant_collection,
)
from service.data.mongo_utils import serialize_mongo


ALLERGY_ALIASES = {
    "peanut": [
        "peanut",
        "groundnut",
        "nut",
        "almond",
        "cashew",
        "walnut",
        "hazelnut",
        "pistachio",
        "pecan",
    ],
    "nut": [
        "nut",
        "peanut",
        "groundnut",
        "almond",
        "cashew",
        "walnut",
        "hazelnut",
        "pistachio",
        "pecan",
    ],
    "dairy": ["dairy", "milk", "cream", "cheese", "butter", "yogurt"],
    "shellfish": ["shellfish", "shrimp", "prawn", "crab", "lobster"],
    "gluten": ["gluten", "wheat", "flour", "bread"],
    "egg": ["egg", "eggs"],
    "soy": ["soy", "soya"],
}

MEAT_TERMS = {
    "beef",
    "chicken",
    "mutton",
    "lamb",
    "pork",
    "bacon",
    "fish",
    "shrimp",
    "prawn",
    "crab",
    "lobster",
    "meat",
}


def _object_id(value):
    try:
        return ObjectId(value)
    except Exception:
        return None


def _as_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _lower_terms(value):
    return [item.lower() for item in _as_list(value)]


def _text_blob(item):
    fields = [
        item.get("name"),
        item.get("food_name"),
        item.get("description"),
        item.get("category"),
        " ".join(_as_list(item.get("tags"))),
        " ".join(_as_list(item.get("ingredients"))),
    ]
    return " ".join(str(field or "") for field in fields).lower()


def _price(item):
    value = item.get("base_price", item.get("price", 0))
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _available(item):
    if "is_available" in item:
        return bool(item.get("is_available"))
    if "available" in item:
        return bool(item.get("available"))
    return True


def _distance_km(lat1, lng1, lat2, lng2):
    earth_radius = 6371
    dlat = math.radians(float(lat2) - float(lat1))
    dlng = math.radians(float(lng2) - float(lng1))
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(float(lat1)))
        * math.cos(math.radians(float(lat2)))
        * math.sin(dlng / 2) ** 2
    )
    return earth_radius * 2 * math.asin(math.sqrt(a))


def generate_food_item_id():
    return f"food_{uuid4().hex[:10]}"


def normalize_food_item(item, source="food_items"):
    if not item:
        return None
    item = serialize_mongo(dict(item))
    food_item_id = str(item.get("_id") or item.get("food_item_id") or item.get("menu_id"))
    name = item.get("name") or item.get("food_name") or "Unnamed food"
    price = _price(item)
    normalized = {
        "_id": str(item.get("_id", "")),
        "food_item_id": str(item.get("food_item_id") or item.get("menu_id") or food_item_id),
        "menu_id": str(item.get("food_item_id") or item.get("menu_id") or food_item_id),
        "legacy_menu_id": item.get("menu_id"),
        "restaurant_id": str(item.get("restaurant_id", "")),
        "name": name,
        "food_name": name,
        "description": item.get("description", ""),
        "image": item.get("image") or item.get("profile_image") or "",
        "category": item.get("category", ""),
        "base_price": price,
        "price": price,
        "spice_level": item.get("spice_level") or item.get("spicy_level") or "",
        "spicy_level": item.get("spice_level") or item.get("spicy_level") or "",
        "tags": _as_list(item.get("tags")),
        "ingredients": _as_list(item.get("ingredients")),
        "is_available": _available(item),
        "available": _available(item),
        "source": source,
    }
    return normalized


def normalize_restaurant(restaurant):
    if not restaurant:
        return None
    restaurant = serialize_mongo(dict(restaurant))
    location = restaurant.get("location") or {}
    mongo_id = str(restaurant.get("_id", ""))
    legacy_restaurant_id = str(restaurant.get("restaurant_id") or "").strip()
    return {
        "_id": mongo_id,
        "restaurant_id": mongo_id,
        "legacy_restaurant_id": legacy_restaurant_id,
        "name": restaurant.get("name") or restaurant.get("restaurant_name") or "Unknown restaurant",
        "category": restaurant.get("category", ""),
        "description": restaurant.get("description", ""),
        "address": restaurant.get("address", ""),
        "latitude": restaurant.get("latitude") or restaurant.get("lat") or location.get("lat"),
        "longitude": restaurant.get("longitude") or restaurant.get("lng") or location.get("lng"),
        "delivery_fee": float(restaurant.get("delivery_fee", 0) or 0),
        "is_active": restaurant.get("is_active", True),
        "opening_time": restaurant.get("opening_time", ""),
        "closing_time": restaurant.get("closing_time", ""),
    }


def _restaurant_map():
    restaurants = {}
    for doc in restaurant_collection.find({}):
        restaurant = normalize_restaurant(doc)
        restaurants[restaurant["_id"]] = restaurant
        if restaurant.get("legacy_restaurant_id"):
            restaurants[restaurant["legacy_restaurant_id"]] = restaurant
    return restaurants


def _catalog_documents(include_legacy=False):
    for doc in food_item_collection.find({}):
        yield normalize_food_item(doc, "food_items")
    if include_legacy:
        for doc in menu_collection.find({}):
            yield normalize_food_item(doc, "menus")


def allergy_conflicts(item, allergies, expanded_terms=None):
    blob = _text_blob(item)
    conflicts = []
    for allergy in _lower_terms(allergies):
        terms = ALLERGY_ALIASES.get(allergy, [allergy])
        for term in terms:
            if term and re.search(rf"\b{re.escape(term)}s?\b", blob):
                conflicts.append(allergy)
                break
    for term in _lower_terms(expanded_terms):
        if term and re.search(rf"\b{re.escape(term)}s?\b", blob):
            conflicts.append(term)
    return sorted(set(conflicts))


def dietary_conflicts(item, dietary_preferences):
    blob = _text_blob(item)
    tags = set(_lower_terms(item.get("tags")))
    conflicts = []

    for dietary in _lower_terms(dietary_preferences):
        if dietary in {"vegetarian", "vegan"}:
            if any(re.search(rf"\b{term}\b", blob) for term in MEAT_TERMS):
                conflicts.append(dietary)
        if dietary == "vegan" and any(term in blob for term in ALLERGY_ALIASES["dairy"] + ["egg"]):
            conflicts.append(dietary)
        if dietary in {"halal", "gluten-free", "dairy-free", "keto"} and dietary not in tags:
            if dietary == "dairy-free" and allergy_conflicts(item, ["dairy"]):
                conflicts.append(dietary)
            elif dietary == "gluten-free" and allergy_conflicts(item, ["gluten"]):
                conflicts.append(dietary)

    return sorted(set(conflicts))


def is_safe_for_user(item, preferences):
    preferences = preferences or {}
    allergy_hits = allergy_conflicts(
        item,
        preferences.get("allergies", []),
        preferences.get("allergy_terms", []),
    )
    dietary_hits = dietary_conflicts(item, preferences.get("dietary_preferences", []))
    disliked_hits = allergy_conflicts(item, preferences.get("disliked_ingredients", []))
    return not allergy_hits and not dietary_hits and not disliked_hits


def _matches_filters(item, filters):
    filters = filters or {}
    blob = _text_blob(item)
    query = str(filters.get("query") or "").strip().lower()
    category = str(filters.get("category") or "").strip().lower()
    spice_level = str(filters.get("spice_level") or "").strip().lower()
    restaurant_id = str(filters.get("restaurant_id") or "").strip()

    if query:
        query_terms = [term for term in re.findall(r"[a-z0-9]+", query) if len(term) > 1]
        if query_terms and not any(term in blob for term in query_terms):
            return False
    if category and category not in blob:
        return False
    if spice_level and spice_level not in str(item.get("spice_level", "")).lower() and spice_level not in blob:
        return False
    if restaurant_id and item.get("restaurant_id") != restaurant_id:
        return False

    min_price = filters.get("min_price")
    max_price = filters.get("max_price")
    if min_price is not None and _price(item) < float(min_price):
        return False
    if max_price is not None and _price(item) > float(max_price):
        return False

    return True


def _score_item(item, filters, preferences, interactions=None):
    score = 0
    blob = _text_blob(item)
    query_terms = re.findall(r"[a-z0-9]+", str((filters or {}).get("query") or "").lower())
    score += sum(4 for term in query_terms if term in blob)
    score += sum(3 for cuisine in _lower_terms((preferences or {}).get("preferred_cuisines")) if cuisine in blob)
    score += sum(3 for spice in _lower_terms((preferences or {}).get("preferred_spice_levels")) if spice in blob)
    if item.get("restaurant_id") in _as_list((preferences or {}).get("favorite_restaurants")):
        score += 4
    if item.get("food_item_id") in _as_list((preferences or {}).get("favorite_food_items")):
        score += 5
    if interactions:
        score += interactions.get(item.get("food_item_id"), 0)
    return score


def find_food_items(filters=None, preferences=None, lat=None, lng=None, limit=8, max_distance_km=10, include_legacy=False):
    restaurants = _restaurant_map()
    results = []

    for item in _catalog_documents(include_legacy=include_legacy):
        if not item or not item.get("is_available"):
            continue
        if not _matches_filters(item, filters):
            continue
        if not is_safe_for_user(item, preferences):
            continue

        restaurant = restaurants.get(item.get("restaurant_id"))
        if restaurant:
            if restaurant.get("is_active") is False:
                continue
            item["restaurant"] = restaurant
            item["restaurant_name"] = restaurant.get("name")
            item["delivery_fee"] = restaurant.get("delivery_fee", 0)
            if lat is not None and lng is not None and restaurant.get("latitude") and restaurant.get("longitude"):
                try:
                    distance = _distance_km(lat, lng, restaurant["latitude"], restaurant["longitude"])
                    if distance > max_distance_km:
                        continue
                    item["distance_km"] = round(distance, 2)
                except Exception:
                    pass

        item["score"] = _score_item(item, filters, preferences)
        results.append(item)

    results.sort(key=lambda item: (-item.get("score", 0), item.get("distance_km", 9999), item.get("base_price", 0)))
    return results[: int(limit or 8)]


def get_food_item(food_item_id):
    if not food_item_id:
        return None

    candidates = [
        {"food_item_id": food_item_id},
        {"menu_id": food_item_id},
    ]
    object_id = _object_id(food_item_id)
    if object_id:
        candidates.append({"_id": object_id})

    for query in candidates:
        doc = food_item_collection.find_one(query)
        if doc:
            return normalize_food_item(doc, "food_items")
        doc = menu_collection.find_one(query)
        if doc:
            return normalize_food_item(doc, "menus")
    return None


def get_food_item_options(food_item_id):
    ids = [food_item_id]
    item = get_food_item(food_item_id)
    if item:
        ids.extend([item.get("_id"), item.get("food_item_id"), item.get("legacy_menu_id")])
    ids = [str(value) for value in ids if value]

    variations = list(food_item_variation_collection.find({"food_item_id": {"$in": ids}, "is_available": {"$ne": False}}))
    extras = list(food_item_extra_collection.find({"food_item_id": {"$in": ids}, "is_available": {"$ne": False}}))
    return {
        "variations": serialize_mongo(variations),
        "extras": serialize_mongo(extras),
    }


def create_food_item(data):
    payload = dict(data or {})
    if not payload.get("food_item_id"):
        payload["food_item_id"] = generate_food_item_id()
    payload.setdefault("is_available", True)
    payload["created_at"] = payload.get("created_at") or datetime.utcnow()
    payload["updated_at"] = datetime.utcnow()
    result = food_item_collection.insert_one(payload)
    created = food_item_collection.find_one({"_id": result.inserted_id})
    return normalize_food_item(created)
