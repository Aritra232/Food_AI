import re
from datetime import datetime
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from bson import ObjectId

# AI Services
from service.ai import chat_with_ai, generate_embedding, detect_intent, extract_preferences

# Memory Services
from service.memory import (
    get_chat_sessions, get_conversation, add_message,
    save_options, get_options, save_selected_item, get_selected_item,
    save_last_blocked_items, get_last_blocked_items, get_last_saved_query,
    save_last_instruction_context, get_last_instruction_context
)

# Data Services
from service.data import (
    get_user_profile, update_favorite_food, update_user_preferences,
    save_onboarding_profile, add_delivery_address, select_delivery_address, record_order_history
)
from service.data.database_service import menu_collection, restaurant_collection, restaurant_requests_collection

# Recommendation Services
from service.recommendation import (
    recommend_foods,
    filter_allergy_safe_foods,
    generate_recommendation_response,
    format_options,
    is_dietary_safe
)

# Business Services
from service.business import (
    add_restaurant, add_menu_item, search_food, semantic_food_search, get_location_based_menus,
    add_to_cart, get_cart, update_item_instruction,
    remove_one_item,
    add_item, remove_item, get_or_create_cart, calculate_total
)

# Vector DB Services
from service.vector_db import upsert_vectors, query_vector

# State Services
from service.state import get_state, set_state

app = FastAPI()


def _build_allergy_disclaimer(blocked_items, allergies):
    if not blocked_items:
        return ""

    blocked_names = []
    for blocked in blocked_items:
        name = blocked.get("food_name")
        if name and name not in blocked_names:
            blocked_names.append(name)

    blocked_text = ", ".join(blocked_names[:3])
    if len(blocked_names) > 3:
        blocked_text += ", and others"

    return (
        f"Safety note: I did not suggest {blocked_text} because they may contain "
        f"your allergy item(s)."
    )


def _is_ingredient_question(message):
    text = (message or "").lower()
    return (
        ("which" in text or "what" in text)
        and ("ingredient" in text or "allergen" in text)
    )


def _is_no_thanks_message(message):
    text = (message or "").strip().lower()
    return text in {
        "no thanks", "no thank you", "no, thanks", "no", "skip",
        "don't want", "do not want", "dont want", "not this",
        "never mind", "nah", "nope", "not that"
    }


def _extract_remove_item_name(message):
    text = (message or "").strip().lower()
    if not text:
        return None

    match = re.search(
        r"(?:remove|delete|take\s+out)\s+(?:one\s+|the\s+|a\s+|an\s+)?(.+?)(?:\s+from\s+my\s+cart|\s+from\s+my\s+order|\s+from\s+the\s+cart|\s+from\s+cart|\s+from\s+it|\.|$)",
        text
    )
    if match:
        item_name = match.group(1).strip()
        item_name = re.sub(r"\s+(please|now|today)$", "", item_name).strip()
        return item_name or None

    return None


def _get_dessert_terms_regex():
    return r"ice|ice cream|kulfi|cake|pie|mousse|cheesecake|gulab|jamun|sundae|pudding|brownie|pastry|gelato|dessert|sweet"


def _attach_restaurant_names(items):
    items = items or []
    if not items:
        return []

    restaurant_ids = []
    seen = set()
    for item in items:
        rid = str(item.get("restaurant_id", "")).strip()
        if not rid or rid in seen:
            continue
        seen.add(rid)
        restaurant_ids.append(rid)

    if not restaurant_ids:
        return items

    cursor = restaurant_collection.find(
        {"restaurant_id": {"$in": restaurant_ids}},
        {"restaurant_id": 1, "name": 1, "restaurant_name": 1}
    )

    name_map = {}
    for doc in cursor:
        rid = str(doc.get("restaurant_id", "")).strip()
        if not rid:
            continue
        name_map[rid] = str(doc.get("name") or doc.get("restaurant_name") or rid).strip()

    enriched = []
    for item in items:
        enriched_item = dict(item)
        rid = str(enriched_item.get("restaurant_id", "")).strip()
        enriched_item["restaurant_name"] = name_map.get(rid, rid or "Unknown")
        enriched.append(enriched_item)

    return enriched


def _normalize_family_text(value):
    return re.sub(r"[^a-z0-9 ]", " ", str(value or "").lower()).strip()


