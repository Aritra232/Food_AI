from service.database_service import db

option_collection = db["user_options"]


def save_options(user_id, options_dict):

    option_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "options": options_dict
            }
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


def get_options(user_id):

    data = option_collection.find_one(
        {"user_id": user_id}
    )

    if not data:
        return {}

    return data.get("options", {})