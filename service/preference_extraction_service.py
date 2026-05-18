from openai import OpenAI
from dotenv import load_dotenv
import os
import json

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


def extract_preferences_with_context(user_message, conversation_history=None, existing_allergies=None):

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
        "preferred_cuisines": []
    }}

    Rules:
    - If the user says they are allergic to something, put it in "allergies".
    - Do NOT place allergy items in "disliked_foods".
    - Use "disliked_foods" only for foods the user does not like.
    - If the user says "both", "all of them", "these", "those", "them", or similar, resolve it to the exact allergy items from the recent conversation context.
    - Never store vague words like "both" as an allergy item.

    Recent Conversation Context:
    {context_block or "None"}

    Existing Known Allergies:
    {allergies_hint or "None"}

    User Message:
    {user_message}
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

        return extracted
    except:
        return {}