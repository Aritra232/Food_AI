# Food AI

Food AI is an AI-powered food discovery and ordering assistant built with Python. It combines conversational recommendations, user preference learning, location-aware restaurant search, cart handling, and order workflows into a single experience.

The project has two main interfaces:
- a FastAPI backend in [main.py](main.py) that exposes REST endpoints for chat, recommendations, search, onboarding, carts, and restaurant requests
- a Streamlit frontend in [app_streamlit.py](app_streamlit.py) that provides a chat-style UI for interacting with the backend

## Features

- Conversational food assistant with chat history and session memory
- Personalized food recommendations based on user profile and preferences
- Allergy and dietary-awareness checks for safer suggestions
- Location-based restaurant and menu discovery
- Semantic search support through Pinecone vector search
- Cart and order-related flows
- Onboarding profile capture and saved delivery addresses
- Restaurant request management for missing restaurants or menu items

## Tech Stack

- Python 3.10+
- FastAPI for the backend API
- Streamlit for the web UI
- MongoDB for persistence
- Anthropic / OpenAI-compatible AI services
- Pinecone for vector embeddings and semantic search
- Requests and python-dotenv for API integration and environment config

## Project Structure

- [main.py](main.py) - FastAPI app and API endpoints
- [app_streamlit.py](app_streamlit.py) - Streamlit frontend and UI state handling
- [service/ai](service/ai) - AI integrations such as chat, embeddings, intent detection, and preference extraction
- [service/business](service/business) - restaurant, location, cart, and order logic
- [service/data](service/data) - MongoDB access and profile persistence
- [service/memory](service/memory) - chat sessions, conversation memory, and option memory
- [service/recommendation](service/recommendation) - recommendation generation and response formatting
- [service/state](service/state) - lightweight conversation state tracking
- [service/vector_db](service/vector_db) - Pinecone vector store integration

## Prerequisites

Before running the project, make sure you have:

- Python installed
- MongoDB running and reachable
- API credentials for the AI services you want to use
- Optional: Pinecone account and index access for semantic search
- Optional: Google Maps API key if you want geocoding/location-based checks

## Environment Variables

Create a file named .env in the project root with values similar to the following:

```env
MONGO_URL=your_mongodb_connection_string
CLAUDE_API_KEY=your_claude_api_key
CLAUDE_MODEL=claude-opus-4-6
OPENAI_API_KEY=your_openai_key
PINECONE_API_KEY=your_pinecone_key
MAPS_API_KEY=your_google_maps_api_key
```

> The application expects MongoDB to be configured before startup. If the environment values are missing, the app will fail to initialize properly.

## Installation

On Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Running the Application

### 1. Start the backend API

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Start the Streamlit UI

In a second terminal:

```powershell
streamlit run app_streamlit.py
```

The Streamlit app expects the backend API to be available at http://127.0.0.1:8000.

## Main API Endpoints

Some of the core endpoints exposed by the backend include:

- GET / - health/home endpoint
- GET /chat-history - fetch chat history and sessions
- POST /chat - send a chat message to the food assistant
- GET /recommend-food - return food recommendations
- GET /available-foods - list nearby available food options
- GET /search-food - keyword search for food items
- GET /semantic-search - semantic search using embeddings
- GET /cart - view the current cart
- POST /profile/onboarding - save onboarding/profile details
- POST /profile/address - save or update delivery address
- POST /add-restaurant - add a restaurant record
- POST /add-menu - add a menu item
- POST /restaurant-request - create a restaurant request

## Notes

- The app uses MongoDB collections such as conversations, chat_sessions, user_profiles, restaurants, menus, cart, orders, and restaurant_requests.
- Pinecone integration is used for semantic item lookup and is expected to be configured before semantic search is used.
- The repo also includes [claude_test.py](claude_test.py), which is a simple Claude API test script for validating API access.

## License

This project is intended for local development and demonstration purposes unless otherwise specified by the repository owner.
