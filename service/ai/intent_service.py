from service.ai.claude_service import chat_with_claude


def _detect_intent_with_claude(message: str):
    if not message or not message.strip():
        return "chat"

    prompt = f"""You are an intent classification assistant for a food ordering conversational system.
Read the user message and classify it into exactly one of these intents:
- select
- modify
- order
- checkout
- chat

Return ONLY the intent label with no extra text.

User message:
""" + message.strip() + """
"""

    messages = [
        {
            "role": "user",
            "content": prompt
        }
    ]

    try:
        result = chat_with_claude(
            messages=messages,
            system_prompt="You are a concise classifier that returns only one of the allowed intent labels.",
            temperature=0,
            max_tokens=16
        )
        if result and isinstance(result, str):
            intent = result.strip().lower()
            if intent in {"select", "modify", "order", "checkout", "chat"}:
                return intent
    except Exception:
        pass

    return None


def _detect_intent_fallback(message: str):
    stripped = message.strip()
    lower_message = message.lower()

    if stripped.upper() in {"A", "B", "C", "D", "E"}:
        return "select"

    if any(word in lower_message for word in [
        "remove", "change", "add more", "extra"
    ]):
        return "modify"

    if any(word in lower_message for word in [
        "want", "crave", "hungry", "order", "eat"
    ]):
        return "order"

    if any(word in lower_message for word in [
        "option a", "option b", "option c", "option d", "option e",
        "i choose", "select", "go with", "choose"
    ]):
        return "select"

    if any(word in lower_message for word in [
        "cart", "checkout", "confirm", "place order", "yes", "confirm order"
    ]):
        return "checkout"

    return "chat"


def detect_intent(message: str):
    intent = _detect_intent_with_claude(message)
    if intent:
        return intent
    return _detect_intent_fallback(message)
