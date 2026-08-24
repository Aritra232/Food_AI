from datetime import datetime

from bson import ObjectId

from service.business.food_item_service import get_food_item, get_food_item_options
from service.data.database_service import ai_cart_session_collection, restaurant_collection
from service.data.mongo_utils import serialize_mongo


def _object_id(value):
    try:
        return ObjectId(value)
    except Exception:
        return None


def _money(value):
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def _find_active_cart(user_id, conversation_id=None):
    query = {"user_id": user_id, "status": "active"}
    object_id = _object_id(conversation_id)
    if object_id:
        query["conversation_id"] = object_id
    return ai_cart_session_collection.find_one(query)


def get_or_create_cart_session(user_id, conversation_id=None, restaurant_id=None):
    existing = _find_active_cart(user_id, conversation_id)
    if existing:
        return serialize_mongo(existing)

    now = datetime.utcnow()
    document = {
        "user_id": user_id,
        "conversation_id": _object_id(conversation_id),
        "restaurant_id": restaurant_id,
        "items": [],
        "subtotal": 0,
        "delivery_fee": 0,
        "total": 0,
        "special_instructions": "",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    result = ai_cart_session_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return serialize_mongo(document)


def _delivery_fee(restaurant_id):
    object_id = _object_id(restaurant_id)
    query = {"_id": object_id} if object_id else {"restaurant_id": restaurant_id}
    restaurant = restaurant_collection.find_one(query) or {}
    return _money(restaurant.get("delivery_fee"))


def _recalculate(cart):
    subtotal = 0
    for item in cart.get("items", []):
        subtotal += _money(item.get("total_price"))
    cart["subtotal"] = _money(subtotal)
    cart["delivery_fee"] = _delivery_fee(cart.get("restaurant_id")) if cart.get("restaurant_id") else 0
    cart["total"] = _money(cart["subtotal"] + cart["delivery_fee"])
    return cart


def _variation_price(food_item, variation_id):
    if not variation_id:
        return None, None
    options = get_food_item_options(food_item.get("food_item_id"))
    for variation in options.get("variations", []):
        if str(variation.get("_id")) == str(variation_id) or str(variation.get("variation_id")) == str(variation_id):
            return variation.get("name"), _money(variation.get("price"))
    return None, None


def _selected_extras(food_item, extra_ids):
    if not extra_ids:
        return [], 0
    requested = {str(item) for item in extra_ids}
    options = get_food_item_options(food_item.get("food_item_id"))
    extras = []
    total = 0
    for extra in options.get("extras", []):
        if str(extra.get("_id")) in requested or str(extra.get("extra_id")) in requested:
            price = _money(extra.get("price"))
            extras.append({
                "extra_id": str(extra.get("_id") or extra.get("extra_id")),
                "name": extra.get("name"),
                "price": price,
            })
            total += price
    return extras, _money(total)


def add_item_to_cart_session(
    user_id,
    conversation_id,
    food_item_id,
    quantity=1,
    variation_id=None,
    extra_ids=None,
    special_instructions="",
):
    food_item = get_food_item(food_item_id)
    if not food_item:
        return None

    cart = get_or_create_cart_session(user_id, conversation_id, restaurant_id=food_item.get("restaurant_id"))
    if cart.get("restaurant_id") and food_item.get("restaurant_id") != cart.get("restaurant_id"):
        # Keep one restaurant per AI cart session for clear delivery fee and checkout.
        return {
            "error": "This cart already has food from another restaurant. Please checkout or start a new cart first."
        }

    quantity = max(1, int(quantity or 1))
    variation_name, variation_price = _variation_price(food_item, variation_id)
    extras, extras_total = _selected_extras(food_item, extra_ids or [])
    unit_price = variation_price if variation_price is not None else _money(food_item.get("base_price"))
    total_price = _money((unit_price + extras_total) * quantity)

    item = {
        "food_item_id": food_item.get("food_item_id"),
        "menu_id": food_item.get("food_item_id"),
        "food_item_name": food_item.get("name"),
        "food_name": food_item.get("name"),
        "restaurant_id": food_item.get("restaurant_id"),
        "variation_id": variation_id,
        "variation_name": variation_name,
        "quantity": quantity,
        "extras": extras,
        "unit_price": unit_price,
        "price": unit_price,
        "total_price": total_price,
        "special_instructions": special_instructions or "",
    }

    object_id = _object_id(cart.get("_id"))
    cart["restaurant_id"] = cart.get("restaurant_id") or food_item.get("restaurant_id")
    cart["items"] = cart.get("items", []) + [item]
    cart = _recalculate(cart)
    cart["updated_at"] = datetime.utcnow()

    ai_cart_session_collection.update_one(
        {"_id": object_id},
        {
            "$set": {
                "restaurant_id": cart["restaurant_id"],
                "items": cart["items"],
                "subtotal": cart["subtotal"],
                "delivery_fee": cart["delivery_fee"],
                "total": cart["total"],
                "updated_at": cart["updated_at"],
            }
        },
    )
    return get_cart_session(user_id, conversation_id)


def update_cart_instructions(user_id, conversation_id=None, instructions=""):
    cart = get_or_create_cart_session(user_id, conversation_id)
    ai_cart_session_collection.update_one(
        {"_id": _object_id(cart["_id"])},
        {"$set": {"special_instructions": instructions or "", "updated_at": datetime.utcnow()}},
    )
    return get_cart_session(user_id, conversation_id)


def get_cart_session(user_id, conversation_id=None):
    cart = _find_active_cart(user_id, conversation_id)
    if not cart:
        return {"user_id": user_id, "items": [], "subtotal": 0, "delivery_fee": 0, "total": 0, "status": "empty"}
    cart = serialize_mongo(cart)
    cart.pop("conversation_id", None)
    return cart


def close_cart_session(cart_id):
    object_id = _object_id(cart_id)
    if object_id:
        ai_cart_session_collection.update_one(
            {"_id": object_id},
            {"$set": {"status": "checked_out", "updated_at": datetime.utcnow()}},
        )
