from bson import ObjectId

from service.database_service import db

cart_collection = db["cart"]


def _serialize_mongo_value(value):

    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, list):
        return [_serialize_mongo_value(item) for item in value]

    if isinstance(value, dict):
        return {
            key: _serialize_mongo_value(item)
            for key, item in value.items()
        }

    return value


def create_cart(user_id):

    existing = cart_collection.find_one(
        {"user_id": user_id}
    )

    if not existing:

        cart_collection.insert_one({
            "user_id": user_id,
            "items": [],
            "status": "active"
        })


def add_to_cart(user_id, item):

    create_cart(user_id)

    cart_collection.update_one(
        {"user_id": user_id},
        {
            "$push": {
                "items": item
            }
        }
    )


def get_cart(user_id):

    cart = cart_collection.find_one(
        {"user_id": user_id}
    )

    if not cart:
        return None

    return _serialize_mongo_value(cart)


def clear_cart(user_id):

    cart_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "items": []
            }
        }
    )