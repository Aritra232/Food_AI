import json
import os
import re

from anthropic import Anthropic
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

CLAUDE_MODEL = (os.getenv("CLAUDE_MODEL") or "claude-3-5-sonnet-latest").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
AI_PROVIDER = (os.getenv("FOOD_AI_PROVIDER") or "auto").strip().lower()

claude_client = Anthropic(api_key=os.getenv("CLAUDE_API_KEY")) if os.getenv("CLAUDE_API_KEY") else None
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None

DEFAULT_INTERPRETATION = {
    "intent": "general_chat",
    "next_step": "",
    "filters": {
        "query": "",
        "category": "",
        "min_price": None,
        "max_price": None,
        "spice_level": "",
        "dietary": [],
        "restaurant_id": "",
    },
    "preference_updates": {
        "allergies": [],
        "remove_allergies": [],
        "dietary_preferences": [],
        "disliked_ingredients": [],
        "preferred_cuisines": [],
        "preferred_spice_levels": [],
        "typical_min_budget": None,
        "typical_max_budget": None,
        "special_preferences": [],
    },
    "cart_action": {
        "operation": "",
        "food_item_id": "",
        "food_name": "",
        "quantity": 1,
        "target_quantity": None,
        "variation_id": "",
        "extra_ids": [],
    },
    "cart_actions": [],
    "special_instructions": "",
}

ALLOWED_INTENTS = {
    "recommend_food",
    "add_to_cart",
    "confirm_food",
    "confirm_addon",
    "decline_addon",
    "add_special_instruction",
    "update_cart",
    "checkout",
    "order_status",
    "general_chat",
}


def _json_from_text(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _deep_merge_defaults(value, defaults):
    value = value if isinstance(value, dict) else {}
    merged = {}
    for key, default_value in defaults.items():
        if isinstance(default_value, dict):
            merged[key] = _deep_merge_defaults(value.get(key), default_value)
        else:
            merged[key] = value.get(key, default_value)
    return merged


def _normalize_interpretation(parsed, original_message):
    normalized = _deep_merge_defaults(parsed, DEFAULT_INTERPRETATION)
    if normalized["intent"] not in ALLOWED_INTENTS:
        normalized["intent"] = "general_chat"
    if not normalized["filters"].get("query"):
        normalized["filters"]["query"] = original_message
    try:
        normalized["cart_action"]["quantity"] = max(1, int(normalized["cart_action"].get("quantity") or 1))
    except Exception:
        normalized["cart_action"]["quantity"] = 1
    actions = normalized.get("cart_actions")
    normalized["cart_actions"] = actions if isinstance(actions, list) else []
    cleaned_actions = []
    for action in normalized["cart_actions"]:
        if not isinstance(action, dict):
            continue
        merged_action = _deep_merge_defaults(action, DEFAULT_INTERPRETATION["cart_action"])
        try:
            merged_action["quantity"] = max(1, int(merged_action.get("quantity") or 1))
        except Exception:
            merged_action["quantity"] = 1
        cleaned_actions.append(merged_action)
    normalized["cart_actions"] = cleaned_actions
    if not normalized["cart_actions"] and normalized["cart_action"].get("operation"):
        normalized["cart_actions"] = [normalized["cart_action"]]
    return normalized


def _call_claude_json(system_prompt, prompt, max_tokens=900):
    if not claude_client:
        return None
    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": json.dumps(prompt)}],
    )
    return _json_from_text(response.content[0].text)


def _call_openai_json(system_prompt, prompt, max_tokens=900):
    if not openai_client:
        return None
    response = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(prompt)},
        ],
    )
    return _json_from_text(response.choices[0].message.content)


def _call_claude_text(system_prompt, prompt, max_tokens=900, temperature=0.4):
    if not claude_client:
        return None
    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": json.dumps(prompt)}],
    )
    return response.content[0].text.strip()


def _call_openai_text(system_prompt, prompt, max_tokens=900, temperature=0.4):
    if not openai_client:
        return None
    response = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(prompt)},
        ],
    )
    return response.choices[0].message.content.strip()


def _model_order():
    if AI_PROVIDER == "openai":
        return ("openai", "claude")
    if AI_PROVIDER == "claude":
        return ("claude", "openai")
    return ("claude", "openai")


def _call_json(system_prompt, prompt, max_tokens=900):
    for provider in _model_order():
        try:
            if provider == "claude":
                parsed = _call_claude_json(system_prompt, prompt, max_tokens=max_tokens)
            else:
                parsed = _call_openai_json(system_prompt, prompt, max_tokens=max_tokens)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


def _call_text(system_prompt, prompt, max_tokens=900, temperature=0.4):
    for provider in _model_order():
        try:
            if provider == "claude":
                text = _call_claude_text(system_prompt, prompt, max_tokens=max_tokens, temperature=temperature)
            else:
                text = _call_openai_text(system_prompt, prompt, max_tokens=max_tokens, temperature=temperature)
            if text:
                return text
        except Exception:
            continue
    return None


