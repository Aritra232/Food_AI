from service.data.database_service import db

option_collection = db["user_options"]


def save_options(user_id, options_dict, original_query=None, recommendation_batch_id=None):

    payload = {
        "options": options_dict
    }
    if original_query:
        payload["last_query"] = original_query

    if recommendation_batch_id:
        payload["active_recommendation_batch_id"] = recommendation_batch_id
        payload[f"options_by_batch.{recommendation_batch_id}"] = options_dict
        if original_query:
            payload[f"batch_queries.{recommendation_batch_id}"] = original_query

    option_collection.update_one(
        {"user_id": user_id},
        {
            "$set": payload
        },
        upsert=True
    )


def save_selected_item(user_id, item):

    option_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "selected_item": item
            }
        },
        upsert=True
    )


def get_selected_item(user_id):

    data = option_collection.find_one(
        {"user_id": user_id}
    )

    if not data:
        return None

    return data.get("selected_item")


def get_options(user_id, recommendation_batch_id=None):

    data = option_collection.find_one(
        {"user_id": user_id}
    )

    if not data:
        return {}

    if recommendation_batch_id:
        batch_options = (data.get("options_by_batch") or {}).get(recommendation_batch_id)
        if batch_options:
            return batch_options

    return data.get("options", {})


def get_last_saved_query(user_id):

    data = option_collection.find_one({"user_id": user_id})
    if not data:
        return None
    return data.get("last_query")


def save_last_blocked_items(user_id, blocked_items):

    option_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "last_blocked_items": blocked_items or []
            }
        },
        upsert=True
    )


def get_last_blocked_items(user_id):

    data = option_collection.find_one(
        {"user_id": user_id}
    )

    if not data:
        return []

    return data.get("last_blocked_items", [])


def save_last_instruction_context(user_id, restaurant_id=None):

    option_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "last_instruction_restaurant_id": restaurant_id
            }
        },
        upsert=True
    )


def get_last_instruction_context(user_id):

    data = option_collection.find_one(
        {"user_id": user_id}
    )

    if not data:
        return None

    return data.get("last_instruction_restaurant_id")
