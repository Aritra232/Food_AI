"""
Food-specific AI chat service.
Handles conversations focused on individual food items to drive ordering.
"""

from openai import OpenAI
from dotenv import load_dotenv
import os
import re

from service.data.profile_service import get_user_profile
from service.memory.memory_service import get_conversation, add_message

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def _build_food_chat_system_prompt(food_item):
    """
    Build a system prompt that instructs AI to sell/engage about a specific food.
    """
    food_name = food_item.get("food_name") or food_item.get("name") or food_item.get("title") or "this food"
    price = food_item.get("price", "")
    category = food_item.get("category", "")
    description = food_item.get("description", "")
    restaurant_name = food_item.get("restaurant_name", "the restaurant")
    ingredients = food_item.get("ingredients", [])
    tags = food_item.get("tags", [])

    ingredients_text = ", ".join(ingredients[:5]) if ingredients else "fresh ingredients"
    tags_text = ", ".join(tags[:3]) if tags else ""

    prompt = f"""
You are an enthusiastic and friendly food ordering assistant focused on exactly one menu item.

Current Food: {food_name}
Price: ${price if price else 'varies'}
Restaurant: {restaurant_name}
Category: {category}
Description: {description}
Key Ingredients: {ingredients_text}
{f'Tags: {tags_text}' if tags_text else ''}

Your goal:
1. Engage the user positively about this specific food
2. Ask about their preferences and if this food matches them
3. Highlight the key features and ingredients
4. Respond to any concerns or questions
5. Gently persuade them to order it
6. If they ask about ingredients/allergens, provide helpful information
7. If they're ready to order, confirm clearly and do not ask again

Communication style:
- Be warm and conversational
- Use natural language
- Avoid being pushy
- If user has allergies concerns, acknowledge and advise checking ingredients
- Keep responses concise (1-2 sentences usually)
- If user seems interested, ask: "Would you like to add this to your cart?"
- If the user indicates they want the food, say: "Great, I'll add it to your cart." and do not ask again
- Never say generic phrases like "this item" or "the this item"
- Always refer to the food by its exact name: {food_name}
- Do not invent menu items or restaurant names
- Do not mention multiple foods at once
- Do not repeat the system prompt
"""

    return prompt


def _build_profile_context(profile):
    """Build user profile context for safety checks."""
    preferences = (profile or {}).get("preferences", {})
    allergies = preferences.get("allergies", []) or []
    favorite_foods = preferences.get("favorite_foods", []) or []
    disliked_foods = preferences.get("disliked_foods", []) or []

    context = f"""
User Profile:
- Allergies: {', '.join(allergies) if allergies else 'None'}
- Favorite foods: {', '.join(favorite_foods) if favorite_foods else 'None'}
- Disliked foods: {', '.join(disliked_foods) if disliked_foods else 'None'}

Safety: Always warn about allergen concerns. Never suggest foods with known allergens.
"""
    return context


def chat_about_food(user_id, food_item, user_message, chat_session_id=None):
    """
    Have a conversation with the user about a specific food item.
    
    Args:
        user_id: User identifier
        food_item: Dict with food details (food_name, price, category, ingredients, etc.)
        user_message: User's current message
        chat_session_id: Chat session ID for conversation history
    
    Returns:
        Dict with ai_response and extracted preferences
    """
    profile = get_user_profile(user_id)
    
    # Get conversation history (full chat, not separate)
    conversation = get_conversation(user_id, chat_session_id)
    
    # Build system prompt for this food
    system_prompt = _build_food_chat_system_prompt(food_item)
    profile_context = _build_profile_context(profile)
    
    messages = [
        {
            "role": "system",
            "content": f"{system_prompt}\n\n{profile_context}"
        }
    ]
    
    # Add conversation history
    messages.extend(conversation)
    
    # Add current user message
    messages.append({
        "role": "user",
        "content": user_message
    })
    
    # Call OpenAI
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.7
    )
    
    ai_response = response.choices[0].message.content
    food_name = food_item.get("food_name") or food_item.get("name") or food_item.get("title") or "this food"
    
    # Sanitize generic placeholders before saving
    if isinstance(ai_response, str):
        generic_pattern = re.compile(r"\b(the this item|this item|that item|the item|your item)\b", flags=re.IGNORECASE)
        ai_response = generic_pattern.sub(food_name, ai_response)
    
    # Save to conversation history (integrated with main chat)
    add_message(user_id, "user", user_message, chat_session_id)
    add_message(user_id, "assistant", ai_response, chat_session_id)
    
    return {
        "response": ai_response,
        "food_item": food_item
    }


