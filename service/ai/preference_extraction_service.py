from anthropic import Anthropic
from dotenv import load_dotenv
import os
import json
import re

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

    text = str(message)
    replacements = [
        (r"\b(fvrt|favrt|fvrt|fvt|fav)\b", "favorite"),
        (r"\b(dslk|dlike|dislk|dontlike|donotlike|dntlike)\b", "dislike"),
        (r"\b(algy|allrgy|allergy|allergic)\b", "allergy"),
        (r"\b(cuis|cuisn|cusine|cuisine)\b", "cuisine"),
        (r"\b(diet|dtry)\b", "dietary"),
        (r"\b(restr|restn|restrn)\b", "restriction"),
        (r"\b(spcy|spci|spicey)\b", "spicy"),
        (r"\b(bgt|budgt|bdgt)\b", "budget"),
        (r"\b(freq|frq)\b", "frequency"),
        (r"\b(addr|addrs|adress)\b", "address"),
        (r"\b(brkfst|bf)\b", "breakfast"),
        (r"\b(lnch|lunc)\b", "lunch"),
        (r"\b(dinr|dnr)\b", "dinner")
    ]

    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


def _sanitize_extracted_preferences(user_message, extracted):
    if not isinstance(extracted, dict):
        return {}

    disliked = _normalize_output_list(extracted.get("disliked_foods"))
    allergies = _normalize_output_list(extracted.get("allergies"))

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
    patterns = [
        r"(?:allerg(?:y|ic) to|intolerant to|intolerance to|reaction to|can(?:'t| not) eat|cannot eat)\s+([a-z0-9 ,&\-]+)",
    ]
    allergies = []

    for pattern in patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                match = match[-1]
            for item in re.split(r",| and | & |/|;|\\band\\b", match, flags=re.IGNORECASE):
                cleaned = re.sub(r"[^a-zA-Z0-9\- ]", "", item or "").strip()
                if cleaned:
                    allergies.append(cleaned)

    deduped = []
    seen = set()
    for item in allergies:
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
- Never put allergy items in "disliked_foods"
- For dietary preferences (vegan, vegetarian, halal, kosher, gluten-free, dairy-free, nut-free, keto, paleo, low-carb), normalize to the exact term
- If user says "both", "all of them", "these", resolve to exact items from context
- Avoid vague terms like "both" as allergy items
"""

    prompt = f"""Extract food preferences from this user message.

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
        if fallback_allergies:
            return _sanitize_extracted_preferences(normalized_user_message, {
                "favorite_foods": [],
                "disliked_foods": [],
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
        return {}

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
