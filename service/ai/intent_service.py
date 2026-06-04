def detect_intent(message: str):

    stripped = message.strip()
    lower_message = message.lower()

    # single-letter option selection (A, B, C, D, E)
    if stripped.upper() in {"A", "B", "C", "D", "E"}:
        return "select"

    # modification intent should take precedence when the user mentions removal or changes
    if any(word in lower_message for word in [
        "remove", "change", "add more", "extra"
    ]):
        return "modify"

    # ordering intent
    if any(word in lower_message for word in [
        "want", "crave", "hungry", "order", "eat"
    ]):
        return "order"

    # selection intent
    if any(word in lower_message for word in [
        "option a", "option b", "option c", "option d", "option e",
        "i choose", "select", "go with", "choose"
    ]):
        return "select"

    # cart intent
    if any(word in lower_message for word in [
        "cart", "checkout", "confirm", "place order", "yes", "confirm order"
    ]):
        return "checkout"

    return "chat"
