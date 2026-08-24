from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from service.ai.food_chat_service import (
    explain_recommendations,
    general_chat_reply,
    interpret_message,
    order_status_reply,
)
from service.business.cart_session_service import (
    add_item_to_cart_session,
    get_cart_session,
    update_cart_instructions,
)
from service.business.final_order_service import (
    create_order_from_cart,
    get_latest_order,
    get_order,
    list_orders,
    record_food_interaction,
)
from service.business.food_item_service import (
    create_food_item,
    find_food_items,
    get_food_item,
    get_food_item_options,
)
from service.data.database_service import (
    food_item_extra_collection,
    food_item_variation_collection,
    restaurant_collection,
)
from service.data.mongo_utils import serialize_mongo
from service.data.preference_memory_service import get_user_preferences, update_user_preferences
from service.memory.ai_conversation_service import (
    add_message,
    get_messages,
    get_or_create_conversation,
    list_conversations,
)

OPENAPI_TAGS = [
    {"name": "System", "description": "Check if the API is running."},
    {"name": "AI Chat", "description": "Talk to the food assistant and load chat history."},
    {"name": "Add Data", "description": "Add restaurants, food items, sizes, extras, or import all catalog data."},
    {"name": "Find Food", "description": "Search restaurants, food items, sizes, and extras."},
    {"name": "User Memory", "description": "Save and read user preferences, allergies, and dietary rules."},
    {"name": "Cart & Orders", "description": "Build a cart, save instructions, checkout, and track orders."},
]

app = FastAPI(title="Food AI", version="2.0.0", openapi_tags=OPENAPI_TAGS)


class ChatRequest(BaseModel):
    user_id: str = "user123"
    message: str
    conversation_id: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class FoodItemCreate(BaseModel):
    food_item_id: Optional[str] = None
    restaurant_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    name: str
    description: str = ""
    image: str = ""
    category: str = ""
    base_price: float = 0
    spice_level: str = ""
    tags: List[str] = Field(default_factory=list)
    ingredients: List[str] = Field(default_factory=list)
    is_available: bool = True


class FoodItemVariationCreate(BaseModel):
    food_item_id: str
    name: str
    price: float
    is_available: bool = True


class FoodItemExtraCreate(BaseModel):
    food_item_id: str
    name: str
    price: float = 0
    is_available: bool = True


class RestaurantCreate(BaseModel):
    name: str
    profile_image: str = ""
    cover_image: str = ""
    category: str = ""
    description: str = ""
    address: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    delivery_fee: float = 0
    is_active: bool = True


class AddToCartRequest(BaseModel):
    user_id: str
    conversation_id: Optional[str] = None
    food_item_id: str
    quantity: int = 1
    variation_id: Optional[str] = None
    extra_ids: List[str] = Field(default_factory=list)
    special_instructions: str = ""


class CheckoutRequest(BaseModel):
    user_id: str
    conversation_id: Optional[str] = None
    delivery_address: Dict[str, Any] = Field(default_factory=dict)


class CatalogImportRequest(BaseModel):
    restaurants: List[RestaurantCreate] = Field(default_factory=list)
    food_items: List[FoodItemCreate] = Field(default_factory=list)
    variations: List[FoodItemVariationCreate] = Field(default_factory=list)
    extras: List[FoodItemExtraCreate] = Field(default_factory=list)


def _combined_preferences(base_preferences, request_filters):
    combined = dict(base_preferences or {})
    dietary = list(combined.get("dietary_preferences") or [])
    for item in request_filters.get("dietary") or []:
        if item and item not in dietary:
            dietary.append(item)
    combined["dietary_preferences"] = dietary
    return combined


def _latest_recommendations(messages):
    for message in reversed(messages or []):
        data = message.get("structured_data") or {}
        recommendations = data.get("recommendations") or []
        if recommendations:
            return recommendations
    return []


