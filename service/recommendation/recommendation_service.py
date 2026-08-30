from anthropic import Anthropic
from dotenv import load_dotenv
import os
import json

from service.data.profile_service import get_user_profile
import re
from difflib import SequenceMatcher

from service.business.restaurant_service import hybrid_food_search
from service.business.location_service import get_nearby_restaurants

load_dotenv()

client = Anthropic(
    api_key=os.getenv("CLAUDE_API_KEY")
)

_DIETARY_QUERY_TERMS = {
    "vegan",
    "vegetarian",
    "plant-based",
    "plant based",
    "meatless",
    "no meat",
    "no-meat",
    "veggie",
    "halal",
    "kosher",
    "gluten-free",
    "gluten free",
    "dairy-free",
    "dairy free",
    "nut-free",
    "nut free",
    "keto",
    "paleo",
    "low-carb",
    "low carb"
}


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


def _normalize_text(value):
    return re.sub(r"[^a-z0-9 ]", " ", str(value or "").lower()).strip()


def _dedupe_preserve_order(values):
    deduped = []
    seen = set()

    for value in values or []:
        cleaned = str(value or "").strip()
        if not cleaned:
            continue

        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)

    return deduped


def _is_dietary_query(query):
    normalized = _normalize_text(query)
    if not normalized:
        return False

    if normalized in _DIETARY_QUERY_TERMS:
        return True

    return any(term in normalized for term in _DIETARY_QUERY_TERMS)


def _expand_search_queries_with_ai(food_query, preferences):
    dietary_style = str((preferences or {}).get("dietary_style", "") or "").strip()
    dietary_restrictions = (preferences or {}).get("dietary_restrictions", []) or []
    preferred_cuisines = (preferences or {}).get("preferred_cuisines", []) or []

    system_prompt = """You generate short, specific food search queries that will match real restaurant menu items.

Important:
- Return ONLY valid JSON as an array of strings
- No explanations, numbering, or markdown
- Each query should be 1-4 words
- Do not repeat the same phrase"""

    prompt = f"""Generate 5 short food search queries that match real restaurant menu items.

User request: {food_query}
Dietary style: {dietary_style or 'none'}
Dietary restrictions: {', '.join(dietary_restrictions) or 'none'}
Preferred cuisines: {', '.join(preferred_cuisines) or 'none'}

Rules:
- Prefer broad menu terms that restaurants actually use
- If the user request is mainly dietary, translate it into dish categories instead of repeating the diet label
- Keep each query short, natural, and searchable
- Return ONLY JSON array of strings, no explanation"""

    try:
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-opus-4-6"),
            max_tokens=256,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )

        content = response.content[0].text or ""
        parsed = json.loads(content)

        if isinstance(parsed, str):
            parsed = [parsed]

        if not isinstance(parsed, list):
            return []

        queries = [str(item).strip() for item in parsed if str(item).strip()]
        return _dedupe_preserve_order([food_query] + queries)
    except Exception:
        fallback_queries = [
            food_query,
            "vegetable bowl",
            "mixed vegetables",
            "rice bowl",
            "salad",
            "tofu",
            "lentil curry",
            "grilled vegetables"
        ]

        if _is_dietary_query(food_query):
            return _dedupe_preserve_order(fallback_queries)

        return [food_query]


def _search_food_candidates(food_query, preferences):
    queries = [food_query]

    if _is_dietary_query(food_query):
        queries = _expand_search_queries_with_ai(food_query, preferences)

    combined = []
    seen_ids = set()

    for query in queries:
        for item in hybrid_food_search(query):
            menu_id = str(item.get("menu_id", ""))
            if not menu_id or menu_id in seen_ids:
                continue
            seen_ids.add(menu_id)
            combined.append(item)

    return combined


def _gather_menu_text(item):
    parts = []
    parts.append(item.get("food_name", ""))
    parts.append(item.get("category", ""))
    parts.extend(item.get("tags", []) or [])
    parts.extend(item.get("ingredients", []) or [])
    parts.append(item.get("description", ""))
    return _normalize_text(" ".join(str(p) for p in parts if p))


def _contains_keywords(item, keywords):
    text = _gather_menu_text(item)
    return any(keyword in text for keyword in keywords if keyword)


def _is_diet_vegan_safe(item):
    text = _gather_menu_text(item)
    vegan_blacklist = [
        "beef", "chicken", "pork", "lamb", "mutton", "shrimp", "prawns",
        "fish", "salmon", "tuna", "crab", "lobster", "oyster", "mussel",
        "clams", "shellfish", "egg", "cheese", "milk", "yogurt", "cream",
        "butter", "ghee", "paneer", "honey", "gelatin", "mayonnaise", "milkshake"
    ]
    if any(term in text for term in vegan_blacklist):
        return False
    if "vegan" in text:
        return True
    # If the item is a burger or kebab and not explicitly vegan, reject as unsafe.
    if any(term in text for term in ["burger", "kebab", "sausage", "steak", "ribs"]):
        return False
    return True