def _get_food_family_keywords(item):
    text = _normalize_family_text(" ".join([
        str(item.get("category", "")),
        str(item.get("food_name", ""))
    ]))

    family_keywords = [
        "burger", "burgers", "biryani", "pizza", "pasta", "noodle", "noodles",
        "rice bowl", "wrap", "sandwich", "shawarma", "kebab", "taco", "tacos",
        "salad", "soup", "fries", "dessert", "cake", "ice cream", "sweet"
    ]

    matched = []
    for keyword in family_keywords:
        if keyword in text:
            matched.append(keyword)

    if not matched:
        category = _normalize_family_text(item.get("category", ""))
        if category:
            matched.append(category)

    return matched


def _is_same_food_family(selected_item, candidate_item):
    selected_keywords = set(_get_food_family_keywords(selected_item))
    candidate_keywords = set(_get_food_family_keywords(candidate_item))

    if not selected_keywords or not candidate_keywords:
        return False

    return bool(selected_keywords.intersection(candidate_keywords))


def _find_desserts_for_restaurant(restaurant_id, profile, exclude_menu_ids=None):
    if not restaurant_id:
        return []

    exclude_menu_ids = exclude_menu_ids or []
    regex_names = _get_dessert_terms_regex()

    cursor = menu_collection.find({
        "restaurant_id": restaurant_id,
        "available": True,
        "menu_id": {"$nin": exclude_menu_ids},
        "$or": [
            {"category": {"$regex": "dessert", "$options": "i"}},
            {"tags": {"$elemMatch": {"$regex": "dessert", "$options": "i"}}},
            {"food_name": {"$regex": regex_names, "$options": "i"}}
        ]
    }).limit(20)

    dessert_items = []
    for item in cursor:
        try:
            if item.get("_id") is not None:
                item["_id"] = str(item["_id"])
        except Exception:
            pass
        dessert_items.append(item)

    dessert_items = [
        item for item in dessert_items
        if is_dietary_safe(item, profile.get("preferences", {}))
    ]

    return dessert_items


def _get_cart_restaurant_id(cart):
    if not cart or not cart.get("items"):
        return None

    restaurant_ids = {
        str(item.get("restaurant_id", "") or "").strip()
        for item in cart.get("items", [])
        if item.get("restaurant_id")
    }

    if len(restaurant_ids) == 1:
        return next(iter(restaurant_ids))

    return None


def _find_global_dessert_recommendations(user_id, relax_dietary=False):
    return recommend_foods(user_id, "dessert", relax_dietary=relax_dietary)


def _find_nearby_dessert_recommendations(lat, lng, profile, relax_dietary=False):
    preferences = profile.get("preferences", {})
    seen_menu_ids = set()
    collected = []

    for query in ["dessert", "sweet", "cake", "ice cream", "pudding", "brownie", "pastry", "fruit dessert"]:
        for item in get_location_based_menus(lat, lng, query):
            menu_id = str(item.get("menu_id", ""))
            if not menu_id or menu_id in seen_menu_ids:
                continue
            seen_menu_ids.add(menu_id)

            if not relax_dietary and not is_dietary_safe(item, preferences):
                continue

            collected.append(item)

    return collected[:5]


def _build_dessert_fallback(user_id, profile, restaurant_id=None, lat=None, lng=None):
    preferences = profile.get("preferences", {})
    allergies = preferences.get("allergies", [])

    if lat is not None and lng is not None:
        dessert_items = _find_nearby_dessert_recommendations(lat, lng, profile)
        if not dessert_items:
            dessert_items = _find_nearby_dessert_recommendations(lat, lng, profile, relax_dietary=True)
    elif restaurant_id:
        dessert_items = _find_desserts_for_restaurant(restaurant_id, profile)
        if not dessert_items:
            dessert_items = _find_global_dessert_recommendations(user_id, relax_dietary=True)
    else:
        dessert_items = _find_global_dessert_recommendations(user_id, relax_dietary=True)

    if not dessert_items:
        return None

    dessert_recommendations = _attach_restaurant_names(dessert_items[:5])
    options_text, options_map = format_options(dessert_recommendations)
    recommendation_batch_id = uuid4().hex

    save_options(
        user_id,
        options_map,
        original_query="dessert_fallback",
        recommendation_batch_id=recommendation_batch_id
    )

    ai_response = generate_recommendation_response(
        "I could not find a matching main dish for your preferences, so here are dessert options instead:",
        dessert_recommendations,
        user_preferences=preferences
    )

    return {
        "options_text": options_text,
        "recommendation_batch_id": recommendation_batch_id,
        "ai_response": ai_response,
        "recommendations": dessert_recommendations,
        "allergies": allergies
    }


