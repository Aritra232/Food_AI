from anthropic import Anthropic
from dotenv import load_dotenv

import os

from service.data.database_service import restaurant_collection

load_dotenv()

client = Anthropic(
    api_key=os.getenv("CLAUDE_API_KEY")
)


def _build_restaurant_name_map(recommendations):
    restaurant_ids = []
    seen = set()

    for item in recommendations or []:
        rid = str(item.get("restaurant_id", "")).strip()
        if not rid or rid in seen:
            continue
        seen.add(rid)
        restaurant_ids.append(rid)

    if not restaurant_ids:
        return {}

    cursor = restaurant_collection.find(
        {"restaurant_id": {"$in": restaurant_ids}},
        {"restaurant_id": 1, "name": 1, "restaurant_name": 1}
    )

    name_map = {}
    for doc in cursor:
        rid = str(doc.get("restaurant_id", "")).strip()
        if not rid:
            continue
        name = str(doc.get("name") or doc.get("restaurant_name") or rid).strip()
        name_map[rid] = name

    return name_map


def format_options(recommendations):

    recommendations = recommendations or []

    options_map = {}
    options_text = ""
    restaurant_name_map = _build_restaurant_name_map(recommendations)

    labels = ["A", "B", "C", "D", "E"]

    for i, item in enumerate(recommendations):

        if i >= len(labels):
            break

        key = labels[i]

        options_map[key] = {
            "menu_id": f"M{str(i+1).zfill(3)}",
            "_id": item["_id"],
            "restaurant_id": item["restaurant_id"]
        }

        restaurant_id = str(item.get("restaurant_id", "")).strip()
        restaurant_name = restaurant_name_map.get(restaurant_id, restaurant_id or "Unknown")

        options_text += f"""
Option {key}:

Food Name: {item['food_name']}
Price: {item['price']} BDT
    Restaurant: {restaurant_name}

"""

    return options_text, options_map


def generate_recommendation_response(
    user_message,
    recommendations,
    user_preferences=None
):
    """
    Generate recommendation response using Claude for superior natural language.
    Claude produces more engaging, contextually-aware recommendations.
    """
    recommendations = recommendations or []

    if not recommendations:
        return {
            "response": "I could not find any matching food right now. Try a different food name or search again.",
            "options": {}
        }

    formatted_foods, options = format_options(
        recommendations
    )
    option_labels = ", ".join([f"Option {label}" for label in options.keys()]) or "Option A"

    dietary_style = user_preferences.get("dietary_style", "") if isinstance(user_preferences, dict) else ""
    dietary_restrictions = user_preferences.get("dietary_restrictions", []) if isinstance(user_preferences, dict) else []
    allergies = user_preferences.get("allergies", []) if isinstance(user_preferences, dict) else []

    system_prompt = """You are a friendly, knowledgeable AI food recommendation assistant. Your recommendations are helpful, personalized, and safe.

Guidelines:
- Always mention every available option
- For each option, include the food name, restaurant, and a brief reason why it fits the user
- Never invent menu items, prices, or restaurants
- If the user has allergies or dietary restrictions, reassure them that these options are safe
- Be warm, conversational, and decision-helpful
- Keep it concise (2-3 sentences per option max)
- Focus on why each option is good for THIS user specifically"""

    prompt = f"""The user said: "{user_message}"

Their preferences:
- Dietary style: {dietary_style or 'None specified'}
- Dietary restrictions: {', '.join(dietary_restrictions) if dietary_restrictions else 'None'}
- Allergies: {', '.join(allergies) if allergies else 'None'}

Available options:
{formatted_foods}

Create a friendly recommendation response. Mention {option_labels}. Explain why each option fits their needs. Be personal but concise."""

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
        temperature=0.7
    )

    return {
        "response": response.content[0].text,
        "options": options
    }
