from anthropic import Anthropic
from dotenv import load_dotenv
import os
import json
import re

from .claude_service import chat_with_claude

load_dotenv()

client = Anthropic(
    api_key=os.getenv("CLAUDE_API_KEY")
)


def extract_preferences(user_message, conversation_history=None, existing_allergies=None):
    """
    Extract food preferences using Claude.
    Claude is better at understanding context, nuance, and resolving ambiguity.
    """
    return extract_preferences_with_context(
        user_message,
        conversation_history=conversation_history,
        existing_allergies=existing_allergies
    )


def _build_context_block(conversation_history):

    if not conversation_history:
        return ""

    recent_messages = conversation_history[-6:]
    lines = []

    for message in recent_messages:
        role = message.get("role", "")
        content = message.get("content", "")
        if content:
            lines.append(f"{role}: {content}")

    return "\n".join(lines)


def _contains_any(text, patterns):
    if not text:
        return False
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


def _normalize_output_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_text(value):
    return re.sub(r"[^a-z0-9\- ]", " ", str(value or "").lower()).strip()


def _normalize_dietary_value(value):
    text = _normalize_text(value)
    if not text:
        return ""

    aliases = {
        "vegan": "vegan",
        "vegetarian": "vegetarian",
        "halal": "halal",
        "kosher": "kosher",
        "gluten free": "gluten-free",
        "gluten-free": "gluten-free",
        "dairy free": "dairy-free",
        "dairy-free": "dairy-free",
        "nut free": "nut-free",
        "nut-free": "nut-free",
        "keto": "keto",
        "paleo": "paleo",
        "low carb": "low-carb",
        "low-carb": "low-carb"
    }

    if text in aliases:
        return aliases[text]

    compact = text.replace(" ", "")
    compact_aliases = {
        "glutenfree": "gluten-free",
        "dairyfree": "dairy-free",
        "nutfree": "nut-free",
        "lowcarb": "low-carb"
    }

    return compact_aliases.get(compact, text)


def _normalize_dietary_list(value):
    items = []
    for item in _normalize_output_list(value):
        normalized = _normalize_dietary_value(item)
        if normalized:
            items.append(normalized)

    deduped = []
    seen = set()
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _expand_user_shorthand(message):
    if not message:
        return ""

    text = str(message).strip()
    prompt = f"""You are a text normalization assistant for food preference extraction.
Rewrite the user message by replacing shorthand, abbreviations, slang, alternate spellings, non-English variants, and informal wording
with canonical English terms that a preference extractor can understand.

If the message is written in another language, interpret it and output the normalized English equivalent.
Keep the original meaning exactly the same.
Return ONLY the rewritten text, without explanations.

Examples:
- fvrt, favrt, fvrt, fvt, fav, favorita -> favorite
- dslk, dislk, dlike, don't like, dontlike -> dislike
- algy, allrgy, allergy, allergic -> allergy
- cuis, cuisn, cusine -> cuisine
- dtry -> dietary
- restr, restn, restrn -> restriction
- spcy, spci, spicey -> spicy
- bgt, budgt, bdgt -> budget
- freq, frq -> frequency
- addr, addrs, adress -> address
- brkfst, bf -> breakfast
- lnch, lunc -> lunch
- dinr, dnr -> dinner
- posondo, like, favorita -> favorite
- ami seafood posondo kori -> I like seafood
- me gusta el marisco -> I like seafood
- If a word is already plain English, preserve it.

Original message:
""" + text + """
"""

    normalizer_messages = [
        {
            "role": "user",
            "content": prompt
        }
    ]

    normalized_text = chat_with_claude(
        messages=normalizer_messages,
        system_prompt="You are an assistant that rewrites informal or multilingual user text into normalized English for downstream preference extraction.",
        temperature=0,
        max_tokens=256
    )

    if normalized_text and isinstance(normalized_text, str):
        normalized_text = normalized_text.strip()

    return normalized_text or text