def _send_dessert_recommendation(user_id, restaurant_id, chat_session_id, profile, prompt_message, lat=None, lng=None):
    dessert_bundle = _build_dessert_fallback(
        user_id,
        profile,
        restaurant_id=restaurant_id,
        lat=lat,
        lng=lng
    )

    if not dessert_bundle:
        return None

    dessert_recs = dessert_bundle["recommendations"]
    ai_reco = generate_recommendation_response(
        prompt_message,
        dessert_recs,
        user_preferences=profile.get("preferences", {})
    )

    dessert_batch_id = uuid4().hex
    save_last_instruction_context(user_id, restaurant_id)

    try:
        _, options_map = format_options(dessert_recs)
        save_options(
            user_id,
            options_map,
            original_query=f"dessert_fallback:{restaurant_id or 'nearby'}",
            recommendation_batch_id=dessert_batch_id
        )
        save_last_blocked_items(user_id, [])
    except Exception:
        pass

    return {
        "intent": "chat",
        "state": "dessert_suggestion",
        "message": ai_reco["response"],
        "recommendations": dessert_recs,
        "ai_response": ai_reco,
        "restaurant_id": restaurant_id,
        "recommendation_batch_id": dessert_batch_id
    }


def _looks_like_dessert_item(item):
    text = " ".join([
        str(item.get("food_name", "")),
        str(item.get("category", "")),
        " ".join(item.get("tags", []) if isinstance(item.get("tags", []), list) else []),
    ]).lower()
    dessert_terms = [
        "dessert", "ice cream", "icecream", "kulfi", "cake", "pie",
        "mousse", "cheesecake", "gulab jamun", "gulab", "jamun", "sundae",
        "pudding", "sweet", "brownie", "pastry", "gelato", "falooda"
    ]
    return any(term in text for term in dessert_terms)


def _build_blocked_ingredient_reply(message, blocked_items):
    if not blocked_items:
        return "I do not have recent blocked items to explain yet."

    target_items = []
    text = (message or "").lower()

    for item in blocked_items:
        name = str(item.get("food_name", "")).lower()
        if name and name in text:
            target_items.append(item)

    if not target_items:
        target_items = blocked_items

    lines = []
    for item in target_items[:3]:
        name = item.get("food_name", "that item")
        ingredients = item.get("matched_ingredients", [])
        cleaned = []
        seen = set()
        for ingredient in ingredients:
            key = str(ingredient).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(key)

        if cleaned:
            lines.append(f"For {name}, the allergen-related ingredient is: {', '.join(cleaned)}.")

    if not lines:
        return "I could not identify the exact ingredient name, but it was blocked for allergy safety."

    return " ".join(lines)


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
# ORDER WITH AI
@app.post("/order-with-ai")
def order_with_ai(user_id: str, restaurant_id: str = None, lat: float = None, lng: float = None, chat_session_id: str = None):
    profile = get_user_profile(user_id) or {}
    cart = get_cart(user_id) or {"items": []}

    if not restaurant_id:
        restaurant_id = _get_cart_restaurant_id(cart)

    if cart.get("items"):
        item_names = ", ".join([str(item.get("food_name", "item")) for item in cart.get("items", [])])
        order_prompt = (
            f"I found {len(cart.get('items'))} items in your cart: {item_names}. "
            f"Let's confirm this order with AI."
        )
    else:
        order_prompt = (
            "Let's start your AI order confirmation. Tell me what you'd like to order today, "
            "and I will guide you through the recommendation and checkout process."
        )

    add_message(user_id, "assistant", order_prompt, chat_session_id)
    set_state(user_id, "order_confirmation")

    if restaurant_id:
        exclude_menu_ids = [item.get("menu_id") for item in cart.get("items", []) if item.get("menu_id")]
        dessert_items = _find_desserts_for_restaurant(restaurant_id, profile, exclude_menu_ids=exclude_menu_ids)

        if dessert_items:
            dessert_recommendations = _attach_restaurant_names(dessert_items[:5])
            recommendation_batch_id = uuid4().hex
            options_text, options_map = format_options(dessert_recommendations)

            save_options(
                user_id,
                options_map,
                original_query="order_with_ai",
                recommendation_batch_id=recommendation_batch_id
            )
            save_last_instruction_context(user_id, restaurant_id)

            ai_response = generate_recommendation_response(
                "I found these dessert options from the same restaurant. Would you like to add one of them to your order?",
                dessert_recommendations,
                user_preferences=profile.get("preferences", {})
            )

            return {
                "intent": "order_with_ai",
                "state": "order_confirmation",
                "message": order_prompt,
                "ai_response": ai_response,
                "recommendations": dessert_recommendations,
                "restaurant_id": restaurant_id,
                "recommendation_batch_id": recommendation_batch_id,
                "cart": cart
            }

    return {
        "intent": "order_with_ai",
        "state": "order_confirmation",
        "message": order_prompt,
        "cart": cart
    }


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
def get_chat_history(user_id: str, chat_session_id: str = None):
    """Get conversation history for a user"""
    sessions = get_chat_sessions(user_id)
    if not chat_session_id and sessions:
        chat_session_id = sessions[0].get("chat_session_id")

    history = get_conversation(user_id, chat_session_id) if chat_session_id else []
    profile = get_user_profile(user_id)
    
    return {
        "user_id": user_id,
        "chat_session_id": chat_session_id,
        "chat_history": history,
        "chat_sessions": sessions,
        "user_profile": profile
    }


