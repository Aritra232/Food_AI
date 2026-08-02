from anthropic import Anthropic
from dotenv import load_dotenv
import os

load_dotenv()

try:
    client = Anthropic(
        api_key=os.getenv("CLAUDE_API_KEY")
    )
except Exception:
    client = None

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")


def chat_with_claude(messages, system_prompt=None, temperature=0.7, max_tokens=2048):
    """
    Generic Claude chat completion.
    
    Args:
        messages: List of {"role": "user"/"assistant", "content": "..."} dicts
        system_prompt: Optional system prompt
        temperature: Model temperature (0-1)
        max_tokens: Max response tokens
    
    Returns:
        str: Claude's response text
    """
    if client is None:
        return "Claude is currently unavailable because the API client could not be initialized."

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system_prompt if system_prompt else "",
        messages=messages,
        temperature=temperature
    )
    
    return response.content[0].text


def extract_preferences_claude(user_message, conversation_history=None, existing_allergies=None):
    """
    Extract food preferences using Claude.
    
    Claude excels at understanding context, nuance, and resolving ambiguous user inputs.
    This is better than OpenAI for preference extraction because Claude can reason
    through complex dietary restrictions and allergy mentions.
    """
    import json
    
    def _expand_user_shorthand(message):
        if not message:
            return ""

        text = str(message)

        prompt = f"""You are a normalization assistant for food preference extraction.
Rewrite the user message by replacing shorthand, abbreviations, slang, alternate spellings, non-English variants, and other informal wording
with canonical terms that a food preference extractor can understand.

Keep the original meaning exactly the same.
Return ONLY the rewritten text, without explanations.

Examples:
- fvrt, favrt, fvt, fav, favorita -> favorite
- dslk, dislk, dlike, don't like, dontlike -> dislike
- algy, allrgy, allergy, allergic -> allergy
- cuis, cuisn, cusine -> cuisine
- dtry -> dietary
- restr, restn, restrn -> restriction
- spcy, spci, spicey -> spicy
- bgt, budgt, bdgt -> budget
- freq, frq -> frequency
- addr, addrs, adress -> address
- brkfst, bf -> breakfast
- lnch, lunc -> lunch
- dinr, dnr -> dinner
- posondo, like, favorita -> favorite
- If a word is already plain English, preserve it.

Original message:
""" + text + """
"""

        normalization_messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        normalized_text = chat_with_claude(
            messages=normalization_messages,
            system_prompt="You are an assistant that rewrites informal user text into normalized English for downstream preference extraction.",
            temperature=0,
            max_tokens=256
        )

        if normalized_text and isinstance(normalized_text, str):
            normalized_text = normalized_text.strip()

        if not normalized_text:
            return text

        return normalized_text
    
    def _build_context_block(history):
        if not history:
            return ""
        recent = history[-6:]
        lines = []
        for msg in recent:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)
    
    normalized_message = _expand_user_shorthand(user_message)
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

    prompt = f"""Extract food preferences from this user message:

Recent conversation context:
{context_block or 'None'}

Existing known allergies:
{allergies_hint or 'None'}

User message:
{normalized_message}

Return JSON in this format:
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

Think carefully. Extract only what the user explicitly mentioned. Use normalized terms."""

    messages = [
        {
            "role": "user",
            "content": prompt
        }
    ]
    
    response_text = chat_with_claude(
        messages=messages,
        system_prompt=system_prompt,
        temperature=0,
        max_tokens=1024
    )
    
    try:
        extracted = json.loads(response_text)
        return extracted
    except:
        # Fallback to empty dict if parsing fails
        return {}