def _resolve_selected_food_id(interpretation, message, recent_messages):
    cart_action = interpretation.get("cart_action") or {}
    if cart_action.get("food_item_id"):
        return cart_action.get("food_item_id")

    text = (message or "").strip().lower()
    recommendations = _latest_recommendations(recent_messages)
    if not recommendations:
        return None

    letter_match = {
        "a": 0,
        "option a": 0,
        "b": 1,
        "option b": 1,
        "c": 2,
        "option c": 2,
        "d": 3,
        "option d": 3,
        "e": 4,
        "option e": 4,
    }
    if text in letter_match and letter_match[text] < len(recommendations):
        return recommendations[letter_match[text]].get("food_item_id")

    for index, item in enumerate(recommendations, start=1):
        if text in {str(index), f"option {index}", f"number {index}"}:
            return item.get("food_item_id")
        name = str(item.get("name") or "").lower()
        if name and (name in text or text in name):
            return item.get("food_item_id")
    return None


def _message_text(message):
    return message.get("message") or message.get("content") or ""


def _model_dump(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _slug(value):
    return str(value or "").strip().lower().replace(" ", "-")


def _distance_km(lat1, lng1, lat2, lng2):
    from math import asin, cos, radians, sin, sqrt

    earth_radius = 6371
    dlat = radians(float(lat2) - float(lat1))
    dlng = radians(float(lng2) - float(lng1))
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(float(lat1)))
        * cos(radians(float(lat2)))
        * sin(dlng / 2) ** 2
    )
    return earth_radius * 2 * asin(sqrt(a))


def _nearest_restaurant_id(latitude=None, longitude=None):
    if latitude is None or longitude is None:
        return None

    nearest = None
    nearest_distance = None
    for restaurant in restaurant_collection.find({"is_active": {"$ne": False}}):
        location = restaurant.get("location") or {}
        restaurant_lat = restaurant.get("latitude") or restaurant.get("lat") or location.get("lat")
        restaurant_lng = restaurant.get("longitude") or restaurant.get("lng") or location.get("lng")
        if restaurant_lat is None or restaurant_lng is None:
            continue
        try:
            distance = _distance_km(latitude, longitude, restaurant_lat, restaurant_lng)
        except Exception:
            continue
        if nearest_distance is None or distance < nearest_distance:
            nearest = restaurant
            nearest_distance = distance

    if not nearest:
        return None
    return str(nearest.get("_id"))


def _prepare_food_item_payload(payload):
    payload = dict(payload or {})
    if not payload.get("restaurant_id"):
        payload["restaurant_id"] = _nearest_restaurant_id(
            payload.pop("latitude", None),
            payload.pop("longitude", None),
        )
    else:
        payload.pop("latitude", None)
        payload.pop("longitude", None)
    if not payload.get("restaurant_id"):
        raise HTTPException(
            status_code=400,
            detail="restaurant_id is required when no nearby restaurant can be found from latitude/longitude",
        )
    return payload


def _with_timestamps(payload):
    now = datetime.utcnow()
    payload = dict(payload or {})
    payload.setdefault("created_at", now)
    payload["updated_at"] = now
    return payload


def _insert_one(collection, payload):
    payload = _with_timestamps(payload)
    result = collection.insert_one(payload)
    payload["_id"] = result.inserted_id
    return serialize_mongo(payload)


@app.get("/", tags=["System"], summary="Check API")
def home():
    return {
        "message": "Food AI is running",
        "collections": [
            "restaurants",
            "food_items",
            "food_item_variations",
            "food_item_extras",
            "user_preferences",
            "ai_conversations",
            "ai_messages",
            "ai_cart_sessions",
            "user_food_interactions",
            "orders",
        ],
    }


@app.get("/user-preferences", tags=["User Memory"], summary="Get User Memory")
def read_user_preferences(user_id: str):
    return get_user_preferences(user_id)


@app.patch("/user-preferences", tags=["User Memory"], summary="Update User Memory")
def patch_user_preferences(user_id: str, updates: Dict[str, Any] = Body(default_factory=dict)):
    return update_user_preferences(user_id, updates)


