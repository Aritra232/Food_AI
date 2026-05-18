import re
import re
from fastapi import FastAPI

# Services
from service.openai_service import chat_with_ai

from service.profile_service import (
    get_user_profile,
    update_favorite_food,
    update_user_preferences,
    record_order_history
)

from service.restaurant_service import (
    add_restaurant,
    add_menu_item,
    search_food,
    semantic_food_search
)

from service.recommendation_service import recommend_foods

from service.recommendation_response_service import (
    generate_recommendation_response,
    format_options
)

from service.embedding_service import generate_embedding
from service.pinecone_service import upsert_vectors, query_vector

from service.intent_service import detect_intent

from service.state_service import get_state, set_state

from service.memory_service import get_conversation, add_message

from service.preference_extraction_service import extract_preferences

from service.option_memory_service import (
    save_options,
    get_options,
    save_selected_item,
    get_selected_item
)

from service.cart_service import add_to_cart, get_cart

from service.database_service import menu_collection, restaurant_collection
from service.restaurant_service import get_location_based_menus
from bson import ObjectId

from service.order_service import (
    add_item,
    remove_item,
    get_or_create_cart
)
from service.order_service import calculate_total

app = FastAPI()


def parse_option_selection(message: str):
    normalized = message.strip().upper()

    option_match = re.search(r"\b([A-E])\b", normalized)
    if option_match:
        option_key = option_match.group(1)
    else:
        option_key = normalized.replace("OPTION ", "").strip().split()[0] if normalized else ""

    quantity = 1
    quantity_match = re.search(r"\b(?:x|qty|quantity)[:= ]*(\d+)\b", message.lower())
    if quantity_match:
        quantity = int(quantity_match.group(1))
    else:
        trailing_numbers = re.findall(r"\b(\d+)\b", normalized)
        if trailing_numbers:
            quantity = int(trailing_numbers[-1])

    return option_key, max(1, quantity)


# -------------------------
# HOME
# -------------------------
@app.get("/")
def home():
    return {"message": "Food AI Agent Running"}


# -------------------------
# PROFILE
# -------------------------
@app.get("/profile")
def profile(user_id: str):
    return get_user_profile(user_id)


@app.get("/favorite-food")
def favorite_food(user_id: str, food: str):
    update_favorite_food(user_id, food)
    return {"message": f"{food} added"}


@app.get("/chat-history")
def get_chat_history(user_id: str):
    """Get conversation history for a user"""
    history = get_conversation(user_id)
    profile = get_user_profile(user_id)
    
    return {
        "user_id": user_id,
        "chat_history": history,
        "user_profile": profile
    }


@app.get("/user-profile")
def get_profile_info(user_id: str):
    """Get user profile with preferences"""
    profile = get_user_profile(user_id)
    return profile


# -------------------------
# RESTAURANT APIs
# -------------------------
@app.post("/add-restaurant")
def create_restaurant(data: dict):
    add_restaurant(data)
    return {"message": "Restaurant added"}


@app.post("/add-menu")
def create_menu(data: dict):
    add_menu_item(data)
    return {"message": "Menu item added"}


# -------------------------
# SEARCH
# -------------------------
@app.get("/search-food")
def food_search(food: str):

    results = search_food(food)

    formatted = []
    for item in results:
        item["_id"] = str(item["_id"])
        formatted.append(item)

    return formatted


@app.get("/semantic-search")
def semantic_search(food: str):
    return semantic_food_search(food)


# -------------------------
# RECOMMENDATION (raw)
# -------------------------
@app.get("/recommend-food")
def recommend(user_id: str, food: str):
    return recommend_foods(user_id, food)


# -------------------------
# AI RECOMMENDATION
# -------------------------
@app.get("/ai-recommend")
def ai_recommend(user_id: str, food: str):

    recommendations = recommend_foods(user_id, food)

    ai_response = generate_recommendation_response(
        food,
        recommendations
    )

    return {
        "user_id": user_id,
        "query": food,
        "recommendations": recommendations,
        "ai_response": ai_response
    }



