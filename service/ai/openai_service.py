from dotenv import load_dotenv
import os

from service.memory.memory_service import (
    get_conversation,
    add_message
)

from service.ai.preference_extraction_service import extract_preferences
from service.ai.claude_service import chat_with_claude_for_food_assistant
from service.data.profile_service import get_user_profile, update_user_preferences

load_dotenv()


def chat_with_ai(user_id, user_message, chat_session_id=None):
    """
    Main chat endpoint. Uses Claude for superior reasoning and context understanding.
    """
    profile = get_user_profile(user_id)

    # Extract preferences using Claude (better at nuance and context)
    extracted_preferences = extract_preferences(
        user_message,
        conversation_history=get_conversation(user_id, chat_session_id),
        existing_allergies=profile.get("preferences", {}).get("allergies", [])
    )

    # Update profile with extracted preferences
    update_user_preferences(
        user_id,
        extracted_preferences,
        source_message=user_message
    )

    # Get conversation history for context
    conversation = get_conversation(user_id, chat_session_id)

    # Use Claude for chat (better language generation and reasoning)
    ai_response_data = chat_with_claude_for_food_assistant(
        user_id,
        user_message,
        profile,
        conversation
    )

    ai_response = ai_response_data["response"]

    # Save to conversation memory
    add_message(user_id, "user", user_message, chat_session_id)
    add_message(user_id, "assistant", ai_response, chat_session_id)

    return {
        "response": ai_response,
        "extracted_preferences": extracted_preferences
    }