@app.get("/user-profile", include_in_schema=False)
def get_profile_info(user_id: str):
    preferences = get_user_preferences(user_id)
    return {
        "user_id": user_id,
        "onboarding_completed": True,
        "preferences": {
            "preferred_cuisines": preferences.get("preferred_cuisines", []),
            "dietary_restrictions": preferences.get("dietary_preferences", []),
            "dietary_style": ", ".join(preferences.get("dietary_preferences", [])),
            "allergies": preferences.get("allergies", []),
            "disliked_foods": preferences.get("disliked_ingredients", []),
            "favorite_foods": preferences.get("favorite_food_items", []),
            "favorite_restaurants": preferences.get("favorite_restaurants", []),
            "spicy_level": ", ".join(preferences.get("preferred_spice_levels", [])),
            "budget_range": "",
        },
        "delivery_address": {},
        "delivery_addresses": [],
    }


@app.post("/profile/onboarding", include_in_schema=False)
def save_profile_onboarding(user_id: str, data: Dict[str, Any] = Body(default_factory=dict)):
    updates = {
        "preferred_cuisines": data.get("preferred_cuisines", []),
        "dietary_preferences": data.get("dietary_restrictions", []),
        "special_preferences": [data.get("dietary_note")] if data.get("dietary_note") else [],
    }
    return update_user_preferences(user_id, updates)


@app.get("/chat-history", tags=["AI Chat"], summary="Load Chat History")
def get_chat_history(user_id: str, chat_session_id: Optional[str] = None, conversation_id: Optional[str] = None):
    selected_id = conversation_id or chat_session_id
    conversations = list_conversations(user_id)
    if not selected_id and conversations:
        selected_id = conversations[0].get("_id")

    messages = get_messages(selected_id, user_id) if selected_id else []
    chat_history = [{"role": msg.get("role"), "content": _message_text(msg)} for msg in messages]
    chat_sessions = [
        {
            "chat_session_id": conv.get("_id"),
            "title": conv.get("title"),
            "message_count": len(get_messages(conv.get("_id"), user_id, limit=500)),
            "created_at": conv.get("created_at"),
            "updated_at": conv.get("updated_at"),
        }
        for conv in conversations
    ]
    return {
        "user_id": user_id,
        "chat_session_id": selected_id,
        "conversation_id": selected_id,
        "chat_history": chat_history,
        "chat_sessions": chat_sessions,
        "user_profile": get_profile_info(user_id),
    }


