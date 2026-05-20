from bson import ObjectId

from service.data.database_service import db

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


def update_item_instruction(user_id, restaurant_id=None, instruction=None):
    """Update special instructions for an item in the user's cart.

    If `restaurant_id` is provided, update the most recent cart item from that restaurant.
    Otherwise update the last item in the cart.
    """

    if instruction is None:
        return 0

    # Find the cart
    cart = cart_collection.find_one({"user_id": user_id})
    if not cart or not cart.get("items"):
        return 0

    target_index = None

    # prefer most recent item from the given restaurant
    if restaurant_id:
        for idx in range(len(cart["items"]) - 1, -1, -1):
            it = cart["items"][idx]
            if it.get("restaurant_id") == restaurant_id:
                target_index = idx
                break

    # fallback to last item
    if target_index is None:
        target_index = len(cart["items"]) - 1

    # build the query to update the specific array element by matching its menu_id
    target_item = cart["items"][target_index]
    menu_id = target_item.get("menu_id")
    if not menu_id:
        return 0

    res = cart_collection.update_one(
        {"user_id": user_id, "items.menu_id": menu_id},
        {"$set": {"items.$.special_instructions": instruction}}
    )

    return res.modified_count


def set_cart_instruction(user_id, instruction=None, restaurant_id=None):
    """Set a top-level special instruction on the cart document.

    Stores the instruction text and the restaurant context used when the prompt was shown.
    """
    if instruction is None:
        return 0

    # ensure cart exists
    create_cart(user_id)

    payload = {
        "special_instructions": instruction,
    }
    if restaurant_id is not None:
        payload["special_instructions_restaurant_id"] = restaurant_id

    res = cart_collection.update_one(
        {"user_id": user_id},
        {"$set": payload}
    )

    return res.modified_count