def _sanitize_extracted_preferences(user_message, extracted):
    if not isinstance(extracted, dict):
        return {}

    favorite_foods = _normalize_output_list(extracted.get("favorite_foods"))
    disliked = _normalize_output_list(extracted.get("disliked_foods"))
    allergies = _normalize_output_list(extracted.get("allergies"))

    def _filter_noise_tokens(items):
        filtered = []
        for item in items:
            if not item:
                continue
            token = str(item).strip()
            if len(token) == 1 and re.fullmatch(r"[A-Za-z0-9]", token):
                continue
            filtered.append(token)
        return filtered

    favorite_foods = _filter_noise_tokens(favorite_foods)
    disliked = _filter_noise_tokens(disliked)
    allergies = _filter_noise_tokens(allergies)

    extracted["favorite_foods"] = favorite_foods

    allergy_patterns = [
        r"\ballerg(y|ic|ies)\b",
        r"\bintoleran(t|ce)\b",
        r"\breaction\b",
        r"\bcannot eat\b",
        r"\bcan'?t eat\b"
    ]
    dislike_patterns = [
        r"\bdon'?t like\b",
        r"\bdo not like\b",
        r"\bdislike\b",
        r"\bhate\b",
        r"\bnot a fan\b",
        r"\bdon'?t want\b"
    ]

    has_allergy_signal = _contains_any(user_message, allergy_patterns)
    has_dislike_signal = _contains_any(user_message, dislike_patterns)

    # If user expressed dislike but not allergy, keep foods in disliked only.
    if has_dislike_signal and not has_allergy_signal and allergies:
        disliked = list(dict.fromkeys(disliked + allergies))
        allergies = []

    extracted["disliked_foods"] = disliked
    extracted["allergies"] = allergies

    # Normalize favorite restaurants and drinks into lists
    fav_rests = _normalize_output_list(extracted.get("favorite_restaurants"))
    fav_drinks = _normalize_output_list(extracted.get("favorite_drinks"))

    extracted["favorite_restaurants"] = fav_rests
    extracted["favorite_drinks"] = fav_drinks

    dietary_style = extracted.get("dietary_style")
    if isinstance(dietary_style, list):
        dietary_style = dietary_style[0] if dietary_style else ""
    dietary_style = _normalize_dietary_value(dietary_style)

    dietary_restrictions = _normalize_dietary_list(extracted.get("dietary_restrictions"))
    if dietary_style and dietary_style not in dietary_restrictions:
        dietary_restrictions.insert(0, dietary_style)

    extracted["dietary_style"] = dietary_style
    extracted["dietary_restrictions"] = dietary_restrictions

    # Normalize delivery speed preference
    dsp = extracted.get("delivery_speed_preference")
    if isinstance(dsp, str):
        dsl = dsp.strip().lower()
        if any(tok in dsl for tok in ("express", "fast", "quick")):
            extracted["delivery_speed_preference"] = "express"
        elif any(tok in dsl for tok in ("slow", "sluggish")):
            extracted["delivery_speed_preference"] = "slow"
        elif any(tok in dsl for tok in ("standard", "normal", "regular")):
            extracted["delivery_speed_preference"] = "standard"
        else:
            extracted["delivery_speed_preference"] = dsl

    # Normalize preferred meal time into list
    pmt = extracted.get("preferred_meal_time")
    if isinstance(pmt, str) and pmt.strip():
        extracted["preferred_meal_time"] = [pmt.strip()]
    elif not pmt:
        extracted["preferred_meal_time"] = []

    return extracted


def _extract_json_object(text):
    if not text:
        return None

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _extract_allergies_from_text(text):
    if not text:
        return []

    text = str(text).strip()
    # replace common apostrophes so contractions like "J'aime" become "J aime"
    text = text.replace("'", " ").replace("'", " ")

    # Use only the Claude prompt-based allergy extractor.
    # Do not fall back to regex heuristics for allergy extraction.
    return _extract_allergies_with_claude(text)


def _parse_allergies_response(text):
    if not text:
        return []

    text = str(text).strip()
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = _extract_json_object(text)

    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(parsed, dict):
        return _normalize_output_list(parsed.get("allergies"))
    if isinstance(parsed, str) and parsed.strip():
        return [parsed.strip()]

    return []