def generate_recommendation_response_claude(user_message, recommendations, user_preferences=None):
    """
    Generate a friendly, personalized recommendation response using Claude.
    
    Claude's superior language generation produces more engaging, contextual responses
    that account for user dietary needs, preferences, and conversation history.
    """
    from service.data.database_service import restaurant_collection
    
    recommendations = recommendations or []
    
    if not recommendations:
        return {
            "response": "I could not find any matching food right now. Try a different food name or search again.",
            "options": {}
        }
    
    # Build restaurant name map
    restaurant_ids = []
    seen = set()
    for item in recommendations:
        rid = str(item.get("restaurant_id", "")).strip()
        if not rid or rid in seen:
            continue
        seen.add(rid)
        restaurant_ids.append(rid)
    
    name_map = {}
    if restaurant_ids:
        cursor = restaurant_collection.find(
            {"restaurant_id": {"$in": restaurant_ids}},
            {"restaurant_id": 1, "name": 1, "restaurant_name": 1}
        )
        for doc in cursor:
            rid = str(doc.get("restaurant_id", "")).strip()
            if rid:
                name = str(doc.get("name") or doc.get("restaurant_name") or rid).strip()
                name_map[rid] = name
    
    # Build options text
    formatted_foods = ""
    options_map = {}
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
        restaurant_name = name_map.get(restaurant_id, restaurant_id or "Unknown")
        
        formatted_foods += f"""
Option {key}: {item['food_name']} ({item['price']} BDT) from {restaurant_name}
"""
    
    dietary_style = user_preferences.get("dietary_style", "") if isinstance(user_preferences, dict) else ""
    dietary_restrictions = user_preferences.get("dietary_restrictions", []) if isinstance(user_preferences, dict) else []
    allergies = user_preferences.get("allergies", []) if isinstance(user_preferences, dict) else []
    
    option_labels = ", ".join([f"Option {label}" for label in options_map.keys()]) or "Option A"
    
    system_prompt = """You are a friendly, knowledgeable AI food recommendation assistant. Your recommendations are helpful, personalized, and safe.

Guidelines:
- Always mention every available option
- For each option, include the food name, restaurant, and a brief reason why it fits the user
- Never invent menu items, prices, or restaurants
- If the user has allergies or dietary restrictions, reassure them that these options are safe
- Be warm, conversational, and decision-helpful
- Keep it concise (2-3 sentences per option max)"""

    prompt = f"""The user asked: "{user_message}"

Their profile:
- Dietary style: {dietary_style or 'None specified'}
- Dietary restrictions: {', '.join(dietary_restrictions) if dietary_restrictions else 'None'}
- Allergies: {', '.join(allergies) if allergies else 'None'}

Available food options:
{formatted_foods}

Create a friendly recommendation response mentioning {option_labels}. Explain why each option fits their preferences. Be personal but concise."""

    messages = [
        {
            "role": "user",
            "content": prompt
        }
    ]
    
    response_text = chat_with_claude(
        messages=messages,
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=1024
    )
    
    return {
        "response": response_text,
        "options": options_map
    }


def chat_with_claude_for_food_assistant(user_id, user_message, profile, conversation_history):
    """
    Main chat function using Claude for natural conversation.
    
    Claude's superior reasoning and context understanding makes it better for:
    - Understanding complex food requests
    - Remembering conversation context
    - Handling follow-up questions naturally
    - Providing personalized responses
    """
    preferences = (profile or {}).get("preferences", {})
    
    allergies = preferences.get("allergies", []) or []
    favorite_foods = preferences.get("favorite_foods", []) or []
    disliked_foods = preferences.get("disliked_foods", []) or []
    preferred_cuisines = preferences.get("preferred_cuisines", []) or []
    
    profile_context = f"""
Known User Profile:
- Allergies: {', '.join(allergies) if allergies else 'None'}
- Favorite foods: {', '.join(favorite_foods) if favorite_foods else 'None'}
- Disliked foods: {', '.join(disliked_foods) if disliked_foods else 'None'}
- Preferred cuisines: {', '.join(preferred_cuisines) if preferred_cuisines else 'None'}

Safety rule:
- Never suggest foods containing the user's allergies.
- If asked for a recommendation that includes an allergen, propose safer alternatives.
"""
    
    system_prompt = f"""You are an AI food ordering assistant for a restaurant delivery app.

Your responsibilities:
- Help users find foods and restaurants
- Suggest personalized recommendations
- Continue conversation naturally
- Remember and respect their dietary needs and allergies
- Be friendly, helpful, and concise

{profile_context}"""
    
    # Convert conversation history to Claude format
    messages = []
    for msg in conversation_history:
        messages.append({
            "role": msg.get("role"),
            "content": msg.get("content")
        })
    
    # Add current user message
    messages.append({
        "role": "user",
        "content": user_message
    })
    
    ai_response = chat_with_claude(
        messages=messages,
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=512
    )
    
    return {
        "response": ai_response
    }
