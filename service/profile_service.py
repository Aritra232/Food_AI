from datetime import datetime
import re

from service.database_service import user_profile_collection


def _normalize_list(value):
    if not value:
        return []

    if isinstance(value, str):
        parts = re.split(r",|;|\band\b|\|", value)
        return [item.strip() for item in parts if item.strip()]

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    return [str(value).strip()]


def _is_generic_allergy_reference(value):
    if not value:
        return False

    return str(value).strip().lower() in {
        "both",
        "all",
        "all of them",
        "these",
        "those",
        "them",
        "it",
        "ones",
        "them all"
    }


def _extract_allergy_terms(values):
    allergies = []

    for value in _normalize_list(values):
        cleaned = value.strip()
        lower_value = cleaned.lower()

        if lower_value.startswith("allergic to "):
            cleaned = cleaned[12:].strip()
        elif lower_value.startswith("allergy to "):
            cleaned = cleaned[11:].strip()
        elif lower_value.startswith("allergic"):
            cleaned = cleaned.replace("allergic", "", 1).strip(" :-")

        if cleaned:
            allergies.append(cleaned)

    return allergies


def _merge_unique_case_insensitive(items):
    merged = []
    seen = set()

    for item in _normalize_list(items):
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)

    return merged


def create_user_profile_if_not_exists(user_id):

    existing_user = user_profile_collection.find_one({
        "user_id": user_id
    })

    if existing_user:
        return

    default_profile = {
        "user_id": user_id,
        "onboarding_completed": False,
        "onboarding_completed_at": None,
        "delivery_address": {
            "address_type": "",
            "street_address": "",
            "city": "",
            "zip_code": ""
        },
        "preferences": {
            "favorite_foods": [],
            "disliked_foods": [],
            "favorite_restaurants": [],
            "preferred_cuisines": [],
            "dietary_restrictions": [],
            "spicy_level": "",
            "budget_range": "",
            "dietary_style": "",
            "allergies": [],
            "favorite_drinks": [],
            "preferred_meal_time": [],
            "order_frequency": "",
            "order_time": "",
            "delivery_speed_preference": "",
            "portion_size_preference": ""
        },
        "order_history": [],
        "last_ordered_at": None
    }

    user_profile_collection.insert_one(default_profile)


def get_user_profile(user_id):

    create_user_profile_if_not_exists(user_id)

    profile = user_profile_collection.find_one({
        "user_id": user_id
    })

    profile["_id"] = str(profile["_id"])

    return profile


def update_favorite_food(user_id, food_name):

    create_user_profile_if_not_exists(user_id)

    user_profile_collection.update_one(
        {
            "user_id": user_id
        },
        {
            "$addToSet": {
                "preferences.favorite_foods": food_name
            }
        }
    )


