from datetime import datetime, timedelta

from bson import ObjectId

from service.business.cart_session_service import close_cart_session, get_cart_session
from service.data.database_service import orders_collection, user_food_interaction_collection
from service.data.mongo_utils import serialize_mongo


def _object_id(value):
    try:
        return ObjectId(value)
    except Exception:
        return None


def record_food_interaction(user_id, food_item_id, restaurant_id=None, interaction_type="viewed", conversation_id=None):
    document = {
        "user_id": user_id,
        "food_item_id": food_item_id,
        "restaurant_id": restaurant_id,
        "interaction_type": interaction_type,
        "conversation_id": _object_id(conversation_id),
        "created_at": datetime.utcnow(),
    }
    user_food_interaction_collection.insert_one(document)
    return serialize_mongo(document)


def create_order_from_cart(user_id, conversation_id=None, delivery_address=None):
    cart = get_cart_session(user_id, conversation_id)
    if not cart.get("items"):
        return {"error": "Cart is empty"}

    now = datetime.utcnow()
    order = {
        "user_id": user_id,
        "conversation_id": _object_id(conversation_id),
        "restaurant_id": cart.get("restaurant_id"),
        "restaurant_ids": cart.get("restaurant_ids", [cart.get("restaurant_id")] if cart.get("restaurant_id") else []),
        "items": cart.get("items", []),
        "subtotal": cart.get("subtotal", 0),
        "delivery_fee": cart.get("delivery_fee", 0),
        "total": cart.get("total", 0),
        "special_instructions": cart.get("special_instructions", ""),
        "delivery_address": delivery_address or {},
        "status": "pending_restaurant_acceptance",
        "estimated_delivery_time": now + timedelta(minutes=45),
        "created_at": now,
        "updated_at": now,
    }
    result = orders_collection.insert_one(order)

    for item in order["items"]:
        record_food_interaction(
            user_id,
            item.get("food_item_id"),
            restaurant_id=item.get("restaurant_id"),
            interaction_type="ordered",
            conversation_id=conversation_id,
        )

    close_cart_session(cart.get("_id"))
    order["_id"] = result.inserted_id
    return serialize_mongo(order)


def get_order(order_id, user_id=None):
    object_id = _object_id(order_id)
    if not object_id:
        return None
    query = {"_id": object_id}
    if user_id:
        query["user_id"] = user_id
    order = orders_collection.find_one(query)
    return serialize_mongo(order) if order else None


def list_orders(user_id, limit=20):
    cursor = orders_collection.find({"user_id": user_id}).sort("created_at", -1).limit(int(limit or 20))
    return [serialize_mongo(doc) for doc in cursor]


def get_latest_order(user_id):
    order = orders_collection.find_one({"user_id": user_id}, sort=[("created_at", -1)])
    return serialize_mongo(order) if order else None