def _extract_allergies_with_claude(text):
    if not text:
        return []

    prompt = f"""Extract only the food allergies or intolerances from the following user message.
Return ONLY a JSON array of foods or drinks the user explicitly says they are allergic to, intolerant to, or have a reaction to.
Do NOT include dislikes, foods the user avoids for preference reasons, dietary restrictions, brands, or generic terms like 'food' or 'anything'.
If there are no allergies, return [] exactly.

Examples:
- "I am allergic to peanuts." -> ["peanuts"]
- "I have an allergy to shellfish." -> ["shellfish"]
- "I'm intolerant to dairy." -> ["dairy"]
- "I cannot eat gluten." -> ["gluten"]
- "I have a reaction to nuts." -> ["nuts"]
- "I don't like mushrooms." -> []
- "I am vegan." -> []

User message:
{text}
"""

    response_text = chat_with_claude(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="You are an assistant that extracts food allergies and intolerances from user text.",
        temperature=0,
        max_tokens=256
    )

    return _parse_allergies_response(response_text)


def _extract_favorite_foods_from_text(text):
    if not text:
        return []

    text = str(text).strip()
    # replace common apostrophes so contractions like "J'aime" become "J aime"
    text = text.replace("'", " ").replace("’", " ")

    # Use only the Claude prompt-based favorite food extractor.
    # Do not fall back to regex heuristics for favorite food extraction.
    return _extract_favorite_foods_with_claude(text)


def _parse_disliked_foods_response(text):
    if not text:
        return []

    text = str(text).strip()
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = _extract_json_object(text)

    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(parsed, dict):
        return _normalize_output_list(parsed.get("disliked_foods"))
    if isinstance(parsed, str) and parsed.strip():
        return [parsed.strip()]

    return []


def _parse_favorite_foods_response(text):
    if not text:
        return []

    text = str(text).strip()
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = _extract_json_object(text)

    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(parsed, dict):
        return _normalize_output_list(parsed.get("favorite_foods"))
    if isinstance(parsed, str) and parsed.strip():
        return [parsed.strip()]

    return []


def _extract_disliked_foods_with_claude(text):
    if not text:
        return []

    prompt = f"""Extract only the disliked food items from the following user message.
Return ONLY a JSON array of foods or drinks the user explicitly or implicitly says they do not like, hate,
avoid, detest, loathe, can't stand, can't abide, dislike, are not a fan of, or use any similar expressions of dislike or aversion.
Do not include allergies, intolerances, dietary restrictions, brands, or generic terms like "food" or "anything".
If there are no disliked foods, return [] exactly.

Examples:
- "I don't like peanuts at all." -> ["peanuts"]
- "I would rather starve than drink milk." -> ["milk"]
- "Mushrooms ruin the taste of any food for me." -> ["mushrooms"]
- "I absolutely dislike onions." -> ["onions"]
- "Bell peppers are really not my thing." -> ["bell peppers"]
- "I detest seafood." -> ["seafood"]
- "I can't stand broccoli." -> ["broccoli"]

User message:
{text}
"""

    response_text = chat_with_claude(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="You are an assistant that extracts disliked food items from user text.",
        temperature=0,
        max_tokens=256
    )

    return _parse_disliked_foods_response(response_text)


def _extract_favorite_foods_with_claude(text):
    if not text:
        return []

    prompt = f"""Extract only the favorite food items from the following user message.
Return ONLY a JSON array of foods or drinks the user explicitly or implicitly indicates are their favorite, preferred, liked, loved, or enjoyed items.
Do NOT treat simple desire phrases such as 'I want rice' or 'I want burger' as favorite foods unless the user also describes them with favorite/like language.
Do not include dislikes, allergies, intolerances, dietary restrictions, brands, or generic terms like 'food' or 'anything'.
If there are no favorite foods, return [] exactly.

Examples:
- "I like rice and burger." -> ["rice", "burger"]
- "Rice is my favorite." -> ["rice"]
- "I love sushi." -> ["sushi"]
- "I enjoy pasta." -> ["pasta"]
- "I would like rice." -> []
- "I need sushi." -> []
- "I want rice, I want burger." -> []
- "I want rice, but I really like fries." -> ["fries"]

User message:
{text}
"""

    response_text = chat_with_claude(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="You are an assistant that extracts favorite food items from user text.",
        temperature=0,
        max_tokens=256
    )

    return _parse_favorite_foods_response(response_text)


