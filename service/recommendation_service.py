from service.profile_service import get_user_profile

from service.restaurant_service import hybrid_food_search


def calculate_score(menu_item, preferences):

    score = 0

    favorite_foods = preferences.get(
        "favorite_foods",
        []
    )

    disliked_foods = preferences.get(
        "disliked_foods",
        []
    )

    preferred_cuisines = preferences.get(
        "preferred_cuisines",
        []
    )

    spicy_level = preferences.get(
        "spicy_level",
        ""
    )

    budget_range = preferences.get(
        "budget_range",
        ""
    )

    ingredients = menu_item.get(
        "ingredients",
        []
    )

    tags = menu_item.get(
        "tags",
        []
    )

    food_name = menu_item.get(
        "food_name",
        ""
    ).lower()

    # Favorite food boost
    for food in favorite_foods:

        if food.lower() in food_name:

            score += 40

    # Disliked food penalty
    for dislike in disliked_foods:

        if dislike.lower() in food_name:

            score -= 50

    # Cuisine matching
    cuisine = menu_item.get(
        "cuisine",
        ""
    )

    if cuisine in preferred_cuisines:

        score += 25

    # Spicy level matching
    if spicy_level:

        if menu_item.get(
            "spicy_level",
            ""
        ).lower() == spicy_level.lower():

            score += 20

    # Tag matching
    for tag in tags:

        if tag.lower() in [
            food.lower()
            for food in favorite_foods
        ]:

            score += 10

    # Budget matching
    price = menu_item.get(
        "price",
        0
    )

    if budget_range == "low":

        if price <= 300:

            score += 15

    elif budget_range == "medium":

        if 300 <= price <= 700:

            score += 15

    elif budget_range == "high":

        if price >= 700:

            score += 15

    # Restaurant rating boost
    restaurant_rating = menu_item.get(
        "restaurant_rating",
        0
    )

    score += int(restaurant_rating * 2)

    # Ingredient matching
    for ingredient in ingredients:

        if ingredient.lower() in [
            food.lower()
            for food in favorite_foods
        ]:

            score += 8

    # Semantic similarity boost
    semantic_score = menu_item.get(
        "semantic_score",
        0
    )

    score += int(semantic_score * 30)

    return score


def recommend_foods(user_id, food_query):

    user_profile = get_user_profile(
        user_id
    )

    preferences = user_profile.get(
        "preferences",
        {}
    )

    candidate_foods = hybrid_food_search(
        food_query
    )

    ranked_foods = []

    for item in candidate_foods:

        score = calculate_score(
            item,
            preferences
        )

        item["_id"] = str(
            item["_id"]
        )

        item["recommendation_score"] = score

        ranked_foods.append(
            item
        )

    ranked_foods.sort(
        key=lambda x: x[
            "recommendation_score"
        ],
        reverse=True
    )

    return ranked_foods