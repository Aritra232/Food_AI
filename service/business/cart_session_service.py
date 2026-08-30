import math
import os
from datetime import datetime

from bson import ObjectId

from service.business.food_item_service import get_food_item, get_food_item_options
from service.data.database_service import ai_cart_session_collection, restaurant_collection
from service.data.mongo_utils import serialize_mongo


NEARBY_RESTAURANT_MAX_KM = float(os.getenv("NEARBY_RESTAURANT_MAX_KM") or 10)


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


def _restaurant_query(restaurant_id):
    object_id = _object_id(restaurant_id)
    return {"_id": object_id} if object_id else {"restaurant_id": restaurant_id}


def _restaurant_by_id(restaurant_id):
    if not restaurant_id:
        return {}
    return restaurant_collection.find_one(_restaurant_query(restaurant_id)) or {}


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
        "restaurant_ids": [restaurant_id] if restaurant_id else [],
        "items": [],
        "subtotal": 0,
        "delivery_fee": 0,
        "total": 0,
        "special_instructions": "",
        "current_step": "building_cart",
        "last_addon_suggestions": [],
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    result = ai_cart_session_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return serialize_mongo(document)


def _delivery_fee(restaurant_id):
    restaurant = _restaurant_by_id(restaurant_id)
    return _money(restaurant.get("delivery_fee"))


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


def _restaurant_distance(restaurant_id, user_lat=None, user_lng=None):
    if user_lat is None or user_lng is None:
        return None
    restaurant = _restaurant_by_id(restaurant_id)
    location = restaurant.get("location") or {}
    restaurant_lat = restaurant.get("latitude") or restaurant.get("lat") or location.get("lat")
    restaurant_lng = restaurant.get("longitude") or restaurant.get("lng") or location.get("lng")
    if restaurant_lat is None or restaurant_lng is None:
        return None
    try:
        return round(_distance_km(user_lat, user_lng, restaurant_lat, restaurant_lng), 2)
    except Exception:
        return None


def _restaurant_ids_from_items(cart):
    ids = []
    if cart.get("restaurant_id"):
        ids.append(str(cart.get("restaurant_id")))
    for item in cart.get("items", []):
        restaurant_id = item.get("restaurant_id")
        if restaurant_id:
            ids.append(str(restaurant_id))
    return list(dict.fromkeys(ids))


def _recalculate(cart):
    subtotal = 0
    for item in cart.get("items", []):
        subtotal += _money(item.get("total_price"))
    cart["subtotal"] = _money(subtotal)
    restaurant_ids = _restaurant_ids_from_items(cart)
    cart["restaurant_ids"] = restaurant_ids
    cart["restaurant_id"] = restaurant_ids[0] if restaurant_ids else cart.get("restaurant_id")
    cart["delivery_fee"] = _money(sum(_delivery_fee(restaurant_id) for restaurant_id in restaurant_ids))
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


def _item_matches(item, food_item_id=None, food_name=None):
    if food_item_id and str(item.get("food_item_id")) == str(food_item_id):
        return True
    if food_name:
        wanted = str(food_name or "").strip().lower()
        current = str(item.get("food_item_name") or item.get("food_name") or "").strip().lower()
        if wanted and (wanted == current or wanted in current or current in wanted):
            return True
    return False


def _persist_cart(cart):
    cart = _recalculate(cart)
    cart["updated_at"] = datetime.utcnow()
    ai_cart_session_collection.update_one(
        {"_id": _object_id(cart.get("_id"))},
        {
            "$set": {
                "items": cart.get("items", []),
                "restaurant_id": cart.get("restaurant_id"),
                "restaurant_ids": cart.get("restaurant_ids", []),
                "subtotal": cart["subtotal"],
                "delivery_fee": cart["delivery_fee"],
                "total": cart["total"],
                "current_step": cart.get("current_step", "building_cart"),
                "updated_at": cart["updated_at"],
            }
        },
    )


