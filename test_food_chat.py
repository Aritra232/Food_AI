#!/usr/bin/env python3
"""
Quick Test Script for Food AI Chat Feature
Run this to test all endpoints
"""

import requests
import json
from pprint import pprint

BASE_URL = "http://127.0.0.1:8000"

# Test data
USER_ID = "user123"
CHAT_SESSION_ID = "test_session_123"
LAT = 23.8103
LNG = 90.4125

# Sample food item (you should get this from recommendations first)
SAMPLE_FOOD_ITEM = {
    "_id": "507f1f77bcf86cd799439011",
    "menu_id": "menu_pasta_001",
    "food_name": "Veggie Italian Pasta",
    "price": 20,
    "category": "Pasta",
    "restaurant_id": "rest_fridays",
    "restaurant_name": "Friday's Food Restaurant",
    "description": "Delicious pasta with fresh vegetables",
    "ingredients": ["pasta", "tomato", "vegetables", "olive oil"],
    "tags": ["vegetarian", "italian", "healthy"]
}

def test_get_recommendations():
    """Test 1: Get food recommendations"""
    print("\n=== TEST 1: Get Recommendations ===")
    response = requests.post(
        f"{BASE_URL}/chat",
        params={
            "user_id": USER_ID,
            "message": "I want pasta",
            "lat": LAT,
            "lng": LNG,
            "chat_session_id": CHAT_SESSION_ID
        }
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    pprint(data)
    return data

def test_open_food_chat(food_item):
    """Test 2: Open food chat (get opening message)"""
    print("\n=== TEST 2: Open Food Chat ===")
    response = requests.post(
        f"{BASE_URL}/food-ai-chat",
        params={
            "user_id": USER_ID,
            "chat_session_id": CHAT_SESSION_ID
        },
        json={
            "food_item": food_item,
            "user_message": None  # None = get opening message
        }
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    pprint(data)
    return data

def test_food_chat_response(food_item, user_response="Yes, I want it!"):
    """Test 3: Send user response in food chat"""
    print("\n=== TEST 3: Send User Response ===")
    print(f"User says: {user_response}")
    response = requests.post(
        f"{BASE_URL}/food-ai-chat",
        params={
            "user_id": USER_ID,
            "chat_session_id": CHAT_SESSION_ID
        },
        json={
            "food_item": food_item,
            "user_message": user_response
        }
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    pprint(data)
    return data

def test_intent_detection(user_response="Yes, I want it!"):
    """Test 4: Detect user intent"""
    print("\n=== TEST 4: Detect Intent ===")
    print(f"Analyzing: '{user_response}'")
    response = requests.post(
        f"{BASE_URL}/food-chat-intent",
        params={
            "user_id": USER_ID
        },
        json={
            "user_response": user_response,
            "food_item": SAMPLE_FOOD_ITEM,
            "chat_session_id": CHAT_SESSION_ID
        }
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    pprint(data)
    return data

def test_add_to_cart(food_item, quantity=1):
    """Test 5: Add food to cart"""
    print("\n=== TEST 5: Add to Cart ===")
    print(f"Adding {quantity}x {food_item.get('food_name')}")
    response = requests.post(
        f"{BASE_URL}/food-ai-order",
        params={
            "user_id": USER_ID
        },
        json={
            "food_item": food_item,
            "quantity": quantity,
            "chat_session_id": CHAT_SESSION_ID
        }
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    pprint(data)
    return data

def test_next_suggestion(food_item):
    """Test 6: Get next food suggestion"""
    print("\n=== TEST 6: Get Next Suggestion ===")
    response = requests.post(
        f"{BASE_URL}/next-food-suggestion",
        params={
            "user_id": USER_ID,
            "last_food_id": food_item.get("menu_id"),
            "restaurant_id": food_item.get("restaurant_id"),
            "lat": LAT,
            "lng": LNG,
            "chat_session_id": CHAT_SESSION_ID
        }
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    pprint(data)
    return data

def test_food_chat_history():
    """Test 7: Get food chat history"""
    print("\n=== TEST 7: Get Food Chat History ===")
    response = requests.get(
        f"{BASE_URL}/food-chat-history",
        params={
            "user_id": USER_ID,
            "chat_session_id": CHAT_SESSION_ID
        }
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Total messages in chat: {data.get('total_messages')}")
    print(f"Food chat messages: {len(data.get('food_chat_messages', []))}")
    pprint(data)
    return data

def test_intent_detection_scenarios():
    """Test various intent detection scenarios"""
    print("\n=== BONUS: Intent Detection Scenarios ===")
    
    scenarios = [
        ("Yes, I want it!", "ORDER"),
        ("Yes please, give me 2", "ORDER"),
        ("Sure, add to cart", "ORDER"),
        ("Sounds good!", "ORDER"),
        ("No thanks", "SKIP"),
        ("Skip, next one", "SKIP"),
        ("What's in it?", "CLARIFY"),
        ("Tell me about the ingredients", "CLARIFY"),
        ("Hmm, interesting", "CONTINUE"),
        ("Can I customize it?", "CLARIFY"),
    ]
    
    for user_input, expected_intent in scenarios:
        intent_data = test_intent_detection(user_input)
        actual_intent = intent_data.get("intent")
        status = "✓" if actual_intent == expected_intent else "✗"
        print(f"{status} Input: '{user_input}' → Expected: {expected_intent}, Got: {actual_intent}")

def run_full_flow():
    """Run a complete flow: Recommend → Chat → Order → Next"""
    print("\n" + "="*60)
    print("FULL FLOW TEST: Recommend → Chat → Order → Next")
    print("="*60)
    
    # Step 1: Get recommendations
    print("\n1️⃣  Getting recommendations...")
    rec_data = test_get_recommendations()
    
    # Use sample food for testing
    print(f"\n2️⃣  Using sample food: {SAMPLE_FOOD_ITEM['food_name']}")
    
    # Step 2: Open food chat
    print("\n3️⃣  Opening food chat...")
    chat_data = test_open_food_chat(SAMPLE_FOOD_ITEM)
    print(f"AI: {chat_data.get('message')}")
    
    # Step 3: User responds
    print("\n4️⃣  User responds with 'Yes, I want 2 of these!'...")
    response_data = test_food_chat_response(SAMPLE_FOOD_ITEM, "Yes, I want 2 of these!")
    
    # Step 4: Detect intent
    print("\n5️⃣  Analyzing user intent...")
    intent_data = test_intent_detection("Yes, I want 2 of these!")
    intent = intent_data.get("intent")
    quantity = intent_data.get("quantity", 1)
    print(f"Intent: {intent}, Quantity: {quantity}")
    
    # Step 5: Add to cart
    if intent == "ORDER":
        print(f"\n6️⃣  Adding {quantity}x to cart...")
        cart_data = test_add_to_cart(SAMPLE_FOOD_ITEM, quantity)
        print(f"Success: {cart_data.get('message')}")
        
        # Step 6: Get next suggestion
        print(f"\n7️⃣  Getting next suggestion...")
        next_data = test_next_suggestion(SAMPLE_FOOD_ITEM)
        print(f"Suggestion Type: {next_data.get('type')}")
        print(f"AI: {next_data.get('message')}")
    
    # Step 7: Get history
    print(f"\n8️⃣  Retrieving chat history...")
    history_data = test_food_chat_history()
    
    print("\n" + "="*60)
    print("✅ FULL FLOW TEST COMPLETE!")
    print("="*60)

if __name__ == "__main__":
    print("🍽️  FOOD AI CHAT - TEST SUITE")
    print("="*60)
    
    # Run individual tests
    # Uncomment to run each test:
    
    # test_open_food_chat(SAMPLE_FOOD_ITEM)
    # test_food_chat_response(SAMPLE_FOOD_ITEM)
    # test_intent_detection()
    # test_intent_detection_scenarios()
    # test_add_to_cart(SAMPLE_FOOD_ITEM, 2)
    # test_next_suggestion(SAMPLE_FOOD_ITEM)
    # test_food_chat_history()
    
    # Run full flow
    run_full_flow()
    
    print("\n✨ All tests completed!")
    print("Check the output above to verify all endpoints are working correctly.")
