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


ONBOARDING_BUDGETS = {
    "budget_friendly": (0, 10),
    "budget friendly": (0, 10),
    "low": (0, 10),
    "casual_dining": (10, 25),
    "casual dining": (10, 25),
    "medium": (10, 25),
    "fine_dining": (25, 50),
    "fine dining": (25, 50),
    "high": (25, 50),
    "premium": (50, None),
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


def _normalize_budget_range(value):
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_address(address):
    address = address or {}
    if not isinstance(address, dict):
        return {}
    return {
        "address_type": str(address.get("address_type") or "Home").strip() or "Home",
        "street_address": str(address.get("street_address") or "").strip(),
        "city": str(address.get("city") or "").strip(),
        "zip_code": str(address.get("zip_code") or "").strip(),
        "leave_at_door": bool(address.get("leave_at_door", False)),
    }


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


def save_onboarding_preferences(user_id, onboarding_data):
    onboarding_data = onboarding_data or {}
    get_user_preferences(user_id)

    budget_range = _normalize_budget_range(onboarding_data.get("budget_range"))
    budget_min = onboarding_data.get("typical_min_budget")
    budget_max = onboarding_data.get("typical_max_budget")
    if budget_range and (budget_min is None and budget_max is None):
        budget_min, budget_max = ONBOARDING_BUDGETS.get(budget_range, (None, None))

    preference_updates = {
        "preferred_cuisines": onboarding_data.get("preferred_cuisines", []),
        "dietary_preferences": _unique(
            _normalize_list(onboarding_data.get("dietary_preferences"))
            + _normalize_list(onboarding_data.get("dietary_restrictions"))
        ),
        "preferred_spice_levels": onboarding_data.get("preferred_spice_levels", []),
        "typical_min_budget": budget_min,
        "typical_max_budget": budget_max,
        "special_preferences": onboarding_data.get("special_preferences", []),
    }
    if onboarding_data.get("dietary_note"):
        preference_updates["special_preferences"] = _unique(
            _normalize_list(preference_updates["special_preferences"])
            + [onboarding_data.get("dietary_note")]
        )

    update_user_preferences(user_id, preference_updates)

    completed = bool(onboarding_data.get("onboarding_completed", True))
    set_values = {
        "budget_range": budget_range,
        "delivery_address": _normalize_address(onboarding_data.get("delivery_address")),
        "order_frequency": str(onboarding_data.get("order_frequency") or "").strip(),
        "order_time": str(onboarding_data.get("order_time") or "").strip(),
        "preferred_meal_time": _normalize_list(onboarding_data.get("preferred_meal_time")),
        "onboarding_completed": completed,
        "updated_at": datetime.utcnow(),
    }
    if budget_range or budget_min is not None or budget_max is not None:
        set_values["typical_min_budget"] = budget_min
        set_values["typical_max_budget"] = budget_max
    if completed:
        set_values["onboarding_completed_at"] = datetime.utcnow()

    user_preference_collection.update_one(
        {"user_id": user_id},
        {"$set": set_values},
        upsert=True,
    )
    return get_user_preferences(user_id)
