from anthropic import Anthropic

API_KEY = "YOUR_API_KEY"

client = Anthropic(api_key=API_KEY)

# ----------------------------
# List available models
# ----------------------------
print("Available Models:")
print("-" * 50)

try:
    models = client.models.list()

    model_names = []
    for model in models.data:
        model_names.append(model.id)
        print(model.id)

except Exception as e:
    print(f"Could not retrieve models: {e}")
    exit()

print("-" * 50)

# ----------------------------
# Select a model
# ----------------------------
selected_model = input(
    "\nEnter model name (or press Enter for first model): "
).strip()

if not selected_model:
    selected_model = model_names[0]

print(f"\nUsing model: {selected_model}")
print("Type 'exit' to quit.\n")

# ----------------------------
# Chat loop
# ----------------------------
conversation = []

while True:
    user_input = input("You: ")

    if user_input.lower() in ["exit", "quit"]:
        break

    conversation.append({
        "role": "user",
        "content": user_input
    })

    try:
        response = client.messages.create(
            model=selected_model,
            max_tokens=2048,
            messages=conversation
        )

        assistant_reply = response.content[0].text

        print(f"\nClaude: {assistant_reply}\n")

        conversation.append({
            "role": "assistant",
            "content": assistant_reply
        })

    except Exception as e:
        print(f"\nError: {e}\n")