@app.post("/chat", tags=["AI Chat"], summary="Send Message")
def chat(
    user_id: Optional[str] = Query(default=None),
    message: Optional[str] = Query(default=None),
    lat: Optional[float] = Query(default=None),
    lng: Optional[float] = Query(default=None),
    chat_session_id: Optional[str] = Query(default=None),
    conversation_id: Optional[str] = Query(default=None),
    payload: Optional[ChatRequest] = Body(default=None),
):
    if payload:
        user_id = payload.user_id
        message = payload.message
        conversation_id = payload.conversation_id or conversation_id
        lat = payload.lat if payload.lat is not None else lat
        lng = payload.lng if payload.lng is not None else lng

    if not user_id or not message:
        raise HTTPException(status_code=400, detail="user_id and message are required")

    conversation = get_or_create_conversation(user_id, conversation_id or chat_session_id, first_message=message)
    conversation_id = conversation["_id"]
    preferences = get_user_preferences(user_id)
    recent_messages = get_messages(conversation_id, user_id, limit=30)
    interpretation = interpret_message(message, preferences, recent_messages)
    preference_updates = interpretation.get("preference_updates") or {}
    if any(value for value in preference_updates.values()):
        preferences = update_user_preferences(user_id, preference_updates)

    intent = interpretation.get("intent") or "general_chat"
    filters = interpretation.get("filters") or {}
    if not filters.get("query"):
        filters["query"] = message

    add_message(user_id, conversation_id, "user", message, intent=intent, structured_data=interpretation)

    if intent == "recommend_food":
        request_preferences = _combined_preferences(preferences, filters)
        recommendations = find_food_items(filters, request_preferences, lat=lat, lng=lng, limit=5)
        for item in recommendations:
            record_food_interaction(
                user_id,
                item.get("food_item_id"),
                restaurant_id=item.get("restaurant_id"),
                interaction_type="recommended",
                conversation_id=conversation_id,
            )
        response_text = explain_recommendations(message, recommendations, request_preferences)
        add_message(
            user_id,
            conversation_id,
            "assistant",
            response_text,
            intent="recommend_food",
            structured_data={"recommendations": recommendations},
        )
        return {
            "intent": intent,
            "state": "browsing",
            "conversation_id": conversation_id,
            "chat_session_id": conversation_id,
            "message": response_text,
            "ai_response": {"response": response_text},
            "recommendations": recommendations,
        }

    if intent == "add_to_cart":
        food_item_id = _resolve_selected_food_id(interpretation, message, recent_messages)
        if not food_item_id:
            response_text = "Which food item would you like to add? You can choose by option number or food name."
        else:
            action = interpretation.get("cart_action") or {}
            cart = add_item_to_cart_session(
                user_id,
                conversation_id,
                food_item_id,
                quantity=action.get("quantity") or 1,
                variation_id=action.get("variation_id") or None,
                extra_ids=action.get("extra_ids") or [],
                special_instructions=interpretation.get("special_instructions") or "",
            )
            if cart and cart.get("error"):
                response_text = cart["error"]
            else:
                food = get_food_item(food_item_id)
                response_text = f"Added {food.get('name') if food else 'that food item'} to your cart."
        add_message(user_id, conversation_id, "assistant", response_text, intent="add_to_cart")
        return {
            "intent": intent,
            "state": "cart",
            "conversation_id": conversation_id,
            "chat_session_id": conversation_id,
            "message": response_text,
            "cart": get_cart_session(user_id, conversation_id),
        }

    if intent == "checkout":
        order = create_order_from_cart(user_id, conversation_id)
        response_text = order.get("error") or f"Your order has been created. Status: {order.get('status')}."
        add_message(user_id, conversation_id, "assistant", response_text, intent="checkout", structured_data={"order": order})
        return {
            "intent": intent,
            "state": "ordered" if not order.get("error") else "cart",
            "conversation_id": conversation_id,
            "chat_session_id": conversation_id,
            "message": response_text,
            "order": order,
        }

    if intent == "update_cart":
        instruction = interpretation.get("special_instructions") or message
        cart = update_cart_instructions(user_id, conversation_id, instruction)
        if cart.get("items"):
            response_text = "Got it. I saved that instruction with your cart."
        else:
            response_text = "I saved the note, but your cart is still empty. Add a food item first when you are ready."
        add_message(
            user_id,
            conversation_id,
            "assistant",
            response_text,
            intent="update_cart",
            structured_data={"cart": cart, "special_instructions": instruction},
        )
        return {
            "intent": intent,
            "state": "cart",
            "conversation_id": conversation_id,
            "chat_session_id": conversation_id,
            "message": response_text,
            "cart": cart,
        }

    if intent == "order_status":
        order = get_latest_order(user_id)
        response_text = order_status_reply(order)
        add_message(
            user_id,
            conversation_id,
            "assistant",
            response_text,
            intent="order_status",
            structured_data={"order": order or {}},
        )
        return {
            "intent": intent,
            "state": "order_status",
            "conversation_id": conversation_id,
            "chat_session_id": conversation_id,
            "message": response_text,
            "order": order,
        }

    if preference_updates and intent == "general_chat":
        response_text = "Got it. I saved that preference and will use it for future recommendations."
    else:
        response_text = general_chat_reply(message, preferences, get_cart_session(user_id, conversation_id))
    add_message(user_id, conversation_id, "assistant", response_text, intent="general_chat")
    return {
        "intent": intent,
        "state": "chat",
        "conversation_id": conversation_id,
        "chat_session_id": conversation_id,
        "message": response_text,
    }


@app.post("/restaurants", tags=["Add Data"], summary="Add Restaurant")
def create_restaurant(data: RestaurantCreate):
    payload = _model_dump(data)
    return _insert_one(restaurant_collection, payload)


@app.post("/add-restaurant", include_in_schema=False)
def create_restaurant_legacy(data: Dict[str, Any] = Body(default_factory=dict)):
    payload = _model_dump(RestaurantCreate(**data))
    return {"message": "Restaurant added", "restaurant": _insert_one(restaurant_collection, payload)}


@app.get("/restaurants", tags=["Find Food"], summary="Get Restaurants")
def list_restaurants():
    return [serialize_mongo(doc) for doc in restaurant_collection.find({})]


