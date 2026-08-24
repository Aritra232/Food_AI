# Food AI

Food AI is a personalized AI food-ordering assistant. The backend uses MongoDB as
the source of truth for restaurants, food items, variations, extras, user
preferences, chat memory, cart sessions, interactions, and final orders.

The AI layer does not invent catalog data. It extracts intent and filters from
natural language, the backend queries MongoDB, safety filters remove unsuitable
food items, and the AI explains the valid results conversationally.

Allergy handling is persistent and safety-focused. When a user says something
like "I am allergic to peanuts", the AI expands that into hidden safety terms
such as related ingredient names and menu wording. Those terms are stored in
`user_preferences.allergy_terms`, and the backend filters matching food items
before the AI explains recommendations.

## Core Flow

```text
user message
-> load persistent user preferences
-> extract intent, filters, instructions, preference updates
-> query restaurants and food_items from MongoDB
-> remove allergy and dietary conflicts
-> rank valid food items
-> AI explains the real options
-> save conversation, interaction, and cart state
```

## Main Collections

- `restaurants`: restaurant profile, location, delivery fee, availability.
- `food_items`: real menu food items used for recommendation.
- `food_item_variations`: sizes or versions for food items.
- `food_item_extras`: valid add-ons connected to food items.
- `user_preferences`: long-term personalization and hard allergy restrictions.
- `ai_conversations`: chat/session records.
- `ai_messages`: individual user and assistant messages with structured data.
- `ai_cart_sessions`: active AI-assisted cart while the user is chatting.
- `user_food_interactions`: recommended, accepted, rejected, ordered, favorited.
- `orders`: finalized checkout records and order status.

Legacy collections such as `menus`, `conversations`, `chat_sessions`, and `cart`
are kept readable for compatibility while the app moves to the cleaner model.

## Tech Stack

- Python
- FastAPI
- Pydantic
- MongoDB
- Anthropic Claude
- OpenAI key available for future embeddings/search work
- Streamlit frontend

Pinecone is no longer required by the active backend flow.

## Running

Install dependencies:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Start the API:

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8001
```

Start the Streamlit UI:

```powershell
streamlit run app_streamlit.py
```

## AI Model Settings

The chat service uses Claude first by default, then OpenAI as a fallback if
Claude fails. You can control this from `.env`:

```env
FOOD_AI_PROVIDER=auto
CLAUDE_MODEL=your_claude_model
OPENAI_MODEL=your_openai_model
```

Allowed `FOOD_AI_PROVIDER` values:

- `auto`: try Claude first, then OpenAI.
- `claude`: prefer Claude.
- `openai`: prefer OpenAI.

## Important Endpoints

Swagger is organized into these simple sections:

- `System`: check if the API is running.
- `AI Chat`: send messages and load chat history.
- `Add Data`: add restaurant, food, sizes, extras, or bulk catalog data.
- `Find Food`: search restaurants, food, sizes, extras, and food options.
- `User Memory`: save/read allergies, dietary rules, and preferences.
- `Cart & Orders`: add to cart, save instructions, checkout, and track orders.

Main endpoints:

- `POST /chat`: main AI chat and ordering endpoint.
- `GET /chat-history`: list and load conversations.
- `GET /user-preferences`: read long-term preferences.
- `PATCH /user-preferences`: update preferences and allergies.
- `POST /restaurants`: add a restaurant to MongoDB.
- `POST /food-items`: add a food item to MongoDB.
- `POST /food-item-variations`: add size/version options.
- `POST /food-item-extras`: add extras connected to a food item.
- `POST /catalog/import`: add restaurants, food items, sizes, and extras together.
- `GET /food-items`: search safe food items.
- `POST /cart/items`: add a food item to an AI cart session.
- `GET /cart`: view active AI cart session.
- `POST /checkout`: convert the AI cart session into an order.
- `GET /orders`: list finalized orders.

Legacy endpoints used by the Streamlit UI still exist, but they are hidden from
Swagger so the API documentation stays simple.

## Example Catalog Input

For real data entry, add a restaurant first, copy its returned Mongo `_id`, then
use that value as the food item's `restaurant_id`.

`POST /restaurants`:

```json
{
  "name": "Pizza House",
  "category": "Italian",
  "description": "Fresh pizza and pasta",
  "address": "Gulshan, Dhaka",
  "latitude": 23.8103,
  "longitude": 90.4125,
  "delivery_fee": 60,
  "is_active": true
}
```

Copy the returned `_id`, for example `68aad9f351cb98228ad1d95`.

`POST /food-items`:

```json
{
  "restaurant_id": "PASTE_RESTAURANT_MONGO_ID_HERE",
  "name": "Spicy Chicken Pasta",
  "description": "Creamy pasta with chicken and chili",
  "category": "Pasta",
  "base_price": 450,
  "spice_level": "spicy",
  "tags": ["pasta", "spicy"],
  "ingredients": ["pasta", "chicken", "cream", "chili"],
  "is_available": true
}
```