@app.get("/user-profile")
def get_profile_info(user_id: str):
    """Get user profile with preferences"""
    profile = get_user_profile(user_id)
    return profile


@app.post("/profile/onboarding")
def save_profile_onboarding(user_id: str, data: dict):
    """Save onboarding preferences and address to the user profile."""
    return save_onboarding_profile(user_id, data)


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


@app.get("/food-items")
def list_food_items(limit: int = 12):
    cursor = menu_collection.find({"available": True}).limit(limit)
    items = []
    for item in cursor:
        if item.get("_id") is not None:
            item["_id"] = str(item["_id"])
        items.append(item)

    return _attach_restaurant_names(items)


@app.get("/semantic-search")
def semantic_search(food: str):
    return semantic_food_search(food)


# -------------------------
# RECOMMENDATION (raw)
# -------------------------
@app.get("/recommend-food")
def recommend(user_id: str, food: str, lat: float = None, lng: float = None):
    recommendations = recommend_foods(user_id, food, lat=lat, lng=lng)
    return _attach_restaurant_names(recommendations)


# -------------------------
# AI RECOMMENDATION
# -------------------------
@app.get("/ai-recommend")
def ai_recommend(user_id: str, food: str, lat: float = None, lng: float = None):

    recommendations = recommend_foods(user_id, food, lat=lat, lng=lng)
    recommendations = _attach_restaurant_names(recommendations)

    user_profile = get_user_profile(user_id)
    preferences = user_profile.get("preferences", {})

    ai_response = generate_recommendation_response(
        food,
        recommendations,
        user_preferences=preferences
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
def chat(user_id: str, message: str, lat: float = None, lng: float = None, chat_session_id: str = None, recommendation_batch_id: str = None):

    intent = detect_intent(message)
    state = get_state(user_id)
    profile = get_user_profile(user_id)
    allergies = profile.get("preferences", {}).get("allergies", [])

    # -------------------------
    # CASE 4: NORMAL CHAT
    # -------------------------
    if intent == "chat":
        # ingredient follow-up: user asking which ingredient/allergen
        if _is_ingredient_question(message):
            blocked_items = get_last_blocked_items(user_id)
            ingredient_reply = _build_blocked_ingredient_reply(message, blocked_items)
            add_message(user_id, "user", message, chat_session_id)
            add_message(user_id, "assistant", ingredient_reply, chat_session_id)
            set_state(user_id, "chat")
            return {
                "intent": intent,
                "state": "chat",
                "message": ingredient_reply
            }

        # dessert follow-up: if the user rejects the current recommendation in cart state,
        # fall back to dessert recommendations first. Only show the instruction card after
        # dessert suggestions have been offered.
        if _is_no_thanks_message(message):
            restaurant_id = get_last_instruction_context(user_id)
            add_message(user_id, "user", message, chat_session_id)

            if state == "dessert_suggestion" and restaurant_id:
                prompt_msg = (
                    "Add any special requests or dietary notes below to customize your order!"
                )
                add_message(user_id, "assistant", prompt_msg, chat_session_id)
                set_state(user_id, "instruction_prompt")

                return {
                    "intent": intent,
                    "state": "instruction_prompt",
                    "message": prompt_msg,
                    "show_instruction_card": True,
                    "restaurant_id": restaurant_id
                }

            if state == "cart" and restaurant_id:
                dessert_result = _send_dessert_recommendation(
                    user_id,
                    restaurant_id,
                    chat_session_id,
                    profile,
                    "I understand you would rather skip the previous suggestions. Here are nearby dessert options:",
                    lat=lat,
                    lng=lng
                )
                if dessert_result:
                    add_message(user_id, "assistant", dessert_result["message"], chat_session_id)
                    set_state(user_id, "dessert_suggestion")
                    return dessert_result

        # regular chat: get AI reply and detect any extracted preference updates
        ai_result = chat_with_ai(user_id, message, chat_session_id=chat_session_id)
        ai_response = ai_result.get("response") if isinstance(ai_result, dict) else ai_result
        extracted = ai_result.get("extracted_preferences") if isinstance(ai_result, dict) else {}

        set_state(user_id, "chat")

        return {
            "intent": intent,
            "state": "chat",
            "message": ai_response
        }


    # -------------------------
    # CASE 1.5: CART MODIFICATION
    if intent == "modify":
        remove_description = _extract_remove_item_name(message)
        cart = get_cart(user_id) or {"items": []}
        removed_cart = None

        if remove_description:
            removed_cart = remove_one_item(user_id, food_name=remove_description)

        if not removed_cart and remove_description is None and cart.get("items"):
            # If user only asked to remove one and no item name was provided,
            # infer the most likely item from cart state.
            candidate_item = None
            items = cart.get("items", [])

            # Prefer a single distinct item
            if len(items) == 1:
                candidate_item = items[0]
            else:
                # First prefer an item with quantity > 1
                for item in items:
                    if int(item.get("quantity", 1) or 1) > 1:
                        candidate_item = item
                        break

                # Next prefer a duplicated menu_id entry when there are repeated items
                if candidate_item is None:
                    counts = {}
                    for item in items:
                        mid = item.get("menu_id") or item.get("food_name")
                        if not mid:
                            continue
                        counts[mid] = counts.get(mid, 0) + 1

                    for item in items:
                        mid = item.get("menu_id") or item.get("food_name")
                        if mid and counts.get(mid, 0) > 1:
                            candidate_item = item
                            break

            if candidate_item is not None:
                removed_cart = remove_one_item(
                    user_id,
                    menu_id=candidate_item.get("menu_id"),
                    food_name=candidate_item.get("food_name")
                )
                remove_description = candidate_item.get("food_name") or candidate_item.get("menu_id")

        if removed_cart:
            response = f"Removed one {remove_description} from your cart."
            add_message(user_id, "user", message, chat_session_id)
            add_message(user_id, "assistant", response, chat_session_id)
            set_state(user_id, "cart")
            return {
                "intent": intent,
                "state": "cart",
                "message": response,
                "cart": removed_cart
            }

        error_msg = "I could not find that item in your cart to remove. Please tell me the exact item name."
        add_message(user_id, "assistant", error_msg, chat_session_id)
        set_state(user_id, "cart")
        return {
            "intent": intent,
            "state": "cart",
            "message": error_msg,
            "cart": cart
        }


    # Save user message to conversation history for order/select/checkout flow
    add_message(user_id, "user", message, chat_session_id)

    # Extract preferences from user message
    extracted_prefs = extract_preferences(
        message,
        conversation_history=get_conversation(user_id, chat_session_id),
        existing_allergies=profile.get("preferences", {}).get("allergies", [])
    )
    if extracted_prefs:
        update_user_preferences(user_id, extracted_prefs, source_message=message)

    # -------------------------
    # CASE 1: ORDER FLOW
    # -------------------------
    if intent == "order":

        blocked_items = []
        save_last_blocked_items(user_id, [])

        if lat and lng:

            recommendations = get_location_based_menus(
                lat,
                lng,
                message
            )

            recommendations, blocked_items = filter_allergy_safe_foods(
                recommendations,
                allergies
            )
            recommendations = [item for item in (recommendations or []) if is_dietary_safe(item, profile.get("preferences", {}))]

        else:

            recommendations = recommend_foods(
                user_id,
                message
            )
            recommendations = _attach_restaurant_names(recommendations)

        if not recommendations or len(recommendations) == 0:

            if lat and lng:
                recommendations = recommend_foods(
                    user_id,
                    message,
                    lat=lat,
                    lng=lng
                )
            else:
                # Fallback to global recommendation search so Pinecone + Mongo can still return options
                recommendations = recommend_foods(
                    user_id,
                    message
                )
            recommendations = _attach_restaurant_names(recommendations)

            # Try to include blocked list for disclaimer context when coming from location search.
            if not blocked_items and lat and lng:
                location_recommendations = get_location_based_menus(lat, lng, message)
                _, blocked_items = filter_allergy_safe_foods(location_recommendations, allergies)

        recommendations = _attach_restaurant_names(recommendations)

        if blocked_items:
            save_last_blocked_items(user_id, blocked_items)

        if not recommendations or len(recommendations) == 0:

            # If no personalized food match is found, business policy: offer dessert instead.
            dessert_bundle = _build_dessert_fallback(user_id, profile, lat=lat, lng=lng)
            if dessert_bundle:
                disclaimer = _build_allergy_disclaimer(blocked_items, allergies)
                if disclaimer:
                    dessert_bundle["ai_response"]["response"] = f"{dessert_bundle['ai_response']['response']}\n\n{disclaimer}"

                add_message(user_id, "assistant", dessert_bundle["ai_response"]["response"], chat_session_id)

                set_state(user_id, "dessert_suggestion")

                return {
                    "intent": intent,
                    "state": "dessert_suggestion",
                    "options": dessert_bundle["options_text"],
                    "ai_response": dessert_bundle["ai_response"],
                    "recommendations": dessert_bundle["recommendations"],
                    "recommendation_batch_id": dessert_bundle["recommendation_batch_id"]
                }

            error_msg = "I couldn't find a matching main dish right now, so I can try dessert options instead."
            disclaimer = _build_allergy_disclaimer(blocked_items, allergies)
            if disclaimer:
                error_msg = f"{error_msg} {disclaimer}"
            add_message(user_id, "assistant", error_msg, chat_session_id)

            return {
                "intent": intent,
                "state": "browsing",
                "message": error_msg
            }
        # CREATE OPTIONS
        options_text, options_map = format_options(recommendations)

        recommendation_batch_id = uuid4().hex

        # SAVE OPTIONS (store original query to allow auto-refresh later)
        save_options(
            user_id,
            options_map,
            original_query=message,
            recommendation_batch_id=recommendation_batch_id
        )

        # AI RESPONSE
        ai_response = generate_recommendation_response(
            message,
            recommendations,
            user_preferences=profile.get("preferences", {})
        )

        disclaimer = _build_allergy_disclaimer(blocked_items, allergies)
        if disclaimer:
            ai_response["response"] = f"{ai_response['response']}\n\n{disclaimer}"

        # Save AI response to conversation
        add_message(user_id, "assistant", ai_response["response"], chat_session_id)

        set_state(
            user_id,
            "browsing"
        )

        return {
            "intent": intent,
            "state": "browsing",
            "options": options_text,
            "ai_response": ai_response,
            "recommendations": recommendations,
            "recommendation_batch_id": recommendation_batch_id
        }

    # -------------------------
    # CASE 2: OPTION SELECT
    # -------------------------
    if intent == "select":

        options = get_options(user_id, recommendation_batch_id)

        option_key, quantity = parse_option_selection(message)
        selected = options.get(option_key)

        if not selected:

            error_msg = "Invalid option selected"
            add_message(user_id, "assistant", error_msg, chat_session_id)

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
            add_message(user_id, "assistant", error_msg, chat_session_id)

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
        add_message(user_id, "assistant", confirm_msg, chat_session_id)

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

                # If the selected item itself is a dessert, do not show more dessert recommendations.
                # Open the instruction card immediately instead.
                if _looks_like_dessert_item(selected_item):
                    restaurant_id = selected_item.get("restaurant_id")
                    save_last_instruction_context(user_id, restaurant_id)

                    add_message(user_id, "assistant", success_msg, chat_session_id)

                    return {
                        "intent": intent,
                        "state": "cart",
                        "message": success_msg,
                        "cart": cart,
                        "show_instruction_card": True,
                        "restaurant_id": restaurant_id  
                    }

                # After adding to cart, first try to suggest other available categories from the same restaurant
                try:
                    restaurant_id = selected_item.get("restaurant_id")
                    selected_category = (selected_item.get("category") or "").strip()

                    other_cursor = menu_collection.find({
                        "restaurant_id": restaurant_id,
                        "available": True,
                        "menu_id": {"$ne": selected_item.get("menu_id")},
                        "$or": [
                            {"category": {"$ne": selected_category}},
                            {"category": {"$exists": False}}
                        ]
                    }).limit(15)

                    other_items = []
                    for d in other_cursor:
                        try:
                            if d.get("_id") is not None:
                                d["_id"] = str(d["_id"])
                        except Exception:
                            pass
                        other_items.append(d)

                    other_items = [item for item in other_items if is_dietary_safe(item, profile.get("preferences", {}))]
                    other_items = [item for item in other_items if not _is_same_food_family(selected_item, item)]
                    non_dessert_items = [item for item in other_items if not _looks_like_dessert_item(item)]
                    if non_dessert_items:
                        other_items = non_dessert_items
                    else:
                        other_items = []

                    if other_items:
                        other_recs = _attach_restaurant_names(other_items[:5])
                        ai_reco = generate_recommendation_response(
                            "I also found these other dishes from different categories in the same restaurant:",
                            other_recs,
                            user_preferences=profile.get("preferences", {})
                        )

                        other_batch_id = uuid4().hex
                        save_last_instruction_context(user_id, restaurant_id)

                        try:
                            _, options_map = format_options(other_recs)
                            save_options(
                                user_id,
                                options_map,
                                original_query=f"other_category_suggestion:{restaurant_id}",
                                recommendation_batch_id=other_batch_id
                            )
                            save_last_blocked_items(user_id, [])
                        except Exception:
                            pass

                        full_msg = f"{success_msg}\n\n{ai_reco['response']}"
                        add_message(user_id, "assistant", full_msg, chat_session_id)

                        return {
                            "intent": intent,
                            "state": "cart",
                            "message": full_msg,
                            "cart": cart,
                            "recommendations": other_recs,
                            "ai_response": ai_reco,
                            "restaurant_id": restaurant_id,
                            "recommendation_batch_id": other_batch_id
                        }

                    dessert_bundle = _build_dessert_fallback(
                        user_id,
                        profile,
                        restaurant_id=restaurant_id,
                        lat=lat,
                        lng=lng
                    )

                    if dessert_bundle:
                        dessert_recs = dessert_bundle["recommendations"]
                        ai_reco = generate_recommendation_response(
                            "Here are nearby dessert options based on your location:",
                            dessert_recs,
                            user_preferences=profile.get("preferences", {})
                        )

                        dessert_batch_id = uuid4().hex
                        save_last_instruction_context(user_id, restaurant_id)

                        try:
                            _, options_map = format_options(dessert_recs)
                            save_options(
                                user_id,
                                options_map,
                                original_query=f"dessert_suggestion:{restaurant_id}",
                                recommendation_batch_id=dessert_batch_id
                            )
                            save_last_blocked_items(user_id, [])
                        except Exception:
                            pass

                        full_msg = f"{success_msg}\n\n{ai_reco['response']}"
                        add_message(user_id, "assistant", full_msg, chat_session_id)

                        return {
                            "intent": intent,
                            "state": "dessert_suggestion",
                            "message": full_msg,
                            "cart": cart,
                            "recommendations": dessert_recs,
                            "ai_response": ai_reco,
                            "restaurant_id": restaurant_id,
                            "recommendation_batch_id": dessert_batch_id
                        }

                except Exception:
                    # fallback: still return success message
                    pass

                add_message(user_id, "assistant", success_msg, chat_session_id)

                return {
                    "intent": intent,
                    "state": "cart",
                    "message": success_msg,
                    "cart": cart
                }

            else:

                error_msg = "No item selected to confirm"
                add_message(user_id, "assistant", error_msg, chat_session_id)

                return {
                    "intent": intent,
                    "state": "checkout",
                    "message": error_msg
                }

        else:

            set_state(user_id, "checkout")

            confirm_msg = "Please say 'yes' to confirm and add the selected item to cart"
            add_message(user_id, "assistant", confirm_msg, chat_session_id)

            return {
                "intent": intent,
                "state": "checkout",
                "message": confirm_msg
            }

    # -------------------------
    # FALLBACK CHAT
    # -------------------------
    default_msg = "I am here to help you find food or place an order."
    add_message(user_id, "assistant", default_msg, chat_session_id)

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


@app.post("/cart/add-item")
def add_cart_item(user_id: str, data: dict):
    menu_id = data.get("menu_id")
    quantity = int(data.get("quantity", 1) or 1)

    if not menu_id:
        raise HTTPException(status_code=400, detail="menu_id is required")

    menu_item = menu_collection.find_one({"menu_id": menu_id, "available": True})
    if not menu_item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    cart_item = {
        "menu_id": menu_item.get("menu_id"),
        "food_name": menu_item.get("food_name"),
        "price": float(menu_item.get("price", 0) or 0),
        "quantity": quantity,
        "restaurant_id": menu_item.get("restaurant_id"),
        "category": menu_item.get("category", "")
    }

    add_to_cart(user_id, cart_item)
    cart = get_cart(user_id)

    return {
        "message": "Item added to cart",
        "cart": cart
    }


@app.post("/instruction")
def add_instruction(user_id: str, instruction: str, restaurant_id: str = None, chat_session_id: str = None):
    """Save a cart-level special instruction for the user's cart.

    This endpoint always stores instructions at the cart document level (`cart.special_instructions`).
    """
    from service.business import set_cart_instruction

    if restaurant_id is None:
        restaurant_id = get_last_instruction_context(user_id)

    set_cart_instruction(user_id, instruction, restaurant_id=restaurant_id)
    add_message(user_id, "assistant", "Saved cart-level instruction.", chat_session_id)
    return {"status": "ok", "target": "cart_level"}


@app.post("/profile/address")
def upsert_profile_address(user_id: str, address: dict = None, address_id: str = None):
    """Add a new delivery address or select an existing one."""
    if address_id:
        return select_delivery_address(user_id, address_id)

    if not address:
        raise HTTPException(status_code=400, detail="Address data is required")

    return add_delivery_address(user_id, address)


def _build_order_summary(cart):
    items = cart.get("items", []) if cart else []
    subtotal = sum(float(item.get("price", 0)) * int(item.get("quantity", 1)) for item in items)
    delivery_fee = 12
    total = subtotal + delivery_fee

    return {
        "items": items,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": total
    }


@app.post("/restaurant-request")
def create_restaurant_request(user_id: str, data: dict = None):
    """Create a restaurant request with pending status."""
    profile = get_user_profile(user_id)
    cart = get_cart(user_id) or {"user_id": user_id, "items": []}
    summary = _build_order_summary(cart)
    delivery_address = profile.get("delivery_address") or {}

    restaurant_ids = []
    for item in summary["items"]:
        restaurant_id = item.get("restaurant_id")
        if restaurant_id and restaurant_id not in restaurant_ids:
            restaurant_ids.append(restaurant_id)

    restaurant_id = restaurant_ids[0] if restaurant_ids else None
    if not restaurant_id:
        raise HTTPException(status_code=400, detail="No restaurant found for the current cart")

    request_doc = {
        "user_id": user_id,
        "restaurant_id": restaurant_id,
        "restaurant_ids": restaurant_ids,
        "status": "pending",
        "cart": cart,
        "summary": summary,
        "delivery_address": delivery_address,
        "instruction": (data or {}).get("instruction", ""),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    inserted = restaurant_requests_collection.insert_one(request_doc)
    request_doc["_id"] = str(inserted.inserted_id)
    return request_doc


@app.get("/restaurant-requests")
def list_restaurant_requests(user_id: str = None, limit: int = 50):
    """List restaurant requests. If `user_id` is provided, filter by that user.

    This endpoint helps Swagger/UI discover valid `request_id` values.
    """
    query = {}
    if user_id:
        query["user_id"] = user_id

    cursor = restaurant_requests_collection.find(query).sort("created_at", -1).limit(int(limit or 50))
    results = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)

    return {"count": len(results), "requests": results}


@app.patch("/restaurant-request/{request_id}")
def update_restaurant_request_status(request_id: str, status: str):
    """Update a restaurant request status to pending, accept, or reject."""
    if status not in {"pending", "accept", "reject"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    try:
        object_id = ObjectId(request_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid request id") from exc

    result = restaurant_requests_collection.update_one(
        {"_id": object_id},
        {
            "$set": {
                "status": status,
                "updated_at": datetime.utcnow()
            }
        }
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Restaurant request not found")

    updated = restaurant_requests_collection.find_one({"_id": object_id})
    updated["_id"] = str(updated["_id"])
    return updated