@app.post("/sync-pinecone")
def sync_pinecone():
    """Sync menus and restaurants into Pinecone index."""
    # load latest menus and restaurants from Mongo
    menus = list(menu_collection.find({}))
    vectors = []

    for m in menus:
        _id = str(m.get("_id"))
        text = f"{m.get('food_name', '')} {m.get('description', '')} {' '.join(m.get('tags', []))} {m.get('ingredients', '')}"
        vec = generate_embedding(text)
        metadata = {
            "menu_id": m.get('menu_id'),
            "restaurant_id": m.get('restaurant_id'),
            "price": m.get('price'),
            "cuisine": m.get('cuisine'),
            "available": m.get('available', True),
            "tags": m.get('tags', [])
        }
        vectors.append((_id, vec, metadata))

    # upsert menus
    upsert_vectors(vectors)

    # restaurants
    restaurants = list(restaurant_collection.find({}))
    rvecs = []
    for r in restaurants:
        _id = str(r.get("_id"))
        text = f"{r.get('name', '')} {r.get('description', '')} {' '.join(r.get('cuisines', []))}"
        vec = generate_embedding(text)
        location = r.get('location') or {}
        location_lat = None
        location_lng = None

        if isinstance(location, dict):
            location_lat = location.get('lat') or location.get('latitude')
            location_lng = location.get('lng') or location.get('longitude')

        metadata = {
            "restaurant_id": r.get('restaurant_id'),
            "name": r.get('name'),
            "cuisines": r.get('cuisines', []),
            "location_lat": location_lat,
            "location_lng": location_lng
        }
        rvecs.append((_id, vec, metadata))

    upsert_vectors(rvecs)

    return {"message": "synced", "menus_indexed": len(vectors), "restaurants_indexed": len(rvecs)}


@app.get("/hybrid-search")
def hybrid_search(query: str, top_k: int = 5, cuisine: str = None, max_price: float = None):
    """Run a hybrid vector + metadata search and return Mongo documents.

    Filters: `cuisine`, `max_price` applied via metadata filters.
    """
    embed = generate_embedding(query)

    # Build metadata filter
    filt = {}
    if cuisine:
        filt["cuisine"] = {"$eq": cuisine}
    if max_price is not None:
        # pinecone supports numeric metadata filters; here we use <=
        filt["price"] = {"$lte": float(max_price)}

    res = query_vector(embed, top_k=top_k, filter=filt)

    # Extract ids from results
    matches = []
    try:
        for match in (res.matches if hasattr(res, 'matches') else res['matches']):
            mid = match.id if hasattr(match, 'id') else match['id']
            meta = match.metadata if hasattr(match, 'metadata') else match.get('metadata', {})
            matches.append({"id": mid, "score": getattr(match, 'score', match.get('score')), "metadata": meta})
    except Exception:
        # fallback for other response shapes
        for m in res:
            matches.append(m)

    # Fetch authoritative records from Mongo for menus
    menu_ids = [m['id'] for m in matches]
    docs = []
    if menu_ids:
        from bson import ObjectId
        for mid in menu_ids:
            try:
                doc = menu_collection.find_one({"_id": ObjectId(mid)})
                if doc:
                    doc['_id'] = str(doc['_id'])
                    docs.append(doc)
            except Exception:
                # maybe it's a restaurant id
                try:
                    doc = restaurant_collection.find_one({"_id": ObjectId(mid)})
                    if doc:
                        doc['_id'] = str(doc['_id'])
                        docs.append(doc)
                except Exception:
                    pass

    return {"query": query, "matches": matches, "documents": docs}




# -------------------------
# MAIN CHAT ORCHESTRATOR
# -------------------------