@app.post("/food-items", tags=["Add Data"], summary="Add Food Item")
def add_food_item(data: FoodItemCreate):
    return create_food_item(_prepare_food_item_payload(_model_dump(data)))


@app.post("/food-item-variations", tags=["Add Data"], summary="Add Size Or Variation")
def add_food_item_variation(data: FoodItemVariationCreate):
    payload = _model_dump(data)
    return _insert_one(food_item_variation_collection, payload)


@app.get("/food-item-variations", tags=["Find Food"], summary="Get Sizes Or Variations")
def list_food_item_variations(food_item_id: Optional[str] = None):
    query = {}
    if food_item_id:
        query["food_item_id"] = food_item_id
    return [serialize_mongo(doc) for doc in food_item_variation_collection.find(query)]


@app.post("/food-item-extras", tags=["Add Data"], summary="Add Extra")
def add_food_item_extra(data: FoodItemExtraCreate):
    payload = _model_dump(data)
    return _insert_one(food_item_extra_collection, payload)


@app.get("/food-item-extras", tags=["Find Food"], summary="Get Extras")
def list_food_item_extras(food_item_id: Optional[str] = None):
    query = {}
    if food_item_id:
        query["food_item_id"] = food_item_id
    return [serialize_mongo(doc) for doc in food_item_extra_collection.find(query)]


@app.post("/catalog/import", tags=["Add Data"], summary="Import Catalog")
def import_catalog(data: CatalogImportRequest):
    imported = {
        "restaurants": [],
        "food_items": [],
        "variations": [],
        "extras": [],
    }

    for restaurant in data.restaurants:
        payload = _model_dump(restaurant)
        imported["restaurants"].append(_insert_one(restaurant_collection, payload))

    for food_item in data.food_items:
        imported["food_items"].append(create_food_item(_prepare_food_item_payload(_model_dump(food_item))))

    for variation in data.variations:
        imported["variations"].append(
            _insert_one(food_item_variation_collection, _model_dump(variation))
        )

    for extra in data.extras:
        imported["extras"].append(
            _insert_one(food_item_extra_collection, _model_dump(extra))
        )

    return {
        "message": "Catalog data imported",
        "counts": {key: len(value) for key, value in imported.items()},
        "imported": imported,
    }


