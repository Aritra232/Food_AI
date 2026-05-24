from openai import OpenAI
from dotenv import load_dotenv

import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def format_options(recommendations):

    recommendations = recommendations or []

    options_map = {}
    options_text = ""

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

        options_text += f"""
Option {key}:

Food Name: {item['food_name']}
Price: {item['price']} BDT
Restaurant: {item['restaurant_id']}

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

    dietary_style = user_preferences.get("dietary_style", "") if isinstance(user_preferences, dict) else ""
    dietary_restrictions = user_preferences.get("dietary_restrictions", []) if isinstance(user_preferences, dict) else []
    allergies = user_preferences.get("allergies", []) if isinstance(user_preferences, dict) else []

    prompt = f"""
    Context:
    - The user message is: {user_message}
    - Recommended foods are listed below.
    - The user preferences are: dietary style = {dietary_style or 'none'}; dietary restrictions = {', '.join(dietary_restrictions) or 'none'}; allergies = {', '.join(allergies) or 'none'}.
    - Only recommend the items in the provided list.
    - Explicitly honor the user's diet and allergy preferences in your explanation.

    Recommended Foods:
    {formatted_foods}

    Requirements:
    - Format output using Option A, Option B, Option C
    - Mention why each food matches the user's preferences and taste
    - If the user is vegan or has a dietary restriction, mention that these options comply
    - Keep response concise and user-friendly
    - Sound like a modern AI food assistant
    - Do NOT include internal recommendation scores or irrelevant menu data
    - Do NOT invent additional items beyond the list provided
    """

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": """
                You are an intelligent AI food assistant.
                """
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