def _fallback_interpret(message):
    # This is intentionally conservative. Natural-language understanding belongs
    # to the AI model; when no model is available we avoid mutating preferences
    # or cart state from brittle keyword guesses.
    return {
        "intent": "general_chat",
        "filters": {"query": message},
        "preference_updates": {},
        "cart_action": {
            "operation": "",
            "food_name": "",
            "quantity": 1,
            "target_quantity": None,
        },
        "cart_actions": [],
        "next_step": "",
        "special_instructions": "",
    }


def interpret_message(message, user_preferences=None, recent_messages=None, cart=None, current_step=None):
    system_prompt = """You convert food-ordering chat into safe structured JSON.

Return ONLY valid JSON with this shape:
{
  "intent": "recommend_food|confirm_food|confirm_addon|decline_addon|add_special_instruction|update_cart|checkout|order_status|general_chat",
  "next_step": "",
  "filters": {
    "query": "",
    "category": "",
    "min_price": null,
    "max_price": null,
    "spice_level": "",
    "dietary": [],
    "restaurant_id": ""
  },
  "preference_updates": {
    "allergies": [],
    "remove_allergies": [],
    "dietary_preferences": [],
    "disliked_ingredients": [],
    "preferred_cuisines": [],
    "preferred_spice_levels": [],
    "typical_min_budget": null,
    "typical_max_budget": null,
    "special_preferences": []
  },
  "cart_action": {
    "operation": "add|remove|set_quantity|increase_quantity|decrease_quantity|",
    "food_item_id": "",
    "food_name": "",
    "quantity": 1,
    "target_quantity": null,
    "variation_id": "",
    "extra_ids": []
  },
  "cart_actions": [
    {
      "operation": "add|remove|set_quantity|increase_quantity|decrease_quantity",
      "food_item_id": "",
      "food_name": "",
      "quantity": 1,
      "target_quantity": null,
      "variation_id": "",
      "extra_ids": []
    }
  ],
  "special_instructions": ""
}

Rules:
- Allergies are hard safety restrictions and must go in preference_updates.allergies.
- If the user explicitly removes an allergy, put it in remove_allergies.
- Do not invent food ids, restaurant ids, extras, prices, or availability.
- If the user asks for food, set intent recommend_food and put searchable words in filters.query.
- Use semantic meaning and conversation context, not exact phrase matching.
- If the user accepts a recommended main food, set intent confirm_food.
- If the user accepts a suggested dessert, drink, side, sauce, extra, or add-on, set intent confirm_addon.
- If the user declines suggested dessert, drink, side, sauce, extra, or add-on, set intent decline_addon and next_step special_instruction.
- If the user requests an additional cart item after cart/instruction flow, set intent update_cart and cart_action.operation add or increase_quantity.
- If the user requests that a cart item be removed, set intent update_cart and cart_action.operation remove.
- If the user requests a quantity change, set intent update_cart and cart_action.operation set_quantity. Put the final amount in target_quantity.
- If one message contains multiple cart changes or multiple foods, return every requested change in cart_actions. Also set cart_action to the first action for compatibility.
- Include food_name when the user mentions a food by name or clearly refers to a specific cart/recommended item.
- Include quantity when the user states how many items to add/remove, and target_quantity when they state the final desired quantity.
- Multiple restaurants are allowed only when the backend can verify they are near the user's location; still extract every food request and let the backend validate restaurant distance.
- If the user gives customization notes about ingredients, spice level, temperature, preparation, substitutions, exclusions, packaging, or delivery handling, set intent add_special_instruction and preserve the user's intended meaning in special_instructions.
- If the message is ambiguous, choose general_chat instead of guessing a cart mutation."""

    prompt = {
        "user_message": message,
        "known_user_preferences": user_preferences or {},
        "recent_messages": recent_messages or [],
        "current_cart": cart or {},
        "current_step": current_step or "",
        "context_rules": [
            "If current_step is suggesting_addons and user accepts, use confirm_addon.",
            "If current_step is suggesting_addons and user declines, use decline_addon.",
            "If current_step is awaiting_instruction and user gives notes, use add_special_instruction.",
            "Use recent assistant recommendations and current cart to resolve references like this one, the first one, another one, or the dessert.",
            "For cart changes, return the user's intended operation in cart_action/cart_actions but do not invent ids.",
        ],
    }

    parsed = _call_json(system_prompt, prompt, max_tokens=900)
    if isinstance(parsed, dict):
        normalized = _normalize_interpretation(parsed, message)
        if current_step == "suggesting_addons" and normalized["intent"] == "confirm_food":
            normalized["intent"] = "confirm_addon"
        if current_step == "awaiting_instruction" and normalized["intent"] == "general_chat":
            normalized["intent"] = "add_special_instruction"
            normalized["special_instructions"] = normalized.get("special_instructions") or message
        return normalized

    fallback = _normalize_interpretation(_fallback_interpret(message), message)
    if current_step == "suggesting_addons" and fallback["intent"] == "confirm_food":
        fallback["intent"] = "confirm_addon"
    if current_step == "awaiting_instruction" and fallback["intent"] == "general_chat":
        fallback["intent"] = "add_special_instruction"
        fallback["special_instructions"] = message
    return fallback