@app.post("/chat")
def chat(user_id: str, message: str, lat: float = None, lng: float = None):

    intent = detect_intent(message)
    state = get_state(user_id)
    profile = get_user_profile(user_id)

    # -------------------------
    # CASE 4: NORMAL CHAT
    # -------------------------
    if intent == "chat":
        ai_response = chat_with_ai(user_id, message)
        set_state(user_id, "chat")
        return {
            "intent": intent,
            "state": "chat",
            "message": ai_response
        }

    # Save user message to conversation history for order/select/checkout flow
    add_message(user_id, "user", message)

    # Extract preferences from user message
    extracted_prefs = extract_preferences(
        message,
        conversation_history=get_conversation(user_id),
        existing_allergies=profile.get("preferences", {}).get("allergies", [])
    )
    if extracted_prefs:
        update_user_preferences(user_id, extracted_prefs)

    # -------------------------
    # CASE 1: ORDER FLOW
    # -------------------------
    if intent == "order":

        if lat and lng:

            recommendations = get_location_based_menus(
                lat,
                lng,
                message
            )

        else:

            recommendations = recommend_foods(
                user_id,
                message
            )

        if not recommendations or len(recommendations) == 0:

            # Fallback to global recommendation search so Pinecone + Mongo can still return options
            recommendations = recommend_foods(
                user_id,
                message
            )

        if not recommendations or len(recommendations) == 0:

            error_msg = "Sorry, no matching food is available in nearby restaurants."
            add_message(user_id, "assistant", error_msg)

            return {
                "intent": intent,
                "state": "browsing",
                "message": error_msg
            }
        # CREATE OPTIONS
        options_text, options_map = format_options(
            recommendations
        )

        # SAVE OPTIONS
        save_options(
            user_id,
            options_map
        )

        # AI RESPONSE
        ai_response = generate_recommendation_response(
            message,
            recommendations
        )

        # Save AI response to conversation
        add_message(user_id, "assistant", ai_response["response"])

        set_state(
            user_id,
            "browsing"
        )

        return {
            "intent": intent,
            "state": "browsing",
            "options": options_text,
            "ai_response": ai_response,
            "recommendations": recommendations
        }

    # -------------------------
    # CASE 2: OPTION SELECT
    # -------------------------
    if intent == "select":

        options = get_options(user_id)

        option_key, quantity = parse_option_selection(message)
        selected = options.get(option_key)

        if not selected:

            error_msg = "Invalid option selected"
            add_message(user_id, "assistant", error_msg)

            return {
                "error": error_msg
            }

        try:

            menu_item = menu_collection.find_one({
                "_id": ObjectId(selected["_id"])
            })

        except Exception:

            menu_item = None

        if not menu_item:

            error_msg = "Selected menu item not found"
            add_message(user_id, "assistant", error_msg)

            return {
                "error": error_msg
            }

        cart_item = {
            "menu_id": menu_item["menu_id"],
            "food_name": menu_item["food_name"],
            "price": menu_item["price"],
            "quantity": quantity,
            "restaurant_id": menu_item["restaurant_id"]
        }

        save_selected_item(user_id, cart_item)

        set_state(user_id, "selected")

        confirm_msg = "Item selected. Say 'yes' or 'confirm' to add to cart."
        add_message(user_id, "assistant", confirm_msg)

        return {
            "intent": intent,
            "state": "selected",
            "message": confirm_msg
        }

    # -------------------------
    # CASE 3: CHECKOUT
    # -------------------------
    if intent == "checkout":

        if "yes" in message.lower() or "confirm" in message.lower() or "okay" in message.lower():

            selected_item = get_selected_item(user_id)

            if selected_item:

                add_to_cart(user_id, selected_item)
                record_order_history(user_id, selected_item)
                save_selected_item(user_id, None)

                set_state(user_id, "cart")

                cart = get_cart(user_id)

                success_msg = "Item added to cart successfully"
                add_message(user_id, "assistant", success_msg)

                return {
                    "intent": intent,
                    "state": "cart",
                    "message": success_msg,
                    "cart": cart
                }

            else:

                error_msg = "No item selected to confirm"
                add_message(user_id, "assistant", error_msg)

                return {
                    "intent": intent,
                    "state": "checkout",
                    "message": error_msg
                }

        else:

            set_state(user_id, "checkout")

            confirm_msg = "Please say 'yes' to confirm and add the selected item to cart"
            add_message(user_id, "assistant", confirm_msg)

            return {
                "intent": intent,
                "state": "checkout",
                "message": confirm_msg
            }

    # -------------------------
    # FALLBACK CHAT
    # -------------------------
    default_msg = "I am here to help you find food or place an order."
    add_message(user_id, "assistant", default_msg)

    return {
        "intent": intent,
        "state": state,
        "message": default_msg
    }




@app.get("/cart")
def view_cart(user_id: str):

    cart = get_cart(user_id)

    if not cart:
        cart = {"user_id": user_id, "items": []}

    total_price = sum(item["price"] * item.get("quantity", 1) for item in cart.get("items", []))

    if "_id" in cart:
        cart["_id"] = str(cart["_id"])

    return {
        "cart": cart,
        "total_price": total_price
    }
