from openai import OpenAI
from dotenv import load_dotenv
import os

from service.memory.memory_service import (
    get_conversation,
    add_message
)


from service.ai.preference_extraction_service import extract_preferences

from service.data.profile_service import get_user_profile, update_user_preferences

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

SYSTEM_PROMPT = """
You are an AI food ordering assistant.

Your responsibilities:
- Help users find foods
- Suggest restaurants
- Continue conversation naturally
- Remember conversation context
"""


def _build_profile_context(profile):
    preferences = (profile or {}).get("preferences", {})

    allergies = preferences.get("allergies", []) or []
    favorite_foods = preferences.get("favorite_foods", []) or []
    disliked_foods = preferences.get("disliked_foods", []) or []
    preferred_cuisines = preferences.get("preferred_cuisines", []) or []

    return f"""
Known User Profile:
- Allergies: {', '.join(allergies) if allergies else 'None'}
- Favorite foods: {', '.join(favorite_foods) if favorite_foods else 'None'}
- Disliked foods: {', '.join(disliked_foods) if disliked_foods else 'None'}
- Preferred cuisines: {', '.join(preferred_cuisines) if preferred_cuisines else 'None'}

Safety rule:
- Never suggest foods containing the user's allergies.
- If asked for a recommendation that includes an allergen, propose safer alternatives.
"""

def chat_with_ai(user_id, user_message):

    profile = get_user_profile(user_id)

    extracted_preferences = extract_preferences(
        user_message,
        conversation_history=get_conversation(user_id),
        existing_allergies=profile.get("preferences", {}).get("allergies", [])
    )

    update_user_preferences(
        user_id,
        extracted_preferences,
        source_message=user_message
    )

    conversation = get_conversation(user_id)

    messages = [
        {
            "role": "system",
            "content": f"{SYSTEM_PROMPT}\n{_build_profile_context(profile)}"
        }
    ]

    messages.extend(conversation)

    messages.append({
        "role": "user",
        "content": user_message
    })

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages
    )

    ai_response = response.choices[0].message.content

    add_message(user_id, "user", user_message)

    add_message(user_id, "assistant", ai_response)

    return {
        "response": ai_response,
        "extracted_preferences": extracted_preferences
    }