def _extract_disliked_foods_from_text(text):
    if not text:
        return []

    text = str(text).strip()
    text = text.replace("'", " ").replace("’", " ")

    disliked = _extract_disliked_foods_with_claude(text)
    if disliked:
        return disliked

    dislikes = []
    patterns = [
        r"\b(?:do not like|dont like|don't like|not a fan of|not a fan|hate|dislike|can't stand|cannot stand|avoid|avoiding|avoidance of)\s+([a-zA-Z0-9 ,&\-]+?)(?:\s*(?:and|but|because|that|with|from|for|$))",
        r"\b([a-zA-Z0-9 ,&\-]+?)\s+is not my (?:favorite|favourite|preferred)\b",
        r"\b(?:not my favorite|not my favourite|not preferred)\s+([a-zA-Z0-9 ,&\-]+?)(?:\s*(?:and|but|because|that|with|from|for|$))"
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                match = match[-1]
            if not match:
                continue
            candidates = re.split(r",| and | & |/|;|\\|", match, flags=re.IGNORECASE)
            for item in candidates:
                cleaned = re.sub(r"[^a-zA-Z0-9\- ]", "", item or "").strip()
                if cleaned and not re.search(r"\b(allergy|allergic|intolerant|reaction|cannot eat)\b", cleaned, flags=re.IGNORECASE):
                    dislikes.append(cleaned)

    deduped = []
    seen = set()
    for item in dislikes:
        normalized = item.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)

    return deduped


