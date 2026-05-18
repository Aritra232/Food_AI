import re

from service.database_service import (
    restaurant_collection,
    menu_collection
)

from service.embedding_service import generate_embedding
from service.pinecone_service import upsert_vectors, query_vector
from service.location_service import get_nearby_restaurants


# -------------------------
# ADD RESTAURANT
# -------------------------
def add_restaurant(data):

    # ensure lat/lng are float if provided
    if "lat" in data:
        data["lat"] = float(data["lat"])
    if "lng" in data:
        data["lng"] = float(data["lng"])

    # also support a nested location object and mirror values for compatibility
    location = data.get("location")
    if isinstance(location, dict):
        if "lat" in location and "lat" not in data:
            data["lat"] = float(location["lat"])
        if "lng" in location and "lng" not in data:
            data["lng"] = float(location["lng"])

    if "lat" in data and "lng" in data and "location" not in data:
        data["location"] = {
            "lat": data["lat"],
            "lng": data["lng"]
        }

    restaurant_collection.insert_one(data)


# -------------------------
# ADD MENU ITEM + VECTOR STORE
# -------------------------
def add_menu_item(data):

    menu_collection.insert_one(data)

    searchable_text = f"""
    {data.get('food_name', '')}
    {data.get('category', '')}
    {data.get('spicy_level', '')}
    {' '.join(data.get('tags', []))}
    {' '.join(data.get('ingredients', []))}
    """

    embedding = generate_embedding(searchable_text)

    upsert_vectors([
        (
            data["menu_id"],
            embedding,
            {
                "food_name": data["food_name"],
                "restaurant_id": data["restaurant_id"]
            }
        )
    ])


# -------------------------
# KEYWORD SEARCH
# -------------------------
def search_food(food_name):

    return list(menu_collection.find({
        "food_name": {
            "$regex": food_name,
            "$options": "i"
        },
        "available": True
    }))


# -------------------------
# SEMANTIC SEARCH (PINECONE)
# -------------------------
def semantic_food_search(query):

    query_embedding = generate_embedding(query)

    res = query_vector(query_embedding, top_k=5, filter=None)

    matches = []
    try:
        candidate_list = res.matches if hasattr(res, 'matches') else res.get('matches', [])
    except Exception:
        candidate_list = res.get('matches', []) if isinstance(res, dict) else []

    for m in candidate_list:
        mid = m.id if hasattr(m, 'id') else m.get('id')
        score = getattr(m, 'score', m.get('score'))
        meta = m.metadata if hasattr(m, 'metadata') else m.get('metadata', {})
        matches.append({"id": mid, "score": score, "metadata": meta})

    return {"matches": matches}


# -------------------------
# HYBRID SEARCH
# -------------------------
def hybrid_food_search(query):

    keyword_results = search_food(query)
    semantic_results = semantic_food_search(query)

    combined = []
    seen = set()

    # keyword first
    for item in keyword_results:
        item["_id"] = str(item["_id"])
        combined.append(item)
        seen.add(item["menu_id"])

    # semantic
    for match in semantic_results["matches"]:

        if match["id"] in seen:
            continue

        menu_item = menu_collection.find_one({
            "menu_id": match["id"]
        })

        if menu_item:
            menu_item["_id"] = str(menu_item["_id"])
            menu_item["semantic_score"] = match["score"]
            combined.append(menu_item)

    return combined


# -------------------------
# LOCATION-BASED SEARCH
# -------------------------
def get_location_based_menus(user_lat, user_lng, query):

    nearby_restaurants = get_nearby_restaurants(user_lat, user_lng)

    if not nearby_restaurants:
        return []

    restaurant_ids = [
        r["restaurant_id"] for r in nearby_restaurants
    ]

    menus = menu_collection.find({
        "restaurant_id": {"$in": restaurant_ids},
        "available": True
    })

    results = []

    query_lower = query.lower()
    query_terms = [
        term
        for term in re.findall(r"\w+", query_lower)
        if len(term) > 2
    ]

    for item in menus:

        food_name_lower = item.get("food_name", "").lower()

        if (
            query_lower in food_name_lower or
            any(term in food_name_lower for term in query_terms)
        ):

            item["_id"] = str(item["_id"])
            results.append(item)

    return results