@app.post("/add-menu", include_in_schema=False)
def add_menu_legacy(data: Dict[str, Any] = Body(default_factory=dict)):
    payload = {
        "restaurant_id": data.get("restaurant_id"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "name": data.get("name") or data.get("food_name"),
        "description": data.get("description", ""),
        "category": data.get("category", ""),
        "base_price": data.get("base_price", data.get("price", 0)),
        "spice_level": data.get("spice_level", data.get("spicy_level", "")),
        "tags": data.get("tags", []),
        "ingredients": data.get("ingredients", []),
        "is_available": data.get("is_available", data.get("available", True)),
    }
    return {"message": "Food item added", "food_item": create_food_item(_prepare_food_item_payload(payload))}


@app.get("/food-items", tags=["Find Food"], summary="Search Food Items")
def search_food_items(
    q: str = "",
    user_id: str = "anonymous",
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    limit: int = 20,
):
    preferences = get_user_preferences(user_id)
    return {"food_items": find_food_items({"query": q}, preferences, lat=lat, lng=lng, limit=limit)}


@app.get("/recommend-food", include_in_schema=False)
def recommend_food(user_id: str, food: str = "popular", lat: Optional[float] = None, lng: Optional[float] = None):
    preferences = get_user_preferences(user_id)
    return find_food_items({"query": food}, preferences, lat=lat, lng=lng, limit=5)


@app.get("/available-foods", include_in_schema=False)
def available_foods(user_id: str, lat: Optional[float] = None, lng: Optional[float] = None, limit: int = 20):
    preferences = get_user_preferences(user_id)
    foods = find_food_items({}, preferences, lat=lat, lng=lng, limit=limit)
    return {"foods": foods, "count": len(foods)}


@app.get("/search-food", include_in_schema=False)
def search_food(food: str, user_id: str = "anonymous"):
    preferences = get_user_preferences(user_id)
    return find_food_items({"query": food}, preferences, limit=20)


@app.get("/food-items/{food_item_id}/options", tags=["Find Food"], summary="Get Food Options")
def food_item_options(food_item_id: str):
    food = get_food_item(food_item_id)
    if not food:
        raise HTTPException(status_code=404, detail="Food item not found")
    return {"food_item": food, **get_food_item_options(food_item_id)}


@app.post("/cart/items", tags=["Cart & Orders"], summary="Add To Cart")
def add_cart_item(data: AddToCartRequest):
    cart = add_item_to_cart_session(
        data.user_id,
        data.conversation_id,
        data.food_item_id,
        quantity=data.quantity,
        variation_id=data.variation_id,
        extra_ids=data.extra_ids,
        special_instructions=data.special_instructions,
    )
    if cart and cart.get("error"):
        raise HTTPException(status_code=400, detail=cart["error"])
    return cart


@app.post("/order-with-ai", include_in_schema=False)
def order_with_ai(
    user_id: str,
    menu_id: str,
    quantity: int = 1,
    chat_mode: bool = False,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    chat_session_id: Optional[str] = None,
):
    conversation = get_or_create_conversation(user_id, chat_session_id, first_message="Order with AI")
    cart = add_item_to_cart_session(user_id, conversation["_id"], menu_id, quantity=quantity)
    if cart and cart.get("error"):
        raise HTTPException(status_code=400, detail=cart["error"])
    food = get_food_item(menu_id)
    message = f"Added {food.get('name') if food else 'that food item'} to your cart."
    add_message(user_id, conversation["_id"], "assistant", message, intent="add_to_cart")
    return {
        "intent": "add_to_cart",
        "state": "cart",
        "conversation_id": conversation["_id"],
        "chat_session_id": conversation["_id"],
        "message": message,
        "selected_item": food,
        "cart": cart,
    }


@app.get("/cart", tags=["Cart & Orders"], summary="View Cart")
def view_cart(user_id: str, conversation_id: Optional[str] = None, chat_session_id: Optional[str] = None):
    cart = get_cart_session(user_id, conversation_id or chat_session_id)
    return {"cart": cart, "total_price": cart.get("total", 0)}


@app.post("/instruction", tags=["Cart & Orders"], summary="Save Instruction")
def add_instruction(
    user_id: str,
    instruction: str,
    restaurant_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
):
    cart = update_cart_instructions(user_id, conversation_id or chat_session_id, instruction)
    return {"status": "ok", "target": "cart_level", "cart": cart}


@app.post("/checkout", tags=["Cart & Orders"], summary="Checkout")
def checkout(data: CheckoutRequest):
    order = create_order_from_cart(data.user_id, data.conversation_id, data.delivery_address)
    if order.get("error"):
        raise HTTPException(status_code=400, detail=order["error"])
    return order


@app.get("/orders", tags=["Cart & Orders"], summary="Get Orders")
def read_orders(user_id: str, limit: int = 20):
    return {"orders": list_orders(user_id, limit)}


@app.get("/orders/{order_id}", tags=["Cart & Orders"], summary="Get Order")
def read_order(order_id: str, user_id: Optional[str] = None):
    order = get_order(order_id, user_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/orders/{order_id}/ai-status", tags=["Cart & Orders"], summary="Ask AI About Order")
def read_order_status_ai(order_id: str, user_id: Optional[str] = None):
    order = get_order(order_id, user_id)
    return {"message": order_status_reply(order), "order": order}


@app.post("/profile/address", include_in_schema=False)
def upsert_profile_address(
    user_id: str,
    address: Dict[str, Any] = Body(default_factory=dict),
    address_id: Optional[str] = None,
):
    return {"user_id": user_id, "selected_delivery_address_id": address_id, "delivery_address": address}


@app.post("/restaurant-request", include_in_schema=False)
def create_restaurant_request(user_id: str, data: Dict[str, Any] = Body(default_factory=dict)):
    order = create_order_from_cart(user_id, data.get("conversation_id"), data.get("delivery_address", {}))
    if order.get("error"):
        raise HTTPException(status_code=400, detail=order["error"])
    return order
