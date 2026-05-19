import streamlit as st
import requests
import json
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8000"

# Page configuration
st.set_page_config(
    page_title="Food AI Chatbot",
    page_icon="🍔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .user-message {
        background-color: #e3f2fd;
        padding: 12px;
        border-radius: 8px;
        margin: 8px 0;
        border-left: 4px solid #2196F3;
    }
    .assistant-message {
        background-color: #f1f8e9;
        padding: 12px;
        border-radius: 8px;
        margin: 8px 0;
        border-left: 4px solid #4CAF50;
    }
    .option-card {
        background-color: #fff3e0;
        padding: 12px;
        border-radius: 8px;
        margin: 8px 0;
        border: 2px solid #FF9800;
    }
    .cart-item {
        background-color: #fce4ec;
        padding: 12px;
        border-radius: 8px;
        margin: 8px 0;
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar - User Settings
st.sidebar.title("👤 User Settings")
user_id = st.sidebar.text_input("User ID", value="user123", placeholder="Enter your user ID")

st.sidebar.title("📍 Location")
lat = st.sidebar.number_input("Latitude", value=23.8103, step=0.0001)
lng = st.sidebar.number_input("Longitude", value=90.4125, step=0.0001)

# Initialize session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "user_profile" not in st.session_state:
    st.session_state.user_profile = None
if "last_recommendations" not in st.session_state:
    st.session_state.last_recommendations = []
if "option_quantities" not in st.session_state:
    st.session_state.option_quantities = {}
if "selected_option_text" not in st.session_state:
    st.session_state.selected_option_text = ""
if "last_assistant_response" not in st.session_state:
    st.session_state.last_assistant_response = ""
if "current_recommendations" not in st.session_state:
    st.session_state.current_recommendations = []
if "awaiting_instruction_prompt" not in st.session_state:
    st.session_state.awaiting_instruction_prompt = False
if "instruction_input_open" not in st.session_state:
    st.session_state.instruction_input_open = False
if "pending_instruction_restaurant_id" not in st.session_state:
    st.session_state.pending_instruction_restaurant_id = None


def _extract_assistant_text(result):
    ai_response = result.get("ai_response")

    if isinstance(ai_response, dict) and ai_response.get("response"):
        return ai_response["response"]

    if isinstance(ai_response, str) and ai_response:
        return ai_response

    for key in ("response", "message"):
        if result.get(key):
            return result[key]

    return ""


def _refresh_chat_history():
    try:
        history_response = requests.get(
            f"{API_BASE_URL}/chat-history",
            params={"user_id": user_id}
        )

        if history_response.status_code == 200:
            data = history_response.json()
            st.session_state.chat_history = data["chat_history"]
            st.session_state.user_profile = data["user_profile"]
    except Exception:
        pass


def _send_chat_message(message_text):
    response = requests.post(
        f"{API_BASE_URL}/chat",
        params={
            "user_id": user_id,
            "message": message_text,
            "lat": lat,
            "lng": lng
        }
    )

    if response.status_code != 200:
        return None, f"Error: {response.status_code}\n{response.text}"

    result = response.json()
    assistant_text = _extract_assistant_text(result)

    if assistant_text:
        st.session_state.last_assistant_response = assistant_text

    recommendations = result.get("recommendations") or []
    show_instruction_card = bool(result.get("show_instruction_card"))

    if show_instruction_card:
        st.session_state.awaiting_instruction_prompt = True
        st.session_state.instruction_input_open = False
        st.session_state.pending_instruction_restaurant_id = result.get("restaurant_id")
        st.session_state.current_recommendations = []

    # Only show recommendations when we are not switching into instruction mode
    if recommendations and not show_instruction_card:
        st.session_state.current_recommendations = recommendations[:5]
        st.session_state.option_quantities = {
            chr(65 + i): 1
            for i in range(len(st.session_state.current_recommendations))
        }

    _refresh_chat_history()
    return result, None


def _render_recommendations():
    recommendations = st.session_state.current_recommendations

    if not recommendations:
        return

    st.markdown("---")
    st.subheader("🍽️ Recommendations")

    for i, item in enumerate(recommendations):
        label = chr(65 + i)
        qty = st.session_state.option_quantities.get(label, 1)
        st.session_state.option_quantities.setdefault(label, 1)

        with st.container(border=True):
            st.markdown(f"**Option {label}: {item.get('food_name', 'N/A')}**")
            st.caption(
                f"₹{item.get('price', 'N/A')} | Restaurant {item.get('restaurant_id', 'N/A')}"
            )

            col_qty, col_minus, col_plus, col_select, col_add = st.columns([1, 1, 1, 1, 1.4])

            col_qty.metric("Qty", qty)

            if col_minus.button("-", key=f"minus_{label}"):
                st.session_state.option_quantities[label] = max(1, qty - 1)
                st.rerun()

            if col_plus.button("+", key=f"plus_{label}"):
                st.session_state.option_quantities[label] = qty + 1
                st.rerun()

            if col_select.button("Select", key=f"select_{label}"):
                selected_message = f"Option {label} x{st.session_state.option_quantities.get(label, 1)}"
                result, error = _send_chat_message(selected_message)
                if error:
                    st.error(error)
                elif result:
                    st.rerun()

            if col_add.button("Add to cart", key=f"add_{label}"):
                selected_message = f"Option {label} x{st.session_state.option_quantities.get(label, 1)}"
                result, error = _send_chat_message(selected_message)

                if error:
                    st.error(error)
                elif result:
                    confirm_response, confirm_error = _send_chat_message("yes")
                    if confirm_error:
                        st.error(confirm_error)
                    else:
                        st.rerun()


# Main title
st.title("🍔 Food AI Chatbot")
st.markdown("---")

# Create tabs
tab1, tab2, tab3 = st.tabs(["💬 Chat", "👤 Profile", "🛒 Cart"])

# ==================== CHAT TAB ====================
with tab1:
    st.subheader("Chat with Food AI Assistant")
    
    # Display chat history
    chat_container = st.container()
    
    # Fetch chat history
    if st.button("🔄 Refresh Chat History"):
        try:
            response = requests.get(f"{API_BASE_URL}/chat-history", params={"user_id": user_id})
            if response.status_code == 200:
                data = response.json()
                st.session_state.chat_history = data["chat_history"]
                st.session_state.user_profile = data["user_profile"]
                st.success("Chat history loaded!")
        except Exception as e:
            st.error(f"Error loading chat history: {str(e)}")
    
    # Display conversation
    with chat_container:
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(f"""
                    <div class="user-message">
                    <b>You:</b> {msg['content']}
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                    <div class="assistant-message">
                    <b>🤖 Assistant:</b> {msg['content']}
                    </div>
                """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Input section
    col1, col2 = st.columns([4, 1])
    
    with col1:
        user_message = st.text_input(
            "Type your message...",
            placeholder="e.g., I want a burger, select option A, yes, confirm order",
            key="message_input"
        )
    
    with col2:
        send_button = st.button("Send 📤", use_container_width=True)
    
    # Send message
    if send_button and user_message:
        try:
            with st.spinner("Processing..."):
                result, error = _send_chat_message(user_message)

                if error:
                    st.error(error)
                elif result:
                    st.success("Message sent!")
                    st.info(
                        f"🎯 Detected Intent: **{result.get('intent', 'unknown')}** | State: **{result.get('state', 'unknown')}**"
                    )

                    assistant_text = _extract_assistant_text(result)
                    if assistant_text:
                        st.markdown(f"""
                            <div class="assistant-message">
                            {assistant_text}
                            </div>
                        """, unsafe_allow_html=True)

                    if "cart" in result and result["cart"]:
                        st.subheader("🛒 Current Cart:")
                        st.json(result["cart"])
        
        except Exception as e:
            st.error(f"Error: {str(e)}")

    # If the backend asked for a special instruction, show the prompt card
    if st.session_state.get('awaiting_instruction_prompt'):
        st.markdown("---")
        st.markdown(
            """
            <div style="background:#ffffff;border-radius:24px;padding:24px;border:1px solid #f1f1f1;box-shadow:0 10px 30px rgba(0,0,0,0.04);">
                <div style="font-size:20px;font-weight:700;color:#1f2937;margin-bottom:12px;">Special instructions</div>
                <div style="font-size:15px;line-height:1.6;color:#6b7280;margin-bottom:18px;">
                    Please let us know if you are allergic to anything or if we need to avoid anything
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        col_skip, col_input = st.columns([1, 2])
        if col_skip.button("Skip", use_container_width=True):
            st.session_state.awaiting_instruction_prompt = False
            st.session_state.instruction_input_open = False
            st.session_state.pending_instruction_restaurant_id = None
            st.rerun()

        if col_input.button("Input Instruction", use_container_width=True):
            st.session_state.instruction_input_open = True
            st.rerun()

        if st.session_state.get("instruction_input_open"):
            instruction_text = st.text_input(
                "Add any special requests or dietary notes below",
                key="pending_order_instr"
            )
            if st.button("Save Instruction", use_container_width=True):
                try:
                    resp = requests.post(
                        f"{API_BASE_URL}/instruction",
                        params={
                            "user_id": user_id,
                            "instruction": instruction_text,
                            "restaurant_id": st.session_state.get("pending_instruction_restaurant_id")
                        }
                    )
                    if resp.status_code == 200:
                        st.success("Instruction saved to cart.")
                        st.session_state.awaiting_instruction_prompt = False
                        st.session_state.instruction_input_open = False
                        st.session_state.pending_instruction_restaurant_id = None
                        st.rerun()
                    else:
                        st.error(f"Failed to save instruction: {resp.status_code}")
                except Exception as e:
                    st.error(f"Error saving instruction: {str(e)}")

    _render_recommendations()

    if st.session_state.selected_option_text:
        st.info(f"Selected command copied to input: {st.session_state.selected_option_text}")

# ==================== PROFILE TAB ====================
with tab2:
    st.subheader("👤 User Profile")
    
    if st.button("Reload Profile"):
        try:
            response = requests.get(f"{API_BASE_URL}/user-profile", params={"user_id": user_id})
            if response.status_code == 200:
                st.session_state.user_profile = response.json()
                st.success("Profile loaded!")
        except Exception as e:
            st.error(f"Error: {str(e)}")
    
    if st.session_state.user_profile:
        profile = st.session_state.user_profile
        
        st.write(f"**User ID:** {profile.get('user_id')}")
        
        st.subheader("🎯 Preferences")
        preferences = profile.get("preferences", {})
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**Favorite Foods:** {', '.join(preferences.get('favorite_foods', [])) or 'None'}")
            st.write(f"**Disliked Foods:** {', '.join(preferences.get('disliked_foods', [])) or 'None'}")
            st.write(f"**Preferred Cuisines:** {', '.join(preferences.get('preferred_cuisines', [])) or 'None'}")
            st.write(f"**Spicy Level:** {preferences.get('spicy_level') or 'Not set'}")
        
        with col2:
            st.write(f"**Budget Range:** {preferences.get('budget_range') or 'Not set'}")
            st.write(f"**Dietary Style:** {preferences.get('dietary_style') or 'Not set'}")
            st.write(f"**Allergies:** {', '.join(preferences.get('allergies', [])) or 'None'}")
            st.write(f"**Favorite Drinks:** {', '.join(preferences.get('favorite_drinks', [])) or 'None'}")
        
        # Display raw JSON
        st.subheader("📊 Full Profile (JSON)")
        st.json(profile)
    else:
        st.info("Click 'Reload Profile' to see your profile details")

# ==================== CART TAB ====================
with tab3:
    st.subheader("🛒 Shopping Cart")

    if st.button("Refresh Cart"):
        try:
            response = requests.get(f"{API_BASE_URL}/cart", params={"user_id": user_id})
            if response.status_code == 200:
                st.success("Cart loaded!")
                st.json(response.json())
        except Exception as e:
            st.error(f"Error: {str(e)}")
    
    try:
        response = requests.get(f"{API_BASE_URL}/cart", params={"user_id": user_id})
        if response.status_code == 200:
            cart_data = response.json()
            cart = cart_data.get("cart", {})
            total = cart_data.get("total_price", 0)
            
            items = cart.get("items", [])
            
            if items:
                st.subheader(f"Items ({len(items)})")
                
                for i, item in enumerate(items, 1):
                    with st.expander(f"🍽️ {item.get('food_name', 'Unknown')} - ₹{item.get('price', 0)}"):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.write(f"**Food Name:** {item.get('food_name')}")
                            st.write(f"**Price:** ₹{item.get('price')}")
                        with col2:
                            st.write(f"**Quantity:** {item.get('quantity', 1)}")
                            st.write(f"**Menu ID:** {item.get('menu_id')}")
                        with col3:
                            st.write(f"**Restaurant:** {item.get('restaurant_id')}")
                        # Show existing item-level instruction (read-only)
                        existing_instr = item.get('special_instructions')
                        if existing_instr:
                            st.write(f"**Item instruction:** {existing_instr}")
                
                st.markdown("---")
                st.markdown(f"### 💰 Total: ₹{total}")
            else:
                st.info("Your cart is empty. Start by asking for food recommendations!")
        else:
            st.error("Could not load cart")
    except Exception as e:
        st.error(f"Error loading cart: {str(e)}")

# Footer
st.markdown("---")
st.markdown("""
    <div style='text-align: center'>
    <p>🍔 Food AI Chatbot v1.0 | Powered by FastAPI & Streamlit</p>
    </div>
""", unsafe_allow_html=True)
