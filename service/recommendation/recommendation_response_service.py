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
    recommendations
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

    prompt = f"""
    User Message:
    {user_message}

    Recommended Foods:
    {formatted_foods}

    Generate a professional AI food recommendation.

    Requirements:
    - Format output using Option A, Option B, Option C
    - Mention why foods match user taste
    - Mention spicy preference if relevant
    - Keep response concise
    - Sound like a modern AI food assistant
    - Do NOT include internal recommendation scores
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
