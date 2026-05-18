import re

from service.database_service import (
    restaurant_collection,
    menu_collection
)

from service.embedding_service import generate_embedding
from service.pinecone_service import index
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

    index.upsert(
        vectors=[
            (
                data["menu_id"],
                embedding,
                {
                    "food_name": data["food_name"],
                    "restaurant_id": data["restaurant_id"]
                }
            )
        ]
    )


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

    results = index.query(
        vector=query_embedding,
        top_k=5,
        include_metadata=True
    )

    return {
        "matches": [
            {
                "id": m["id"],
                "score": m["score"],
                "metadata": m.get("metadata", {})
            }
            for m in results.get("matches", [])
        ]
    }


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