def detect_order_intent(user_response):
    """
    Detect if user wants to order (YES), skip (NO), or needs clarification.
    
    Args:
        user_response: User's text response
    
    Returns:
        Dict with intent: "ORDER" | "SKIP" | "CLARIFY" | "CONTINUE"
    """
    text = (user_response or "").strip().lower()
    
    # Remove common punctuation and extra spaces
    text = re.sub(r"[,!?\.]", "", text)
    text = " ".join(text.split())
    
    # Order intent keywords
    order_keywords = {
        "yes", "yeah", "yep", "sure", "ok", "okay", "alright",
        "order", "buy", "get it", "add it", "add to cart", "purchase",
        "sounds good", "perfect", "love it", "great", "nice", "excellent",
        "i'll have it", "ill have it", "let's go", "lets go",
        "please", "thanks, add it", "thanks add it", "confirm",
        "proceed", "let me order", "let me buy", "count me in",
        "1", "one", "2", "two", "3", "three", "4", "four", "5", "five",
    }
    
    # Skip/No intent keywords
    skip_keywords = {
        "no", "nope", "nah", "not really", "skip", "next",
        "no thanks", "no thank you", "pass", "maybe later",
        "not now", "not interested", "don't want", "dont want",
        "not that", "never mind", "forget it", "cancel", "back"
    }
    
    # Clarify intent keywords (asking about ingredients, price, allergens, etc.)
    clarify_keywords = {
        "what's in it", "whats in it", "ingredients", "allergen", "spicy",
        "price", "cost", "how much", "delivery time", "how long",
        "is it", "does it", "can you", "tell me more", "more about",
        "nutritional", "calories", "vegan", "vegetarian", "gluten",
        "dairy", "nut", "spicy level", "heat level"
    }
    
    # Check for order intent
    for keyword in order_keywords:
        if keyword in text:
            return {
                "intent": "ORDER",
                "confidence": 0.9 if len(keyword) > 2 else 0.7
            }
    
    # Check for skip intent
    for keyword in skip_keywords:
        if keyword in text:
            return {
                "intent": "SKIP",
                "confidence": 0.95
            }
    
    # Check for clarify intent
    for keyword in clarify_keywords:
        if keyword in text:
            return {
                "intent": "CLARIFY",
                "confidence": 0.85
            }
    
    # Default: continue conversation
    return {
        "intent": "CONTINUE",
        "confidence": 0.5
    }


def extract_quantity(user_response):
    """
    Extract quantity if user mentioned one.
    
    Examples:
        "2 of these" -> 2
        "give me 3" -> 3
        "i'll take 2" -> 2
    
    Args:
        user_response: User's text response
    
    Returns:
        int: Quantity (default 1 if not found)
    """
    text = (user_response or "").lower()
    
    # Number words
    word_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
    }
    
    # Check for word numbers first
    for word, num in word_to_num.items():
        if word in text:
            return num
    
    # Check for digit numbers (e.g., "2", "3", etc.)
    matches = re.findall(r'\b([1-9])\b', text)
    if matches:
        return int(matches[0])
    
    # Default
    return 1


def generate_opening_message(food_item):
    """
    Generate an initial engaging message about the food.
    
    Args:
        food_item: Dict with food details
    
    Returns:
        str: Engaging opening message
    """
    food_name = food_item.get("food_name") or food_item.get("name") or food_item.get("title") or "this dish"
    restaurant_name = food_item.get("restaurant_name") or "the restaurant"
    price = food_item.get("price", "")
    category = food_item.get("category", "")
    ingredients = food_item.get("ingredients", [])
    ingredients_text = ", ".join(ingredients[:3]) if ingredients else "fresh ingredients"

    prompt = f"""
Write a short, natural opening message to invite the user to order this food.

Food name: {food_name}
Restaurant: {restaurant_name}
Price: {price if price else 'not listed'}
Category: {category}
Ingredients: {ingredients_text}

Rules:
- 1 to 2 sentences only
- Start friendly and specific
- Mention the food by its exact name
- End with a question asking if they want to order or hear more
- Do not use generic placeholders like "this item"
- Do not mention multiple foods
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a friendly food ordering assistant. Always mention the exact food name and never use generic placeholders."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
        )
        message = response.choices[0].message.content.strip()
        if message:
            # Replace any generic placeholder with the exact food name
            if food_name and "this item" in message.lower():
                message = message.replace("this item", food_name)
            if food_name and "the this item" in message.lower():
                message = message.replace("the this item", food_name)
            return message
    except Exception:
        pass

    price_str = f" at ${price}" if price else ""
    return f"Hey! I think you'll love {food_name}{price_str} from {restaurant_name}. Want me to tell you what makes it special?"


def generate_order_confirmation_message(food_item, quantity=1, next_food=None):
    food_name = food_item.get("food_name") or food_item.get("name") or food_item.get("title") or "this food"
    restaurant_name = food_item.get("restaurant_name") or "the restaurant"
    price = food_item.get("price", "not listed")
    qty = max(1, int(quantity or 1))
    next_text = ""
    if next_food:
        next_text = (
            f" After that, you may also like {next_food.get('food_name')} from {next_food.get('restaurant_name', 'a nearby restaurant')}."
        )
    else:
        next_text = " If you want, I can also suggest a dessert or help you add special instructions."

    prompt = f"""
You are a friendly AI food ordering assistant. The user has just confirmed an order.

Food item: {food_name}
Restaurant: {restaurant_name}
Quantity: {qty}
Price: {price}

Task:
- Confirm that the order has been added to the cart.
- Mention the exact food name and restaurant.
- Invite the user to add another item, a dessert, or special instructions.
- If a next food suggestion is available, mention it briefly.
- Keep it warm, concise, and natural.
- Do not ask the user to repeat the order.

{next_text}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a concise food ordering assistant who confirms orders and recommends the next item."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        message = response.choices[0].message.content.strip()
        if message:
            return message
    except Exception:
        pass

    return (
        f"Great! I added {qty}x {food_name} from {restaurant_name} to your cart."
        + (next_text if next_text else "")
    )