def extract_preferences_with_context(user_message, conversation_history=None, existing_allergies=None):
    """
    Extract preferences using Claude for superior context understanding.
    """
    normalized_user_message = _expand_user_shorthand(user_message)
    context_block = _build_context_block(conversation_history)
    allergies_hint = ", ".join(existing_allergies or [])

    system_prompt = """You are an expert food preference extraction AI. Your job is to carefully analyze user messages and extract structured food preferences.

Return ONLY valid JSON. Be precise and careful about allergies vs dislikes.

Key rules:
- Allergies are health/safety concerns (user says: allergic, intolerant, reaction)
- Disliked foods are taste preferences (user says: don't like, hate, not a fan)
- Favorite foods are items the user likes, loves, enjoys, prefers, or explicitly indicates are favorites.
- Do NOT treat simple desire or ordering phrases such as "I want", "I would like", "I need", "I would love", or "Can I have" as favorite foods unless the user also clearly expresses liking, preference, or favorite sentiment.
- Never put allergy items in "disliked_foods"
- For dietary preferences (vegan, vegetarian, halal, kosher, gluten-free, dairy-free, nut-free, keto, paleo, low-carb), normalize to the exact term
- If user says "both", "all of them", "these", resolve to exact items from context
- Avoid vague terms like "both" as allergy items
- Use meaning and sentiment to determine disliked foods, not just hard keyword matching
"""

    prompt = f"""Extract food preferences from this user message.

Example:
- "I like seafood and I have allergy to pasta." -> favorite_foods: ["seafood"], allergies: ["pasta"]
- "Sandwiches always hit the spot for me." -> favorite_foods: ["sandwiches"]
- "biriyani always loved by me." -> favorite_foods: ["biriyani"]
- "I don't like mushrooms." -> disliked_foods: ["mushrooms"]
- "I'm not a fan of olives." -> disliked_foods: ["olives"]
- "I hate tomatoes." -> disliked_foods: ["tomatoes"]
- "I can't stand peanuts." -> disliked_foods: ["peanuts"]
- "I absolutely dislike peanuts." -> disliked_foods: ["peanuts"]
- "I detest peanuts." -> disliked_foods: ["peanuts"]
- "I loathe peanuts." -> disliked_foods: ["peanuts"]
- "I can't abide peanuts." -> disliked_foods: ["peanuts"]

Recent conversation context:
{context_block or "None"}

Existing known allergies:
{allergies_hint or "None"}

User message:
{normalized_user_message}

Return JSON in this format (ONLY JSON, no explanation):
{{
    "favorite_foods": [],
    "disliked_foods": [],
    "allergies": [],
    "dietary_style": "",
    "dietary_restrictions": [],
    "spicy_level": "",
    "budget_range": "",
    "preferred_cuisines": [],
    "favorite_restaurants": [],
    "favorite_drinks": [],
    "delivery_speed_preference": "",
    "preferred_meal_time": []
}}

Rules:
- If the user says they are allergic to something, put it in "allergies".
- Do NOT place allergy items in "disliked_foods".
- Use "disliked_foods" only for foods the user does not like.
- Favorite food values must be whole food terms, not single letters or fragments.
- Do not output single-character food items.
- If the user mentions a diet such as vegan, vegetarian, halal, kosher, gluten-free, dairy-free, nut-free, keto, paleo, or low-carb, fill both "dietary_style" and "dietary_restrictions" with the best matching normalized label.
- If the user says "both", "all of them", "these", "those", "them", or similar, resolve it to the exact allergy items from the recent conversation context.
- Never store vague words like "both" as an allergy item.
"""

    response = client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-opus-4-6"),
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )

    content = response.content[0].text

    extracted = None
    try:
        extracted = json.loads(content)
    except Exception:
        extracted = _extract_json_object(content)

    if not isinstance(extracted, dict):
        fallback_allergies = _extract_allergies_from_text(normalized_user_message)
        fallback_favorites = _extract_favorite_foods_from_text(normalized_user_message)
        fallback_dislikes = _extract_disliked_foods_from_text(normalized_user_message)
        return _sanitize_extracted_preferences(normalized_user_message, {
            "favorite_foods": fallback_favorites,
            "disliked_foods": fallback_dislikes,
            "allergies": fallback_allergies,
            "dietary_style": "",
            "dietary_restrictions": [],
            "spicy_level": "",
            "budget_range": "",
            "preferred_cuisines": [],
            "favorite_restaurants": [],
            "favorite_drinks": [],
            "delivery_speed_preference": "",
            "preferred_meal_time": []
        })

    favorite_foods = _normalize_output_list(extracted.get("favorite_foods"))
    extracted["favorite_foods"] = favorite_foods
    if not favorite_foods:
        inferred_favorites = _extract_favorite_foods_from_text(normalized_user_message)
        if inferred_favorites:
            extracted["favorite_foods"] = inferred_favorites

    disliked_foods = _normalize_output_list(extracted.get("disliked_foods"))
    extracted["disliked_foods"] = disliked_foods
    if not disliked_foods:
        inferred_dislikes = _extract_disliked_foods_from_text(normalized_user_message)
        if inferred_dislikes:
            extracted["disliked_foods"] = inferred_dislikes

    if existing_allergies:
        normalized_existing = [str(item).strip() for item in existing_allergies if str(item).strip()]

        allergy_values = extracted.get("allergies", [])
        if isinstance(allergy_values, str):
            allergy_values = [allergy_values]

        cleaned_allergies = []
        generic_terms = {"both", "all", "all of them", "these", "those", "them", "it", "ones", "them all"}

        for item in allergy_values:
            cleaned = str(item).strip()
            if not cleaned:
                continue
            if cleaned.lower() in generic_terms:
                cleaned_allergies.extend(normalized_existing)
                continue
            cleaned_allergies.append(cleaned)

        if cleaned_allergies:
            deduped = []
            for item in cleaned_allergies:
                if item not in deduped:
                    deduped.append(item)
            extracted["allergies"] = deduped

    extracted = _sanitize_extracted_preferences(normalized_user_message, extracted)

    return extracted