def add_item_to_cart_session(
    user_id,
    conversation_id,
    food_item_id,
    quantity=1,
    variation_id=None,
    extra_ids=None,
    special_instructions="",
    allow_cross_restaurant=False,
    user_lat=None,
    user_lng=None,
    max_distance_km=None,
):
    food_item = get_food_item(food_item_id)
    if not food_item:
        return None

    cart = get_or_create_cart_session(user_id, conversation_id, restaurant_id=food_item.get("restaurant_id"))
    current_restaurant_ids = set(_restaurant_ids_from_items(cart))
    food_restaurant_id = str(food_item.get("restaurant_id") or "")
    if current_restaurant_ids and food_restaurant_id not in current_restaurant_ids:
        if not allow_cross_restaurant:
            return {
                "error": "This cart already has food from another restaurant. Please checkout or start a new cart first."
            }
        if user_lat is None or user_lng is None:
            return {
                "error": "Please share your location before adding food from another restaurant."
            }
        distance = _restaurant_distance(food_item.get("restaurant_id"), user_lat, user_lng)
        allowed_distance = max_distance_km if max_distance_km is not None else NEARBY_RESTAURANT_MAX_KM
        if distance is None or distance > allowed_distance:
            return {
                "error": "That restaurant is not nearby enough to add to this order."
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
                "restaurant_ids": cart.get("restaurant_ids", []),
                "items": cart["items"],
                "subtotal": cart["subtotal"],
                "delivery_fee": cart["delivery_fee"],
                "total": cart["total"],
                "current_step": "suggesting_addons",
                "updated_at": cart["updated_at"],
            }
        },
    )
    return get_cart_session(user_id, conversation_id)


def update_cart_item_quantity(user_id, conversation_id=None, food_item_id=None, food_name=None, quantity=None, delta=None):
    cart = get_or_create_cart_session(user_id, conversation_id)
    items = list(cart.get("items", []))
    matched = False

    for item in items:
        if not _item_matches(item, food_item_id=food_item_id, food_name=food_name):
            continue
        current_quantity = max(1, int(item.get("quantity", 1) or 1))
        if delta is not None:
            new_quantity = current_quantity + int(delta or 0)
        else:
            new_quantity = int(quantity or current_quantity)
        new_quantity = max(1, new_quantity)
        item["quantity"] = new_quantity
        item["total_price"] = _money((item.get("unit_price", item.get("price", 0)) + sum(_money(extra.get("price")) for extra in item.get("extras", []))) * new_quantity)
        matched = True
        break

    if not matched:
        return {"error": "I could not find that item in your cart."}

    cart["items"] = items
    cart["current_step"] = "ready_for_checkout"
    _persist_cart(cart)
    return get_cart_session(user_id, conversation_id)


def remove_cart_item(user_id, conversation_id=None, food_item_id=None, food_name=None, quantity=None):
    cart = get_or_create_cart_session(user_id, conversation_id)
    items = list(cart.get("items", []))
    matched = False
    remove_quantity = int(quantity or 0)
    updated_items = []

    for item in items:
        if matched or not _item_matches(item, food_item_id=food_item_id, food_name=food_name):
            updated_items.append(item)
            continue

        matched = True
        current_quantity = max(1, int(item.get("quantity", 1) or 1))
        if remove_quantity and remove_quantity < current_quantity:
            item["quantity"] = current_quantity - remove_quantity
            item["total_price"] = _money((item.get("unit_price", item.get("price", 0)) + sum(_money(extra.get("price")) for extra in item.get("extras", []))) * item["quantity"])
            updated_items.append(item)

    if not matched:
        return {"error": "I could not find that item in your cart."}

    cart["items"] = updated_items
    cart["current_step"] = "ready_for_checkout"
    _persist_cart(cart)
    return get_cart_session(user_id, conversation_id)


def update_cart_instructions(user_id, conversation_id=None, instructions="", current_step="ready_for_checkout"):
    cart = get_or_create_cart_session(user_id, conversation_id)
    ai_cart_session_collection.update_one(
        {"_id": _object_id(cart["_id"])},
        {
            "$set": {
                "special_instructions": instructions or "",
                "current_step": current_step,
                "updated_at": datetime.utcnow(),
            }
        },
    )
    return get_cart_session(user_id, conversation_id)


def update_cart_step(user_id, conversation_id=None, current_step="building_cart", addon_suggestions=None):
    cart = get_or_create_cart_session(user_id, conversation_id)
    payload = {
        "current_step": current_step,
        "updated_at": datetime.utcnow(),
    }
    if addon_suggestions is not None:
        payload["last_addon_suggestions"] = addon_suggestions

    ai_cart_session_collection.update_one(
        {"_id": _object_id(cart["_id"])},
        {"$set": payload},
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