def explain_recommendations(message, recommendations, user_preferences=None):
    recommendations = recommendations or []
    if not recommendations:
        return "I could not find a matching safe food item from the available restaurant data right now."

    safe_payload = [
        {
            "food_item_id": item.get("food_item_id"),
            "name": item.get("name"),
            "restaurant_name": item.get("restaurant_name"),
            "category": item.get("category"),
            "base_price": item.get("base_price"),
            "spice_level": item.get("spice_level"),
            "tags": item.get("tags"),
            "distance_km": item.get("distance_km"),
        }
        for item in recommendations[:5]
    ]

    system_prompt = """You are a concise food-ordering assistant.
Use only the provided food items. Never invent restaurants, prices, availability, variations, or extras.
Mention allergy/dietary safety only as based on the already-filtered candidate list."""

    prompt = {
        "user_message": message,
        "user_preferences": user_preferences or {},
        "available_safe_food_items": safe_payload,
        "task": "Recommend the best options conversationally. Include food name, restaurant, price, and a short reason.",
    }

    text = _call_text(system_prompt, prompt, max_tokens=900, temperature=0.4)
    if text:
        return text

    lines = []
    for index, item in enumerate(safe_payload, start=1):
        lines.append(
            f"{index}. {item['name']} from {item.get('restaurant_name') or 'the restaurant'} "
            f"for {item.get('base_price', 0):.2f}."
        )
    return "Here are safe matching food items from the database:\n" + "\n".join(lines)


def general_chat_reply(message, user_preferences=None, cart=None):
    system_prompt = """You are a helpful AI food-ordering assistant.
Keep answers brief. Do not invent menu items, prices, restaurants, order statuses, or availability.
If the user wants recommendations, ask for the food, cuisine, budget, or dietary need."""
    prompt = {
        "user_message": message,
        "user_preferences": user_preferences or {},
        "current_cart": cart or {},
    }
    text = _call_text(system_prompt, prompt, max_tokens=500, temperature=0.4)
    return text or "I can help you find food, remember preferences, and build an order. What would you like today?"


def expand_allergy_terms(allergies):
    allergies = [str(item).strip() for item in (allergies or []) if str(item).strip()]
    if not allergies:
        return []

    system_prompt = """You expand food allergies into ingredient search terms for a food-ordering safety filter.

Return ONLY valid JSON:
{
  "terms": []
}

Rules:
- Include the original allergy words.
- Include common ingredient names, synonyms, and menu wording that may indicate the allergen.
- Include plural/singular forms when useful.
- Do not include unrelated foods.
- Be conservative but safety-focused.
- Do not explain."""

    prompt = {
        "allergies": allergies,
        "examples": {
            "peanut": ["peanut", "peanuts", "groundnut", "groundnuts", "nut", "nuts"],
            "dairy": ["dairy", "milk", "cream", "cheese", "butter", "yogurt"],
            "shellfish": ["shellfish", "shrimp", "prawn", "crab", "lobster"],
        },
    }

    parsed = _call_json(system_prompt, prompt, max_tokens=350)
    terms = []
    if isinstance(parsed, dict) and isinstance(parsed.get("terms"), list):
        terms = [str(item).strip().lower() for item in parsed["terms"] if str(item).strip()]

    if not terms:
        # Safety fallback when the model/API is unavailable.
        fallback = {
            "peanut": ["peanut", "peanuts", "groundnut", "groundnuts", "nut", "nuts"],
            "nut": ["nut", "nuts", "peanut", "peanuts", "almond", "cashew", "walnut"],
            "dairy": ["dairy", "milk", "cream", "cheese", "butter", "yogurt"],
            "shellfish": ["shellfish", "shrimp", "prawn", "crab", "lobster"],
            "gluten": ["gluten", "wheat", "flour", "bread"],
            "egg": ["egg", "eggs"],
            "soy": ["soy", "soya"],
        }
        for allergy in allergies:
            key = allergy.lower()
            terms.extend(fallback.get(key, [key]))

    combined = []
    seen = set()
    for term in allergies + terms:
        cleaned = str(term).strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        combined.append(cleaned)
    return combined


def order_status_reply(order):
    if not order:
        return "I could not find that order. Please share a valid order id."
    return (
        f"Your order is currently {order.get('status', 'being processed')}. "
        f"Estimated delivery time: {order.get('estimated_delivery_time', 'not available yet')}."
    )