def update_user_preferences(user_id, extracted_data):

    create_user_profile_if_not_exists(user_id)

    current_profile = user_profile_collection.find_one({
        "user_id": user_id
    }) or {}
    current_preferences = current_profile.get("preferences", {})
    existing_allergies = _normalize_list(current_preferences.get("allergies", []))

    update_query = {}

    if extracted_data.get("favorite_foods"):

        update_query["preferences.favorite_foods"] = extracted_data["favorite_foods"]

    if extracted_data.get("disliked_foods"):

        update_query["preferences.disliked_foods"] = extracted_data["disliked_foods"]

    if extracted_data.get("allergies"):

        normalized_allergies = _normalize_list(extracted_data["allergies"])
        cleaned_allergies = [item for item in normalized_allergies if not _is_generic_allergy_reference(item)]

        if not cleaned_allergies and existing_allergies:
            cleaned_allergies = existing_allergies
        elif existing_allergies:
            for item in existing_allergies:
                if item not in cleaned_allergies:
                    cleaned_allergies.append(item)

        if cleaned_allergies:
            update_query["preferences.allergies"] = cleaned_allergies

    allergy_like_dislikes = _extract_allergy_terms(extracted_data.get("disliked_foods", []))
    if allergy_like_dislikes:

        merged_allergies = _merge_unique_case_insensitive(existing_allergies + allergy_like_dislikes)
        update_query["preferences.allergies"] = merged_allergies

        filtered_disliked = []
        for item in _normalize_list(extracted_data.get("disliked_foods", [])):
            if item not in allergy_like_dislikes:
                filtered_disliked.append(item)

        update_query["preferences.disliked_foods"] = filtered_disliked

    if extracted_data.get("spicy_level"):

        update_query["preferences.spicy_level"] = extracted_data["spicy_level"]

    if extracted_data.get("budget_range"):

        update_query["preferences.budget_range"] = extracted_data["budget_range"]

    if extracted_data.get("preferred_cuisines"):

        update_query["preferences.preferred_cuisines"] = extracted_data["preferred_cuisines"]

    if extracted_data.get("dietary_style"):

        update_query["preferences.dietary_style"] = extracted_data["dietary_style"]

    if extracted_data.get("dietary_restrictions"):

        update_query["preferences.dietary_restrictions"] = extracted_data["dietary_restrictions"]

    if extracted_data.get("order_frequency"):

        update_query["preferences.order_frequency"] = extracted_data["order_frequency"]

    if extracted_data.get("order_time"):

        update_query["preferences.order_time"] = extracted_data["order_time"]

    if extracted_data.get("delivery_address"):

        update_query["delivery_address"] = extracted_data["delivery_address"]

    if extracted_data.get("onboarding_completed") is not None:

        update_query["onboarding_completed"] = bool(extracted_data["onboarding_completed"])

        if extracted_data["onboarding_completed"]:

            update_query["onboarding_completed_at"] = datetime.utcnow()

    for field, value in update_query.items():

        user_profile_collection.update_one(
            {
                "user_id": user_id
            },
            {
                "$set": {
                    field: value
                }
            }
        )


def save_onboarding_profile(user_id, onboarding_data):

    create_user_profile_if_not_exists(user_id)

    delivery_address = onboarding_data.get("delivery_address", {}) or {}
    cleaned_address = {
        "address_type": str(delivery_address.get("address_type", "")).strip(),
        "street_address": str(delivery_address.get("street_address", "")).strip(),
        "city": str(delivery_address.get("city", "")).strip(),
        "zip_code": str(delivery_address.get("zip_code", "")).strip()
    }

    update_user_preferences(
        user_id,
        {
            "preferred_cuisines": _normalize_list(onboarding_data.get("preferred_cuisines")),
            "dietary_style": ", ".join(_normalize_list(onboarding_data.get("dietary_restrictions"))),
            "dietary_restrictions": _normalize_list(onboarding_data.get("dietary_restrictions")),
            "budget_range": str(onboarding_data.get("budget_range", "")).strip(),
            "preferred_meal_time": _normalize_list(onboarding_data.get("preferred_meal_time")),
            "order_frequency": str(onboarding_data.get("order_frequency", "")).strip(),
            "order_time": str(onboarding_data.get("order_time", "")).strip(),
            "delivery_address": cleaned_address,
            "onboarding_completed": True
        }
    )

    return get_user_profile(user_id)


def record_order_history(user_id, item):

    create_user_profile_if_not_exists(user_id)

    if not item:
        return

    restaurant = item.get("restaurant_id")
    cuisine = item.get("cuisine")

    operations = {"$push": {}, "$set": {}, "$addToSet": {}}
    operations["$push"]["order_history"] = {
        "menu_id": item.get("menu_id"),
        "food_name": item.get("food_name"),
        "price": item.get("price"),
        "restaurant_id": restaurant,
        "ordered_at": datetime.utcnow()
    }
    operations["$set"]["last_ordered_at"] = datetime.utcnow()

    if item.get("food_name"):
        operations["$addToSet"]["preferences.favorite_foods"] = {"$each": _normalize_list(item.get("food_name"))}

    if restaurant:
        operations["$addToSet"]["preferences.favorite_restaurants"] = restaurant

    if cuisine:
        cuisines = _normalize_list(cuisine)
        if cuisines:
            operations["$addToSet"]["preferences.preferred_cuisines"] = {"$each": cuisines}

    final_ops = {}
    if operations["$addToSet"]:
        final_ops["$addToSet"] = operations["$addToSet"]
    if operations["$push"]:
        final_ops["$push"] = operations["$push"]
    if operations["$set"]:
        final_ops["$set"] = operations["$set"]

    user_profile_collection.update_one({"user_id": user_id}, final_ops)