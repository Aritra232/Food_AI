from openai import OpenAI
from dotenv import load_dotenv

import os

from service.data.database_service import restaurant_collection

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
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

    prompt = f"""
    CRAFT Prompt

    C - Context:
    The user said: {user_message}
    User preferences:
    - Dietary style: {dietary_style or 'none'}
    - Dietary restrictions: {', '.join(dietary_restrictions) or 'none'}
    - Allergies: {', '.join(allergies) or 'none'}

    Recommended foods:
    {formatted_foods}

    R - Role:
    You are a careful AI food assistant that recommends only the items provided.

    A - Audience:
    Write for a user who wants a simple, friendly, decision-ready food recommendation.

    F - Format:
    - Use the option labels exactly as provided: {option_labels}
    - Mention every available option in the list; do not omit later options
    - For each option, include the food name, restaurant name, and one short reason it fits
    - Do not invent new menu items, prices, or restaurants
    - Do not mention internal scores or backend details

    T - Tone:
    Be concise, natural, confident, and helpful.
    If the user's diet or allergies matter, briefly explain why the options are safe or suitable.
    """

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": "You are an intelligent AI food assistant that follows CRAFT instructions exactly."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return {
        "response": response.choices[0].message.content,
        "options": options
    }
