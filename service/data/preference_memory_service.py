from datetime import datetime

from service.ai.food_chat_service import expand_allergy_terms
from service.data.database_service import user_preference_collection, user_profile_collection
from service.data.mongo_utils import serialize_mongo


DEFAULT_PREFERENCES = {
    "preferred_cuisines": [],
    "disliked_cuisines": [],
    "preferred_spice_levels": [],
    "dietary_preferences": [],
    "allergies": [],
    "allergy_terms": [],
    "disliked_ingredients": [],
    "favorite_restaurants": [],
    "favorite_food_items": [],
    "typical_min_budget": None,
    "typical_max_budget": None,
    "special_preferences": [],
}


def _normalize_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _unique(values):
    seen = set()
    result = []
    for value in _normalize_list(values):
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _legacy_preferences(user_id):
    profile = user_profile_collection.find_one({"user_id": user_id}) or {}
    prefs = profile.get("preferences", {}) or {}
    return {
        "preferred_cuisines": prefs.get("preferred_cuisines", []),
        "preferred_spice_levels": [prefs.get("spicy_level")] if prefs.get("spicy_level") else [],
        "dietary_preferences": _unique(
            (prefs.get("dietary_restrictions", []) or [])
            + ([prefs.get("dietary_style")] if prefs.get("dietary_style") else [])
        ),
        "allergies": prefs.get("allergies", []),
        "allergy_terms": expand_allergy_terms(prefs.get("allergies", [])),
        "disliked_ingredients": prefs.get("disliked_foods", []),
        "favorite_restaurants": prefs.get("favorite_restaurants", []),
        "favorite_food_items": prefs.get("favorite_foods", []),
        "special_preferences": prefs.get("special_preferences", []),
    }


def get_user_preferences(user_id):
    existing = user_preference_collection.find_one({"user_id": user_id})
    if existing:
        return serialize_mongo(existing)

    now = datetime.utcnow()
    legacy = _legacy_preferences(user_id)
    document = {
        "user_id": user_id,
        **DEFAULT_PREFERENCES,
        **{key: value for key, value in legacy.items() if value not in (None, [], "")},
        "created_at": now,
        "updated_at": now,
    }
    user_preference_collection.insert_one(document)
    return serialize_mongo(document)


def update_user_preferences(user_id, updates):
    updates = updates or {}
    get_user_preferences(user_id)

    add_to_set = {}
    set_values = {}

    list_fields = {
        "preferred_cuisines",
        "disliked_cuisines",
        "preferred_spice_levels",
        "dietary_preferences",
        "allergies",
        "allergy_terms",
        "disliked_ingredients",
        "favorite_restaurants",
        "favorite_food_items",
        "special_preferences",
    }
    scalar_fields = {"typical_min_budget", "typical_max_budget"}

    if updates.get("allergies"):
        updates["allergy_terms"] = _unique(
            _normalize_list(updates.get("allergy_terms"))
            + expand_allergy_terms(updates.get("allergies"))
        )

    for field in list_fields:
        values = _normalize_list(updates.get(field))
        if values:
            add_to_set[field] = {"$each": values}

    for field in scalar_fields:
        if updates.get(field) is not None:
            set_values[field] = updates.get(field)

    if updates.get("remove_allergies"):
        current = get_user_preferences(user_id)
        remove_keys = {item.lower() for item in _normalize_list(updates.get("remove_allergies"))}
        remaining_allergies = [
            item
            for item in _normalize_list(current.get("allergies", []))
            if item.lower() not in remove_keys
        ]
        remaining_terms = expand_allergy_terms(remaining_allergies)
        user_preference_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "allergies": remaining_allergies,
                    "allergy_terms": remaining_terms,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

    update_doc = {"$set": {"updated_at": datetime.utcnow()}}
    if set_values:
        update_doc["$set"].update(set_values)
    if add_to_set:
        update_doc["$addToSet"] = add_to_set

    user_preference_collection.update_one({"user_id": user_id}, update_doc, upsert=True)
    return get_user_preferences(user_id)
