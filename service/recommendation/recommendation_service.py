from service.data.profile_service import get_user_profile
import re
from difflib import SequenceMatcher

from service.business.restaurant_service import hybrid_food_search


def _normalize_token(value):
    token = re.sub(r"[^a-z0-9]", "", str(value or "").lower())
    return token


def _collect_terms(value):
    if not value:
        return []

    if isinstance(value, list):
        raw = []
        for item in value:
            raw.extend(_collect_terms(item))
        return raw

    text = str(value)
    parts = re.split(r"[,;/|]", text)
    tokens = []
    for part in parts:
        words = re.findall(r"[a-zA-Z0-9]+", part.lower())
        tokens.extend(words)
    return tokens


def _looks_like_match(allergy_term, candidate_term):
    left = _normalize_token(allergy_term)
    right = _normalize_token(candidate_term)

    if not left or not right:
        return False

    if left == right:
        return True

    if left in right or right in left:
        if min(len(left), len(right)) >= 4:
            return True

    length_gap = abs(len(left) - len(right))
    if length_gap > 2:
        return False

    similarity = SequenceMatcher(None, left, right).ratio()
    return similarity >= 0.8


def _is_allergy_safe(menu_item, allergies):
    if not allergies:
        return True

    allergy_terms = _collect_terms(allergies)
    if not allergy_terms:
        return True

    candidate_terms = []
    candidate_terms.extend(_collect_terms(menu_item.get("ingredients", [])))
    candidate_terms.extend(_collect_terms(menu_item.get("tags", [])))
    candidate_terms.extend(_collect_terms(menu_item.get("food_name", "")))

    if not candidate_terms:
        return True

    for allergy_term in allergy_terms:
        for candidate_term in candidate_terms:
            if _looks_like_match(allergy_term, candidate_term):
                return False

    return True


def _get_allergy_conflicts(menu_item, allergies):
    if not allergies:
        return []

    allergy_terms = _collect_terms(allergies)
    candidate_terms = []
    candidate_terms.extend(_collect_terms(menu_item.get("ingredients", [])))
    candidate_terms.extend(_collect_terms(menu_item.get("tags", [])))
    candidate_terms.extend(_collect_terms(menu_item.get("food_name", "")))

    conflicts = []
    for allergy_term in allergy_terms:
        for candidate_term in candidate_terms:
            if _looks_like_match(allergy_term, candidate_term):
                conflicts.append(candidate_term)
                break

    # preserve order, remove duplicates
    unique_conflicts = []
    seen = set()
    for item in conflicts:
        key = str(item).lower()
        if key in seen:
            continue
        seen.add(key)
        unique_conflicts.append(str(item).lower())

    return unique_conflicts


def filter_allergy_safe_foods(menu_items, allergies):
    safe_items = []
    blocked_items = []

    for item in (menu_items or []):
        conflicts = _get_allergy_conflicts(item, allergies)
        if conflicts:
            blocked_items.append({
                "food_name": item.get("food_name", "Unknown"),
                "matched_ingredients": conflicts
            })
            continue
        safe_items.append(item)

    return safe_items, blocked_items


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

    allergies = preferences.get(
        "allergies",
        []
    )

    candidate_foods = hybrid_food_search(
        food_query
    )

    ranked_foods = []

    for item in candidate_foods:

        if not _is_allergy_safe(item, allergies):
            continue

        score = calculate_score(
            item,
            preferences
        )

        item["_id"] = str(
            item["_id"]
        )
