from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import re

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def extract_preferences(user_message, conversation_history=None, existing_allergies=None):

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


def extract_preferences_with_context(user_message, conversation_history=None, existing_allergies=None):

    normalized_user_message = _expand_user_shorthand(user_message)
    context_block = _build_context_block(conversation_history)
    allergies_hint = ", ".join(existing_allergies or [])

    prompt = f"""
    Extract food preferences from the user message.

    Return ONLY valid JSON.

    Example format:

    {{
        "favorite_foods": [],
        "disliked_foods": [],
        "allergies": [],
        "spicy_level": "",
        "budget_range": "",
        "preferred_cuisines": [],
        "favorite_restaurants": [],
        "favorite_drinks": [],
        "delivery_speed_preference": "",   # express|standard|slow
        "preferred_meal_time": []
    }}

    Rules:
    - If the user says they are allergic to something, put it in "allergies".
    - Do NOT place allergy items in "disliked_foods".
    - Use "disliked_foods" only for foods the user does not like.
    - If the user says "both", "all of them", "these", "those", "them", or similar, resolve it to the exact allergy items from the recent conversation context.
    - Never store vague words like "both" as an allergy item.
    - Users may type short forms (example: fvrt=favorite, algy=allergy, bgt=budget, spcy=spicy, addr=address). Interpret these correctly.

    Recent Conversation Context:
    {context_block or "None"}

    Existing Known Allergies:
    {allergies_hint or "None"}

    User Message:
    {normalized_user_message}
    """

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": "You extract food preferences."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )

    content = response.choices[0].message.content

    try:
        extracted = json.loads(content)

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
    except:
        return {}