def _is_diet_vegetarian_safe(item):
    text = _gather_menu_text(item)
    vegetarian_blacklist = [
        "beef", "chicken", "pork", "lamb", "mutton", "shrimp", "prawns",
        "fish", "salmon", "tuna", "crab", "lobster", "oyster", "mussel",
        "clams", "shellfish"
    ]
    if any(term in text for term in vegetarian_blacklist):
        return False
    return True


def _is_diet_gluten_free_safe(item):
    text = _gather_menu_text(item)
    gluten_blacklist = ["wheat", "barley", "rye", "malt", "semolina", "spelt", "pasta", "breadcrumbs", "bread", "flour"]
    return not any(term in text for term in gluten_blacklist)


def _is_diet_dairy_free_safe(item):
    text = _gather_menu_text(item)
    dairy_blacklist = ["milk", "cheese", "yogurt", "cream", "butter", "paneer", "ghee", "ice cream", "custard"]
    return not any(term in text for term in dairy_blacklist)


def _is_diet_halal_safe(item):
    text = _gather_menu_text(item)
    halal_blacklist = ["pork", "ham", "bacon", "alcohol", "wine", "beer", "whiskey", "vodka"]
    if any(term in text for term in halal_blacklist):
        return False
    return True


def _is_restriction_safe(item, restriction):
    if not restriction:
        return True
    normalized = str(restriction).lower().strip()
    if normalized in {"vegan", "vegetarian", "halal", "kosher", "gluten-free", "gluten free", "dairy-free", "dairy free", "low-carb", "keto", "paleo"}:
        if normalized == "vegan":
            return _is_diet_vegan_safe(item)
        if normalized == "vegetarian":
            return _is_diet_vegetarian_safe(item)
        if normalized == "halal":
            return _is_diet_halal_safe(item)
        if normalized == "kosher":
            # Kosher filtering is best-effort based on meat + dairy mixing; if a kosher tag exists, accept.
            text = _gather_menu_text(item)
            if "kosher" in text:
                return True
            return not any(term in text for term in ["pork", "shellfish", "shrimp", "crab", "ham", "bacon"])
        if normalized in {"gluten-free", "gluten free"}:
            return _is_diet_gluten_free_safe(item)
        if normalized in {"dairy-free", "dairy free"}:
            return _is_diet_dairy_free_safe(item)
        if normalized == "low-carb":
            text = _gather_menu_text(item)
            return not any(term in text for term in ["bread", "pasta", "rice", "potato", "fries", "brioche", "bun"])
        if normalized == "keto":
            text = _gather_menu_text(item)
            return not any(term in text for term in ["bread", "pasta", "rice", "sugar", "corn", "potato", "flour"])
        if normalized == "paleo":
            text = _gather_menu_text(item)
            return not any(term in text for term in ["bread", "pasta", "rice", "dairy", "beans", "lentils", "sugar"])
    return True


def is_dietary_safe(menu_item, preferences):
    if not preferences:
        return True

    style = str(preferences.get("dietary_style", "") or "").lower().strip()
    restrictions = [str(r).lower().strip() for r in (preferences.get("dietary_restrictions", []) or []) if str(r).strip()]

    # If dietary_style duplicates restrictions, keep unique values
    if style and style not in restrictions:
        restrictions.insert(0, style)

    if not restrictions:
        return True

    for restriction in restrictions:
        if not _is_restriction_safe(menu_item, restriction):
            return False

    return True


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


def recommend_foods(user_id, food_query, relax_dietary=False, lat=None, lng=None):

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

    candidate_foods = _search_food_candidates(
        food_query,
        preferences
    )

    if lat is not None and lng is not None:
        nearby_restaurants = get_nearby_restaurants(lat, lng)
        nearby_ids = {
            str(item.get("restaurant_id", "")).strip()
            for item in (nearby_restaurants or [])
            if str(item.get("restaurant_id", "")).strip()
        }

        if nearby_ids:
            candidate_foods = [
                item for item in candidate_foods
                if str(item.get("restaurant_id", "")).strip() in nearby_ids
            ]
        else:
            candidate_foods = []

    ranked_foods = []

    for item in candidate_foods:

        if not _is_allergy_safe(item, allergies):
            continue

        if not relax_dietary and not is_dietary_safe(item, preferences):
            continue

        score = calculate_score(
            item,
            preferences
        )

        item["_id"] = str(
            item["_id"]
        )

        item["score"] = score
        ranked_foods.append(item)

    ranked_foods.sort(key=lambda x: x.get("score", 0), reverse=True)

    return ranked_foods[:5]
