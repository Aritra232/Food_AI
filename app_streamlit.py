import streamlit as st
import requests
import json
from datetime import datetime
from uuid import uuid4

# Configuration
# Use 127.0.0.1 to avoid IPv6/localhost resolving to another local service
API_BASE_URL = "http://127.0.0.1:8000"

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
    .onboarding-shell {
        background: linear-gradient(180deg, #ffffff 0%, #f9fafb 100%);
        border: 1px solid rgba(15, 23, 42, 0.06);
        border-radius: 28px;
        padding: 28px;
        box-shadow: 0 18px 60px rgba(15, 23, 42, 0.08);
    }
    .onboarding-title {
        font-size: 30px;
        font-weight: 800;
        color: #1f2937;
        margin-bottom: 6px;
    }
    .onboarding-subtitle {
        color: #64748b;
        font-size: 16px;
        line-height: 1.6;
        margin-bottom: 18px;
    }
    .onboarding-step {
        height: 8px;
        border-radius: 999px;
        background: #e5e7eb;
        overflow: hidden;
    }
    .onboarding-step.active {
        background: linear-gradient(90deg, #d81f45 0%, #ea3a5f 100%);
    }
    .onboarding-summary {
        background: white;
        border-radius: 22px;
        border: 1px solid rgba(15, 23, 42, 0.08);
        padding: 24px;
        box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
    }
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
    .food-chat-container {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        border-radius: 16px;
        padding: 20px;
        margin: 15px 0;
        border: 2px solid #e8ecf1;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
    }
    .food-chat-header {
        font-size: 20px;
        font-weight: 700;
        color: #1f2937;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .food-chat-message-user {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 12px 16px;
        border-radius: 12px;
        margin: 8px 0;
        width: fit-content;
        max-width: 80%;
        margin-left: auto;
        word-wrap: break-word;
    }
    .food-chat-message-ai {
        background: white;
        color: #1f2937;
        padding: 12px 16px;
        border-radius: 12px;
        margin: 8px 0;
        border-left: 4px solid #4CAF50;
        width: fit-content;
        max-width: 80%;
        word-wrap: break-word;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize session state early so sidebar/chat history access is safe.
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "chat_sessions" not in st.session_state:
    st.session_state.chat_sessions = []
if "active_chat_session_id" not in st.session_state:
    st.session_state.active_chat_session_id = None
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
if "recommendation_history" not in st.session_state:
    st.session_state.recommendation_history = []
if "active_recommendation_batch_id" not in st.session_state:
    st.session_state.active_recommendation_batch_id = None
if "last_loaded_chat_session_id" not in st.session_state:
    st.session_state.last_loaded_chat_session_id = None
if "awaiting_instruction_prompt" not in st.session_state:
    st.session_state.awaiting_instruction_prompt = False
if "instruction_input_open" not in st.session_state:
    st.session_state.instruction_input_open = False
if "pending_instruction_restaurant_id" not in st.session_state:
    st.session_state.pending_instruction_restaurant_id = None
if "awaiting_delivery_address_prompt" not in st.session_state:
    st.session_state.awaiting_delivery_address_prompt = False
if "delivery_address_input_open" not in st.session_state:
    st.session_state.delivery_address_input_open = False
if "awaiting_order_summary_prompt" not in st.session_state:
    st.session_state.awaiting_order_summary_prompt = False
if "restaurant_request_created" not in st.session_state:
    st.session_state.restaurant_request_created = None

# ===== FOOD AI CHAT SESSION STATE =====
if "food_ai_chat_active" not in st.session_state:
    st.session_state.food_ai_chat_active = False
if "current_food_item" not in st.session_state:
    st.session_state.current_food_item = None
if "food_chat_history" not in st.session_state:
    st.session_state.food_chat_history = []
if "food_chat_opened" not in st.session_state:
    st.session_state.food_chat_opened = False
if "food_chat_last_processed" not in st.session_state:
    st.session_state.food_chat_last_processed = ""

# Sidebar - User Settings
st.sidebar.title("👤 User Settings")
user_id = st.sidebar.text_input("User ID", value="user123", placeholder="Enter your user ID")

st.sidebar.title("📍 Location")
lat = st.sidebar.number_input("Latitude", value=23.8103, step=0.0001)
lng = st.sidebar.number_input("Longitude", value=90.4125, step=0.0001)

st.sidebar.title("💬 Chats")
if st.sidebar.button("New chat", use_container_width=True):
    st.session_state.active_chat_session_id = f"draft-{uuid4().hex}"
    st.session_state.chat_history = []
    st.session_state.current_recommendations = []
    st.session_state.recommendation_history = []
    st.session_state.option_quantities = {}
    st.session_state.active_recommendation_batch_id = None
    st.session_state.last_assistant_response = ""
    st.session_state.awaiting_instruction_prompt = False
    st.session_state.instruction_input_open = False
    st.session_state.awaiting_delivery_address_prompt = False
    st.session_state.delivery_address_input_open = False
    st.session_state.awaiting_order_summary_prompt = False
    st.rerun()

try:
    previous_loaded_chat_session_id = st.session_state.get("last_loaded_chat_session_id")
    chat_history_response = requests.get(
        f"{API_BASE_URL}/chat-history",
        params={
            "user_id": user_id,
            "chat_session_id": st.session_state.get("active_chat_session_id")
        }
    )
    if chat_history_response.status_code == 200:
        chat_data = chat_history_response.json()
        st.session_state.chat_history = chat_data.get("chat_history", [])
        st.session_state.chat_sessions = chat_data.get("chat_sessions", [])
        loaded_chat_session_id = chat_data.get("chat_session_id")
        if loaded_chat_session_id:
            st.session_state.active_chat_session_id = loaded_chat_session_id
            if previous_loaded_chat_session_id and loaded_chat_session_id != previous_loaded_chat_session_id:
                st.session_state.current_recommendations = []
                st.session_state.recommendation_history = []
                st.session_state.option_quantities = {}
                st.session_state.active_recommendation_batch_id = None
            st.session_state.last_loaded_chat_session_id = loaded_chat_session_id
        elif not st.session_state.active_chat_session_id and not st.session_state.chat_sessions:
            st.session_state.active_chat_session_id = f"draft-{uuid4().hex}"
except Exception:
    pass

if st.session_state.chat_sessions:
    st.sidebar.caption("Recent chats")
    for index, chat_session in enumerate(st.session_state.chat_sessions[:8]):
        session_label = chat_session.get("title") or "New chat"
        session_id = chat_session.get("chat_session_id") or f"legacy-session-{index}"
        button_label = session_label if len(session_label) <= 28 else f"{session_label[:28]}..."
        if st.sidebar.button(button_label, key=f"chat_session_{index}_{session_id}", use_container_width=True):
            st.session_state.current_recommendations = []
            st.session_state.recommendation_history = []
            st.session_state.option_quantities = {}
            st.session_state.active_recommendation_batch_id = None
            st.session_state.active_chat_session_id = session_id
            st.rerun()

def _reset_recommendation_state():
    st.session_state.current_recommendations = []
    st.session_state.recommendation_history = []
    st.session_state.option_quantities = {}
    st.session_state.active_recommendation_batch_id = None


CUISINE_OPTIONS = [
    "Indian",
    "Chinese",
    "Thai",
    "Italian",
    "Mexican",
    "Japanese",
    "Mediterranean",
    "Korean",
    "American",
    "Healthy",
    "Fast Food",
    "Desserts",
    "Breakfast",
    "BBQ"
]

DIETARY_OPTIONS = [
    "None",
    "Vegan",
    "Vegetarian",
    "Halal",
    "Kosher",
    "Gluten-free",
    "Dairy-free",
    "Nut-free",
    "Keto",
    "Paleo",
    "Low-carb"
]

BUDGET_OPTIONS = [
    ("Budget Friendly", "low", "Under $10"),
    ("Casual Dining", "medium", "$10 - $25"),
    ("Fine Dining", "high", "$25 - $50"),
    ("Premium", "high", "$50+")
]

ORDER_FREQUENCY_OPTIONS = [
    "Daily",
    "3-4 times/week",
    "1-2 times/week",
    "Occasionally"
]

ORDER_TIME_OPTIONS = [
    "Breakfast",
    "Lunch",
    "Dinner",
    "Late Night"
]

ADDRESS_TYPE_OPTIONS = ["Home", "Office"]


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


def _profile_is_onboarded(profile):
    return bool(profile and profile.get("onboarding_completed"))


def _sync_onboarding_state(profile):
    preferences = (profile or {}).get("preferences", {})
    delivery_address = (profile or {}).get("delivery_address", {})

    st.session_state.onboarding_step = st.session_state.get("onboarding_step", 0)
    st.session_state.onboarding_cuisines = preferences.get("preferred_cuisines", []) or []
    restrictions = preferences.get("dietary_restrictions", []) or []
    if not restrictions and preferences.get("dietary_style"):
        restrictions = [item.strip() for item in str(preferences.get("dietary_style", "")).split(",") if item.strip()]
    st.session_state.onboarding_restrictions = restrictions
    st.session_state.onboarding_dietary_note = preferences.get("dietary_note", "") or ""
    st.session_state.onboarding_budget = preferences.get("budget_range", "") or ""
    st.session_state.onboarding_order_frequency = preferences.get("order_frequency", "") or ""
    st.session_state.onboarding_order_time = preferences.get("order_time", "") or ""
    st.session_state.onboarding_address_type = delivery_address.get("address_type", "Home") or "Home"
    st.session_state.onboarding_street_address = delivery_address.get("street_address", "") or ""
    st.session_state.onboarding_city = delivery_address.get("city", "") or ""
    st.session_state.onboarding_zip_code = delivery_address.get("zip_code", "") or ""


def _load_user_profile(force=False):
    loaded_user_id = st.session_state.get("loaded_profile_user_id")
    if loaded_user_id and loaded_user_id != user_id:
        st.session_state.user_profile = None
        st.session_state.chat_history = []
        st.session_state.chat_sessions = []
        st.session_state.active_chat_session_id = None
        st.session_state.onboarding_step = 0
        st.session_state.onboarding_show_success = False
        st.session_state.awaiting_instruction_prompt = False
        st.session_state.instruction_input_open = False
        st.session_state.pending_instruction_restaurant_id = None
        st.session_state.awaiting_delivery_address_prompt = False
        st.session_state.delivery_address_input_open = False
        st.session_state.awaiting_order_summary_prompt = False
        st.session_state.restaurant_request_created = None

    if not force and st.session_state.get("loaded_profile_user_id") == user_id and st.session_state.get("user_profile"):
        return st.session_state.user_profile

    try:
        response = requests.get(f"{API_BASE_URL}/user-profile", params={"user_id": user_id})
        if response.status_code == 200:
            profile = response.json()
            st.session_state.user_profile = profile
            st.session_state.loaded_profile_user_id = user_id
            _sync_onboarding_state(profile)
            return profile
    except Exception:
        pass

    return st.session_state.get("user_profile")


def _save_onboarding_profile():
    cuisines = st.session_state.get("onboarding_cuisines", []) or []
    restrictions = [item for item in (st.session_state.get("onboarding_restrictions", []) or []) if item != "None"]
    budget_value = st.session_state.get("onboarding_budget", "")
    meal_time = st.session_state.get("onboarding_order_time", "")
    dietary_note = str(st.session_state.get("onboarding_dietary_note", "") or "").strip()

    payload = {
        "preferred_cuisines": cuisines,
        "dietary_restrictions": restrictions,
        "dietary_note": dietary_note,
        "budget_range": budget_value,
        "preferred_meal_time": [meal_time] if meal_time else [],
        "order_frequency": st.session_state.get("onboarding_order_frequency", ""),
        "order_time": meal_time,
        "delivery_address": {
            "address_type": st.session_state.get("onboarding_address_type", "Home"),
            "street_address": st.session_state.get("onboarding_street_address", ""),
            "city": st.session_state.get("onboarding_city", ""),
            "zip_code": st.session_state.get("onboarding_zip_code", "")
        }
    }

    response = requests.post(
        f"{API_BASE_URL}/profile/onboarding",
        params={"user_id": user_id},
        json=payload
    )

    if response.status_code != 200:
        raise RuntimeError(f"Failed to save profile: {response.status_code} {response.text}")

    profile = response.json()
    st.session_state.user_profile = profile
    st.session_state.loaded_profile_user_id = user_id
    st.session_state.onboarding_show_success = True
    _sync_onboarding_state(profile)
    return profile


def _render_onboarding_progress(step_index, total_steps):
    progress_cols = st.columns(total_steps)
    for index, col in enumerate(progress_cols):
        with col:
            active = index <= step_index
            st.markdown(
                f"<div class='onboarding-step {'active' if active else ''}'></div>",
                unsafe_allow_html=True
            )


def _render_onboarding_success():
    st.markdown(
        """
        <div class="onboarding-shell" style="max-width:760px;margin:0 auto;">
            <div style="display:flex;justify-content:center;margin-top:18px;">
                <div style="width:96px;height:96px;border-radius:999px;background:linear-gradient(135deg,#d81f45 0%,#ef476f 100%);display:flex;align-items:center;justify-content:center;box-shadow:0 16px 40px rgba(216,31,69,0.28);">
                    <div style="width:52px;height:52px;border-radius:999px;border:4px solid white;color:white;display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:800;">✓</div>
                </div>
            </div>
            <div style="text-align:center;margin-top:28px;">
                <div class="onboarding-title">You're all set!</div>
                <div class="onboarding-subtitle" style="max-width:520px;margin:0 auto;">
                    Your preferences and address have been saved to your profile. We can now personalize the food experience for this user.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    col_primary, col_secondary = st.columns(2)
    with col_primary:
        if st.button("Start Ordering with AI", use_container_width=True):
            st.session_state.onboarding_show_success = False
            st.rerun()
    with col_secondary:
        if st.button("Explore App", use_container_width=True):
            st.session_state.onboarding_show_success = False
            st.rerun()


def _render_onboarding_flow():
    if st.session_state.get("onboarding_show_success"):
        _render_onboarding_success()
        st.stop()

    if "onboarding_step" not in st.session_state:
        st.session_state.onboarding_step = 0

    step = st.session_state.onboarding_step
    total_steps = 6

    st.markdown("<div class='onboarding-shell'>", unsafe_allow_html=True)
    _render_onboarding_progress(step, total_steps)
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

    if step == 0:
        st.markdown("<div class='onboarding-title'>Welcome to Roub</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='onboarding-subtitle'>Answer a few quick questions so we can personalize food recommendations, understand your taste, and store your delivery details in your profile.</div>",
            unsafe_allow_html=True
        )
        st.markdown(
            """
            <div style="background:#fff5f7;border-radius:24px;padding:24px;border:1px solid rgba(216,31,69,0.08);margin-bottom:20px;">
                <div style="font-size:18px;font-weight:700;color:#d81f45;margin-bottom:8px;">Personalized setup</div>
                <div style="color:#64748b;line-height:1.6;">We will save your selected cuisines, dietary restrictions, budget, delivery address, and eating habits to the user profile.</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        col_left, col_right = st.columns([1, 1])
        with col_left:
            st.button("Skip for now", use_container_width=True, disabled=True)
        with col_right:
            if st.button("Proceed", use_container_width=True):
                st.session_state.onboarding_step = 1
                st.rerun()

    elif step == 1:
        st.markdown("<div class='onboarding-title'>What do you love to eat?</div>", unsafe_allow_html=True)
        st.markdown("<div class='onboarding-subtitle'>Select all your favorite cuisines.</div>", unsafe_allow_html=True)
        st.session_state.onboarding_cuisines = st.multiselect(
            "Favorite cuisines",
            CUISINE_OPTIONS,
            default=st.session_state.get("onboarding_cuisines", []),
            label_visibility="collapsed"
        )
        col_back, col_next = st.columns([1, 1.2])
        with col_back:
            if st.button("Back", use_container_width=True):
                st.session_state.onboarding_step = 0
                st.rerun()
        with col_next:
            if st.button("Next", use_container_width=True):
                st.session_state.onboarding_step = 2
                st.rerun()

    elif step == 2:
        st.markdown("<div class='onboarding-title'>Dietary Restrictions</div>", unsafe_allow_html=True)
        st.markdown("<div class='onboarding-subtitle'>Pick a quick option, or describe your diet in your own words and we will normalize it with AI.</div>", unsafe_allow_html=True)
        st.session_state.onboarding_restrictions = st.multiselect(
            "Dietary restrictions",
            DIETARY_OPTIONS,
            default=st.session_state.get("onboarding_restrictions", []),
            label_visibility="collapsed"
        )
        st.session_state.onboarding_dietary_note = st.text_input(
            "Dietary note",
            value=st.session_state.get("onboarding_dietary_note", ""),
            placeholder="Example: plant-based, no meat, but I eat eggs sometimes",
            label_visibility="collapsed"
        )
        col_back, col_next = st.columns([1, 1.2])
        with col_back:
            if st.button("Back", use_container_width=True):
                st.session_state.onboarding_step = 1
                st.rerun()
        with col_next:
            if st.button("Next", use_container_width=True):
                st.session_state.onboarding_step = 3
                st.rerun()

    elif step == 3:
        st.markdown("<div class='onboarding-title'>Select Your Budget</div>", unsafe_allow_html=True)
        st.markdown("<div class='onboarding-subtitle'>Choose your preferred spending range.</div>", unsafe_allow_html=True)
        budget_options = ["Budget Friendly", "Casual Dining", "Fine Dining", "Premium"]
        budget_values = ["low", "medium", "high", "premium"]
        budget_display = ["Under $10", "$10 - $25", "$25 - $50", "$50+"]
        
        current_budget = st.session_state.get("onboarding_budget", "")
        try:
            current_index = budget_values.index(current_budget) if current_budget in budget_values else 0
        except:
            current_index = 0
        
        selected_budget_label = st.selectbox(
            "Budget range",
            budget_options,
            index=current_index,
            key="budget_select_step3",
            label_visibility="collapsed"
        )
        
        selected_index = budget_options.index(selected_budget_label)
        st.session_state.onboarding_budget = budget_values[selected_index]
        st.caption(f"Selected: {budget_display[selected_index]}")
        col_back, col_next = st.columns([1, 1.2])
        with col_back:
            if st.button("Back", use_container_width=True):
                st.session_state.onboarding_step = 2
                st.rerun()
        with col_next:
            if st.button("Next", use_container_width=True):
                st.session_state.onboarding_step = 4
                st.rerun()

    elif step == 4:
        st.markdown("<div class='onboarding-title'>Delivery Address</div>", unsafe_allow_html=True)
        st.markdown("<div class='onboarding-subtitle'>Where should we deliver your food?</div>", unsafe_allow_html=True)
        current_addr_type = st.session_state.get("onboarding_address_type", "Home") or "Home"
        current_index = ADDRESS_TYPE_OPTIONS.index(current_addr_type) if current_addr_type in ADDRESS_TYPE_OPTIONS else 0
        st.session_state.onboarding_address_type = st.radio(
            "Address Type",
            ADDRESS_TYPE_OPTIONS,
            index=current_index,
            key="address_type_step4",
            horizontal=True,
            label_visibility="collapsed"
        )
        col_addr1, col_addr2 = st.columns(2)
        with col_addr1:
            st.session_state.onboarding_street_address = st.text_input(
                "Street Address",
                value=st.session_state.get("onboarding_street_address", ""),
                placeholder="Street Address*"
            )
        with col_addr2:
            st.session_state.onboarding_city = st.text_input(
                "City",
                value=st.session_state.get("onboarding_city", ""),
                placeholder="City*"
            )
        st.session_state.onboarding_zip_code = st.text_input(
            "ZIP Code",
            value=st.session_state.get("onboarding_zip_code", ""),
            placeholder="ZIP Code*"
        )
        col_back, col_next = st.columns([1, 1.2])
        with col_back:
            if st.button("Back", use_container_width=True):
                st.session_state.onboarding_step = 3
                st.rerun()
        with col_next:
            if st.button("Next", use_container_width=True):
                st.session_state.onboarding_step = 5
                st.rerun()

    elif step == 5:
        st.markdown("<div class='onboarding-title'>Your Eating Habits</div>", unsafe_allow_html=True)
        st.markdown("<div class='onboarding-subtitle'>Help us understand your ordering patterns.</div>", unsafe_allow_html=True)
        st.write("**How often do you order food?**")
        st.session_state.onboarding_order_frequency = st.radio(
            "Order frequency",
            ORDER_FREQUENCY_OPTIONS,
            index=ORDER_FREQUENCY_OPTIONS.index(st.session_state.get("onboarding_order_frequency", "Daily") or "Daily"),
            label_visibility="collapsed"
        )
        st.write("**When do you usually order?**")
        st.session_state.onboarding_order_time = st.radio(
            "Order time",
            ORDER_TIME_OPTIONS,
            index=ORDER_TIME_OPTIONS.index(st.session_state.get("onboarding_order_time", "Breakfast") or "Breakfast"),
            horizontal=False,
            label_visibility="collapsed"
        )

        with st.container():
            st.markdown("<div class='onboarding-summary'>", unsafe_allow_html=True)
            st.markdown("<div style='font-size:18px;font-weight:700;color:#d81f45;text-align:center;margin-bottom:8px;'>R</div>", unsafe_allow_html=True)
            st.markdown("<div style='text-align:center;color:#374151;line-height:1.6;'>Every bite, personalized - we will save these choices in your profile and use them to shape future recommendations.</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        col_back, col_save = st.columns([1, 1.2])
        with col_back:
            if st.button("Back", use_container_width=True):
                st.session_state.onboarding_step = 4
                st.rerun()
        with col_save:
            if st.button("Save Profile", use_container_width=True):
                try:
                    _save_onboarding_profile()
                    st.session_state.onboarding_step = 0
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save profile: {exc}")

    st.markdown("</div>", unsafe_allow_html=True)


def _get_profile_delivery_addresses(profile):
    addresses = (profile or {}).get("delivery_addresses") or []
    if not addresses:
        fallback_address = (profile or {}).get("delivery_address") or {}
        if any(fallback_address.get(field) for field in ("street_address", "city", "zip_code", "address_type")):
            addresses = [fallback_address]
    return addresses


def _format_address_label(address):
    address_type = address.get("address_type") or "Saved address"
    street_address = address.get("street_address") or ""
    city = address.get("city") or ""
    zip_code = address.get("zip_code") or ""
    details = ", ".join([part for part in [street_address, city, zip_code] if part])
    return f"{address_type} - {details}" if details else address_type


def _save_delivery_address(address_payload):
    response = requests.post(
        f"{API_BASE_URL}/profile/address",
        params={"user_id": user_id},
        json=address_payload
    )

    if response.status_code != 200:
        raise RuntimeError(f"Failed to save address: {response.status_code} {response.text}")

    profile = response.json()
    st.session_state.user_profile = profile
    st.session_state.loaded_profile_user_id = user_id
    return profile


def _select_delivery_address(address_id):
    response = requests.post(
        f"{API_BASE_URL}/profile/address",
        params={"user_id": user_id, "address_id": address_id}
    )

    if response.status_code != 200:
        raise RuntimeError(f"Failed to select address: {response.status_code} {response.text}")

    profile = response.json()
    st.session_state.user_profile = profile
    st.session_state.loaded_profile_user_id = user_id
    return profile


def _load_cart_summary():
    response = requests.get(f"{API_BASE_URL}/cart", params={"user_id": user_id})
    if response.status_code != 200:
        raise RuntimeError(f"Failed to load cart: {response.status_code} {response.text}")
    return response.json()


def _create_restaurant_request():
    response = requests.post(
        f"{API_BASE_URL}/restaurant-request",
        params={"user_id": user_id},
        json={}
    )

    if response.status_code != 200:
        raise RuntimeError(f"Failed to create restaurant request: {response.status_code} {response.text}")

    return response.json()


def _render_delivery_address_flow():
    profile = _load_user_profile(force=True) or st.session_state.get("user_profile") or {}
    addresses = _get_profile_delivery_addresses(profile)

    st.markdown("---")
    st.markdown(
        """
        <div style="background:#ffffff;border-radius:24px;padding:22px;border:1px solid #f1f1f1;box-shadow:0 10px 30px rgba(0,0,0,0.04);">
            <div style="font-size:20px;font-weight:700;color:#1f2937;margin-bottom:10px;">Select a delivery address</div>
            <div style="font-size:15px;line-height:1.6;color:#6b7280;margin-bottom:16px;">Choose one of your saved addresses or add a new address before we create the restaurant request.</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    address_choices = []
    address_labels = {}
    for address in addresses:
        address_id = address.get("address_id") or _format_address_label(address)
        label = _format_address_label(address)
        address_choices.append(address_id)
        address_labels[address_id] = label

    address_choices.append("__new__")
    address_labels["__new__"] = "Add New Address"

    selected_address_key = st.radio(
        "Delivery address",
        address_choices,
        format_func=lambda key: address_labels.get(key, key),
        key="delivery_address_choice"
    )

    if selected_address_key == "__new__":
        st.session_state.delivery_address_input_open = True
    else:
        st.session_state.delivery_address_input_open = False

    if st.session_state.get("delivery_address_input_open"):
        col_label, col_leave = st.columns([3, 1])
        with col_label:
            address_type = st.text_input("Address label", placeholder="Home / Work / Other", key="new_address_label")
        with col_leave:
            leave_at_door = st.toggle("Leave at the door", value=False, key="new_address_leave_at_door")

        street_address = st.text_input("Street address", placeholder="House No, Street, Area", key="new_address_street")
        col_city, col_zip = st.columns(2)
        with col_city:
            city = st.text_input("City", placeholder="City", key="new_address_city")
        with col_zip:
            zip_code = st.text_input("ZIP Code", placeholder="ZIP Code", key="new_address_zip")

        if st.button("Save New Address", use_container_width=True):
            if not street_address or not city or not zip_code:
                st.error("Please fill in street address, city, and ZIP code.")
            else:
                try:
                    profile = _save_delivery_address(
                        {
                            "address_type": address_type or "Home",
                            "street_address": street_address,
                            "city": city,
                            "zip_code": zip_code,
                            "leave_at_door": leave_at_door,
                            "is_default": True
                        }
                    )
                    st.session_state.awaiting_delivery_address_prompt = False
                    st.session_state.awaiting_order_summary_prompt = True
                    st.session_state.restaurant_request_created = None
                    st.success("New address saved.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    else:
        col_back, col_continue = st.columns([1, 1.4])
        with col_back:
            if st.button("Back", use_container_width=True):
                st.session_state.awaiting_delivery_address_prompt = False
                st.session_state.instruction_input_open = True
                st.rerun()
        with col_continue:
            if st.button("Continue to Summary", use_container_width=True):
                try:
                    if selected_address_key != "__new__":
                        _select_delivery_address(selected_address_key)
                    st.session_state.awaiting_delivery_address_prompt = False
                    st.session_state.awaiting_order_summary_prompt = True
                    st.session_state.restaurant_request_created = None
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def _render_order_summary_flow():
    profile = _load_user_profile(force=True) or st.session_state.get("user_profile") or {}
    cart_payload = _load_cart_summary()
    cart = cart_payload.get("cart", {}) or {}
    total_price = float(cart_payload.get("total_price", 0) or 0)
    delivery_fee = 12
    grand_total = total_price + delivery_fee
    items = cart.get("items", []) or []
    delivery_address = profile.get("delivery_address", {}) or {}

    st.markdown("---")
    st.markdown(
        """
        <div style="background:#ffffff;border-radius:24px;padding:22px;border:1px solid #f1f1f1;box-shadow:0 10px 30px rgba(0,0,0,0.04);">
            <div style="font-size:20px;font-weight:700;color:#1f2937;margin-bottom:10px;">Great! Here is a total summary of your order. Please recheck!</div>
            <div style="font-size:15px;line-height:1.6;color:#6b7280;margin-bottom:12px;">We fetched the latest items from your cart and your selected delivery address before sending the request to the restaurant.</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    with st.container(border=True):
        st.subheader("Order Summary")
        for item in items:
            col_img, col_name, col_price = st.columns([1, 4, 1])
            with col_img:
                image_url = item.get("image_url")
                if image_url:
                    st.image(image_url, width=72)
                else:
                    st.markdown(
                        "<div style='width:72px;height:72px;border-radius:16px;background:#fff1f2;display:flex;align-items:center;justify-content:center;font-size:28px;'>🍽️</div>",
                        unsafe_allow_html=True
                    )
            with col_name:
                st.write(item.get("food_name", "Item"))
                st.caption(f"{item.get('quantity', 1)}x")
            with col_price:
                st.markdown(f"**${float(item.get('price', 0)) * int(item.get('quantity', 1)):.0f}**")

        st.markdown("---")
        st.write(f"**Subtotal:** ${total_price:.0f}")
        st.write(f"**Standard delivery:** ${delivery_fee:.0f}")
        st.markdown(f"### Total: ${grand_total:.0f}")

        st.subheader("Delivery Address")
        st.write(f"**{delivery_address.get('address_type') or 'Saved address'}**")
        st.write(delivery_address.get("street_address") or "")
        st.write(", ".join([part for part in [delivery_address.get("city"), delivery_address.get("zip_code")] if part]))

        if st.button("Request to Restaurant", use_container_width=True):
            try:
                request_doc = _create_restaurant_request()
                st.session_state.restaurant_request_created = request_doc
                st.session_state.awaiting_order_summary_prompt = False
                st.success(f"Request sent to restaurant. Status: {request_doc.get('status', 'pending')}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    if st.session_state.get("restaurant_request_created"):
        request_doc = st.session_state.restaurant_request_created
        st.info(
            f"Restaurant request saved with status: {request_doc.get('status', 'pending')} (pending / accept / reject)"
        )


def _refresh_chat_history():
    try:
        history_response = requests.get(
            f"{API_BASE_URL}/chat-history",
            params={
                "user_id": user_id,
                "chat_session_id": st.session_state.get("active_chat_session_id")
            }
        )

        if history_response.status_code == 200:
            data = history_response.json()
            st.session_state.chat_history = data.get("chat_history", [])
            st.session_state.chat_sessions = data.get("chat_sessions", [])
            if data.get("chat_session_id"):
                st.session_state.active_chat_session_id = data.get("chat_session_id")
            st.session_state.user_profile = data["user_profile"]
    except Exception:
        pass


def _append_recommendation_batch(result, assistant_text):
    recommendations = result.get("recommendations") or []
    if not recommendations:
        return

    batch_id = result.get("recommendation_batch_id") or uuid4().hex
    batch_entry = {
        "batch_id": batch_id,
        "assistant_text": assistant_text or "",
        "recommendations": recommendations[:5]
    }

    updated_history = []
    replaced = False
    for existing_batch in st.session_state.recommendation_history:
        if existing_batch.get("batch_id") == batch_id:
            updated_history.append(batch_entry)
            replaced = True
        else:
            updated_history.append(existing_batch)

    if not replaced:
        updated_history.append(batch_entry)

    st.session_state.recommendation_history = updated_history
    st.session_state.current_recommendations = batch_entry["recommendations"]
    st.session_state.active_recommendation_batch_id = batch_id
    quantities = dict(st.session_state.option_quantities)
    for i in range(len(batch_entry["recommendations"])):
        quantities.setdefault(f"{batch_id}_{chr(65 + i)}", 1)
    st.session_state.option_quantities = quantities


def _assistant_text_matches(batch_text, message_text):
    if not batch_text or not message_text:
        return False

    normalize = lambda text: " ".join(str(text).strip().split()).lower()
    batch_text_norm = normalize(batch_text)
    message_text_norm = normalize(message_text)
    return batch_text_norm == message_text_norm or batch_text_norm in message_text_norm or message_text_norm in batch_text_norm


def _render_recommendation_batch(batch):
    recommendations = batch.get("recommendations", []) or []
    batch_id = batch.get("batch_id") or "batch"
    if not recommendations:
        return

    st.markdown("---")
    st.markdown(f"**🍽️ Recommendations for the above response:**")

    for i, item in enumerate(recommendations):
        label = chr(65 + i)
        quantity_key = f"{batch_id}_{label}"
        qty = st.session_state.option_quantities.get(quantity_key, 1)
        st.session_state.option_quantities.setdefault(quantity_key, 1)

        with st.container():
            restaurant_label = item.get("restaurant_name") or item.get("restaurant_id", "N/A")
            st.markdown(
                f"<div class='option-card'><strong>Option {label}:</strong> {item.get('food_name', 'N/A')}<br>"
                f"<small>₹{item.get('price', 'N/A')} | Restaurant {restaurant_label}</small></div>",
                unsafe_allow_html=True
            )

            col_qty, col_minus, col_plus, col_select, col_chat, col_add = st.columns([1, 1, 1, 1, 1.2, 1.4])
            col_qty.metric("Qty", qty)

            if col_minus.button("-", key=f"minus_{batch_id}_{label}"):
                st.session_state.option_quantities[quantity_key] = max(1, qty - 1)
                st.rerun()

            if col_plus.button("+", key=f"plus_{batch_id}_{label}"):
                st.session_state.option_quantities[quantity_key] = qty + 1
                st.rerun()

            if col_select.button("Select", key=f"select_{batch_id}_{label}"):
                selected_message = f"Option {label} x{st.session_state.option_quantities.get(quantity_key, 1)}"
                result, error = _send_chat_message(selected_message, recommendation_batch_id=batch_id)
                if error:
                    st.error(error)
                elif result:
                    st.rerun()

            if col_chat.button("💬 Chat AI", key=f"chat_{batch_id}_{label}"):
                st.session_state.food_ai_chat_active = True
                st.session_state.current_food_item = item
                st.session_state.food_chat_history = []
                st.session_state.food_chat_opened = False
                st.session_state.food_chat_last_processed = ""
                st.rerun()

            if col_add.button("Add to cart", key=f"add_{batch_id}_{label}"):
                selected_message = f"Option {label} x{st.session_state.option_quantities.get(quantity_key, 1)}"
                result, error = _send_chat_message(selected_message, recommendation_batch_id=batch_id)

                if error:
                    st.error(error)
                elif result:
                    confirm_response, confirm_error = _send_chat_message("yes", recommendation_batch_id=batch_id)
                    if confirm_error:
                        st.error(confirm_error)
                    else:
                        st.rerun()


def _render_recommendations_for_message(msg, rendered_batch_ids):
    for batch in st.session_state.recommendation_history:
        if batch.get("batch_id") in rendered_batch_ids:
            continue

        if _assistant_text_matches(batch.get("assistant_text", ""), msg["content"]):
            _render_recommendation_batch(batch)
            rendered_batch_ids.add(batch.get("batch_id"))

    return rendered_batch_ids


def _render_remaining_recommendation_batches(rendered_batch_ids):
    unmatched_batches = [
        batch for batch in st.session_state.recommendation_history
        if batch.get("batch_id") not in rendered_batch_ids
    ]

    if not unmatched_batches:
        return

    st.markdown("---")
    st.subheader("🍽️ Additional Recommendations")

    for batch in unmatched_batches:
        _render_recommendation_batch(batch)


def _send_chat_message(message_text, recommendation_batch_id=None):
    response = requests.post(
        f"{API_BASE_URL}/chat",
        params={
            "user_id": user_id,
            "message": message_text,
            "lat": lat,
            "lng": lng,
            "chat_session_id": st.session_state.get("active_chat_session_id"),
            "recommendation_batch_id": recommendation_batch_id
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

    if recommendations:
        try:
            _append_recommendation_batch(result, assistant_text)
        except Exception:
            batch_id = result.get("recommendation_batch_id") or uuid4().hex
            batch_entry = {
                "batch_id": batch_id,
                "assistant_text": assistant_text or "",
                "recommendations": recommendations[:5]
            }
            st.session_state.recommendation_history = st.session_state.recommendation_history + [batch_entry]
            st.session_state.current_recommendations = recommendations[:5]
            st.session_state.active_recommendation_batch_id = batch_id

    _refresh_chat_history()
    return result, None


def _render_recommendations():
    recommendation_batches = st.session_state.recommendation_history

    if not recommendation_batches:
        return

    st.markdown("---")
    st.subheader("🍽️ Recommendations")

    for batch_index, batch in enumerate(recommendation_batches, 1):
        batch_id = batch.get("batch_id") or f"batch_{batch_index}"
        recommendations = batch.get("recommendations", []) or []

        if len(recommendation_batches) > 1:
            st.caption(f"Suggestion set {batch_index}")

        for i, item in enumerate(recommendations):
            label = chr(65 + i)
            quantity_key = f"{batch_id}_{label}"
            qty = st.session_state.option_quantities.get(quantity_key, 1)
            st.session_state.option_quantities.setdefault(quantity_key, 1)

            with st.container(border=True):
                st.markdown(f"**Option {label}: {item.get('food_name', 'N/A')}**")
                restaurant_label = item.get("restaurant_name") or item.get("restaurant_id", "N/A")
                st.caption(
                    f"₹{item.get('price', 'N/A')} | Restaurant {restaurant_label}"
                )

                col_qty, col_minus, col_plus, col_select, col_add = st.columns([1, 1, 1, 1, 1.4])

                col_qty.metric("Qty", qty)

                if col_minus.button("-", key=f"minus_{batch_id}_{label}"):
                    st.session_state.option_quantities[quantity_key] = max(1, qty - 1)
                    st.rerun()

                if col_plus.button("+", key=f"plus_{batch_id}_{label}"):
                    st.session_state.option_quantities[quantity_key] = qty + 1
                    st.rerun()

                if col_select.button("Select", key=f"select_{batch_id}_{label}"):
                    selected_message = f"Option {label} x{st.session_state.option_quantities.get(quantity_key, 1)}"
                    result, error = _send_chat_message(selected_message, recommendation_batch_id=batch_id)
                    if error:
                        st.error(error)
                    elif result:
                        st.rerun()

                if col_add.button("Add to cart", key=f"add_{batch_id}_{label}"):
                    selected_message = f"Option {label} x{st.session_state.option_quantities.get(quantity_key, 1)}"
                    result, error = _send_chat_message(selected_message, recommendation_batch_id=batch_id)

                    if error:
                        st.error(error)
                    elif result:
                        confirm_response, confirm_error = _send_chat_message("yes", recommendation_batch_id=batch_id)
                        if confirm_error:
                            st.error(confirm_error)
                        else:
                            st.rerun()


# Main title
st.title("🍔 Food AI Chatbot")
st.markdown("---")

if st.session_state.get("restaurant_request_created"):
    request_doc = st.session_state.restaurant_request_created
    st.success(
        f"Restaurant request saved. Current status: {request_doc.get('status', 'pending')} (pending / accept / reject)"
    )

current_profile = _load_user_profile()
if st.session_state.get("onboarding_show_success"):
    _render_onboarding_success()
    st.stop()

if current_profile and not _profile_is_onboarded(current_profile):
    _render_onboarding_flow()
    st.stop()

# Create tabs
tab1, tab2, tab3, tab4 = st.tabs(["🍽️ Food Chat", "💬 Chat", "👤 Profile", "🛒 Cart"])

# ==================== FOOD CHAT TAB ====================
with tab1:
    # Check if food AI chat is active
    if st.session_state.get("food_ai_chat_active"):
        food_item = st.session_state.get("current_food_item")
        if food_item:
            st.markdown("---")
            st.subheader("💬 AI Food Chat")
            
            # Display food details
            col_food_img, col_food_info = st.columns([1, 2])
            with col_food_img:
                st.markdown(f"""
                    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                border-radius: 12px; padding: 20px; text-align: center; color: white;">
                        <div style="font-size: 48px; margin-bottom: 10px;">🍽️</div>
                    </div>
                """, unsafe_allow_html=True)
            
            with col_food_info:
                st.markdown(f"""
                    <div style="background: #f9fafb; border-radius: 12px; padding: 16px;">
                        <div style="font-size: 24px; font-weight: bold; color: #1f2937; margin-bottom: 8px;">
                            {food_item.get('food_name', 'Unknown')}
                        </div>
                        <div style="color: #6b7280; margin-bottom: 12px;">
                            <b>Price:</b> ₹{food_item.get('price', 'N/A')} | 
                            <b>Restaurant:</b> {food_item.get('restaurant_name', 'N/A')}
                        </div>
                        <div style="color: #6b7280; font-size: 14px;">
                            <b>Category:</b> {food_item.get('category', 'N/A')}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Initialize food chat if not opened yet
            if not st.session_state.get("food_chat_opened"):
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/food-ai-chat",
                        json={
                            "user_id": user_id,
                            "food_item": food_item,
                            "user_message": None,
                            "chat_session_id": st.session_state.get("active_chat_session_id")
                        }
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        opening_msg = data.get("message", "Hi! How can I help?")
                        st.session_state.food_chat_history = [
                            {"role": "assistant", "content": opening_msg}
                        ]
                        st.session_state.food_chat_opened = True
                except Exception as e:
                    st.error(f"Error opening food chat: {str(e)}")
            
            # Display food chat history
            for msg in st.session_state.get("food_chat_history", []):
                if msg["role"] == "user":
                    st.markdown(f"""
                        <div class="user-message">
                        <b>You:</b> {msg['content']}
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                        <div class="assistant-message">
                        <b>🤖 AI:</b> {msg['content']}
                        </div>
                    """, unsafe_allow_html=True)
            
            if "food_chat_input" not in st.session_state:
                st.session_state.food_chat_input = ""

            user_response = st.session_state.get("food_chat_input", "")
            last_processed = st.session_state.get("food_chat_last_processed", "")

            def _skip_food_chat():
                st.session_state.food_ai_chat_active = False
                st.session_state.current_food_item = None
                st.session_state.food_chat_history = []
                st.session_state.food_chat_last_processed = ""
                st.session_state.food_chat_input = ""

            # Process user response
            if user_response and user_response != st.session_state.get("food_chat_last_processed", ""):
                try:
                    st.session_state.food_chat_last_processed = user_response
                    with st.spinner("Processing your response..."):
                        # Send food chat message
                        food_response = requests.post(
                            f"{API_BASE_URL}/food-ai-chat",
                            json={
                                "user_id": user_id,
                                "food_item": food_item,
                                "user_message": user_response,
                                "chat_session_id": st.session_state.get("active_chat_session_id")
                            }
                        )
                        
                        if food_response.status_code == 200:
                            food_data = food_response.json()
                            ai_msg = food_data.get("message", "I see...")
                            st.session_state.food_chat_history.append(
                                {"role": "user", "content": user_response}
                            )
                            st.session_state.food_chat_history.append(
                                {"role": "assistant", "content": ai_msg}
                            )

                            # If backend already handled ordering, skip extra intent flow.
                            if food_data.get("status") == "ordered":
                                st.success("Added to cart!")
                                next_food = food_data.get("next_food")
                                next_message = food_data.get("next_message")
                                if next_message:
                                    st.session_state.food_chat_history.append(
                                        {"role": "assistant", "content": next_message}
                                    )
                                if next_food:
                                    st.session_state.current_food_item = next_food
                                    st.session_state.food_chat_opened = False
                                    st.session_state.food_chat_last_processed = ""
                                st.session_state.food_chat_input = ""
                                st.rerun()

                            # Detect intent only if the assistant replied with a normal chat response.
                            intent_response = requests.post(
                                f"{API_BASE_URL}/food-chat-intent",
                                json={
                                    "user_id": user_id,
                                    "user_response": user_response,
                                    "food_item": food_item,
                                    "chat_session_id": st.session_state.get("active_chat_session_id")
                                }
                            )
                            
                            if intent_response.status_code == 200:
                                intent_data = intent_response.json()
                                intent = intent_data.get("intent")
                                quantity = intent_data.get("quantity", 1)
                                
                                if intent == "ORDER":
                                    # Add to cart
                                    add_response = requests.post(
                                        f"{API_BASE_URL}/food-ai-order",
                                        json={
                                            "user_id": user_id,
                                            "food_item": food_item,
                                            "quantity": quantity,
                                            "chat_session_id": st.session_state.get("active_chat_session_id")
                                        }
                                    )
                                    
                                    if add_response.status_code == 200:
                                        order_data = add_response.json()
                                        success_msg = order_data.get("message", "Added to cart!")
                                        st.session_state.food_chat_history.append(
                                            {"role": "assistant", "content": success_msg}
                                        )
                                        st.success(success_msg)
                                        
                                        # Get next suggestion
                                        next_response = requests.post(
                                            f"{API_BASE_URL}/next-food-suggestion",
                                            params={
                                                "user_id": user_id,
                                                "last_food_id": food_item.get("menu_id"),
                                                "restaurant_id": food_item.get("restaurant_id"),
                                                "lat": lat,
                                                "lng": lng,
                                                "chat_session_id": st.session_state.get("active_chat_session_id")
                                            }
                                        )
                                        
                                        if next_response.status_code == 200:
                                            next_data = next_response.json()
                                            if next_data.get("status") == "suggested":
                                                suggestion_msg = next_data.get("message", "Want to add something else?")
                                                next_food = next_data.get("food_item")
                                                
                                                st.session_state.food_chat_history.append(
                                                    {"role": "assistant", "content": suggestion_msg}
                                                )
                                                st.session_state.current_food_item = next_food
                                                st.session_state.food_chat_opened = False
                                                st.session_state.food_chat_last_processed = ""
                                        
                                        st.session_state.food_chat_input = ""
                                        st.rerun()
                                    else:
                                        try:
                                            error_json = add_response.json()
                                            st.error(f"Failed to add to cart: {error_json}")
                                        except Exception:
                                            st.error("Failed to add to cart")
                                
                                elif intent == "SKIP":
                                    skip_msg = "No problem! Let me show you other options."
                                    st.session_state.food_chat_history.append(
                                        {"role": "assistant", "content": skip_msg}
                                    )
                                    
                                    # Get next suggestion
                                    next_response = requests.post(
                                        f"{API_BASE_URL}/next-food-suggestion",
                                        params={
                                            "user_id": user_id,
                                            "restaurant_id": food_item.get("restaurant_id"),
                                            "lat": lat,
                                            "lng": lng,
                                            "chat_session_id": st.session_state.get("active_chat_session_id")
                                        }
                                    )
                                    
                                    if next_response.status_code == 200:
                                        next_data = next_response.json()
                                        if next_data.get("status") == "suggested":
                                            next_food = next_data.get("food_item")
                                            st.session_state.current_food_item = next_food
                                            st.session_state.food_chat_opened = False
                                            st.session_state.food_chat_last_processed = ""
                                    
                                    st.session_state.food_chat_input = ""
                                    st.rerun()
                        
                        st.session_state.food_chat_input = ""
                        st.rerun()
                
                except Exception as e:
                    st.error(f"Error: {str(e)}")

            col_input, col_skip = st.columns([4, 1])
            with col_input:
                st.text_input(
                    "Your response...",
                    placeholder="e.g., Yes, I want it! or Tell me more about ingredients",
                    key="food_chat_input"
                )

            with col_skip:
                st.button("Skip ⏭️", use_container_width=True, on_click=_skip_food_chat)

    else:
        st.markdown("""
            <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                        border-radius: 20px; padding: 30px; text-align: center; color: white; margin-bottom: 20px;">
                <div style="font-size: 36px; font-weight: bold; margin-bottom: 10px;">🍽️ Food Chat</div>
                <div style="font-size: 18px; line-height: 1.6;">
                    Foods are shown automatically from your location. Click "💬 Chat AI" on any item to start the ordering conversation.
                </div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("#### 🔍 Search or browse nearby food")
        food_search = st.text_input(
            "Search for a food item (optional)",
            placeholder="Try burger, pizza, pasta, biryani...",
            key="food_search"
        )

        browse_query = food_search.strip() if food_search else None

        try:
            with st.spinner("Loading food options..."):
                browse_response = requests.get(
                    f"{API_BASE_URL}/food-browse",
                    params={
                        "user_id": user_id,
                        "query": browse_query,
                        "lat": lat,
                        "lng": lng,
                        "limit": 8
                    }
                )

            if browse_response.status_code == 200:
                browse_data = browse_response.json()
                food_items = browse_data.get("items", []) or []

                if not food_items:
                    fallback_terms = [browse_query] if browse_query else ["burger", "pizza", "pasta", "biryani", "noodle", "dessert"]
                    fallback_terms = [term for term in fallback_terms if term]

                    for term in fallback_terms:
                        try:
                            fallback_response = requests.get(
                                f"{API_BASE_URL}/search-food",
                                params={"food": term}
                            )
                            if fallback_response.status_code == 200:
                                fallback_items = fallback_response.json() or []
                                if isinstance(fallback_items, dict):
                                    fallback_items = fallback_items.get("value") or fallback_items.get("items") or []
                                for item in fallback_items:
                                    if item not in food_items:
                                        food_items.append(item)
                        except Exception:
                            continue

                if food_items:
                    heading = f"#### Found {len(food_items)} food options"
                    if browse_query:
                        heading = f"#### Results for '{browse_query}'"
                    st.markdown(heading)

                    for idx, food in enumerate(food_items):
                        col1, col2, col3 = st.columns([2, 2, 1])

                        with col1:
                            st.markdown(f"**{food.get('food_name', 'Food item')}**")
                            st.caption(f"₹{food.get('price', 'N/A')} • {food.get('category', 'Food')}")

                        with col2:
                            st.caption(f"🏪 {food.get('restaurant_name', 'Restaurant')}")

                        with col3:
                            if st.button("💬 Chat with AI", key=f"browse_chat_{idx}_{food.get('menu_id')}"):
                                st.session_state.food_ai_chat_active = True
                                st.session_state.current_food_item = food
                                st.session_state.food_chat_history = []
                                st.session_state.food_chat_opened = False
                                st.session_state.food_chat_last_processed = ""
                                st.rerun()
                else:
                    st.info("No food found nearby yet. Try a different search term or check your location.")
            else:
                st.error(f"Could not load food options: {browse_response.status_code}")
        except Exception as e:
            st.error(f"Error loading food options: {str(e)}")

# ==================== CHAT TAB ====================
with tab2:
    st.subheader("💬 Chat with AI Assistant")
    
    # Display chat history
    chat_container = st.container()
    
    # Fetch chat history
    if st.button("🔄 Refresh Chat History"):
        try:
            response = requests.get(
                f"{API_BASE_URL}/chat-history",
                params={
                    "user_id": user_id,
                    "chat_session_id": st.session_state.get("active_chat_session_id")
                }
            )
            if response.status_code == 200:
                data = response.json()
                st.session_state.chat_history = data.get("chat_history", [])
                st.session_state.chat_sessions = data.get("chat_sessions", [])
                if data.get("chat_session_id"):
                    st.session_state.active_chat_session_id = data.get("chat_session_id")
                st.session_state.user_profile = data["user_profile"]
                st.success("Chat history loaded!")
        except Exception as e:
            st.error(f"Error loading chat history: {str(e)}")
    
    with chat_container:
        rendered_batch_ids = set()

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

                rendered_batch_ids = _render_recommendations_for_message(msg, rendered_batch_ids)

        _render_remaining_recommendation_batches(rendered_batch_ids)
    
        if not st.session_state.recommendation_history and st.session_state.current_recommendations:
            _render_recommendation_batch({
                "batch_id": st.session_state.active_recommendation_batch_id or "active_batch",
                "assistant_text": st.session_state.last_assistant_response,
                "recommendations": st.session_state.current_recommendations
            })

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
                    if result.get("recommendations"):
                        st.rerun()

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
                            "restaurant_id": st.session_state.get("pending_instruction_restaurant_id"),
                            "chat_session_id": st.session_state.get("active_chat_session_id")
                        }
                    )
                    if resp.status_code == 200:
                        st.success("Instruction saved to cart.")
                        st.session_state.awaiting_instruction_prompt = False
                        st.session_state.instruction_input_open = False
                        st.session_state.pending_instruction_restaurant_id = None
                        st.session_state.awaiting_delivery_address_prompt = True
                        st.session_state.delivery_address_input_open = False
                        st.session_state.awaiting_order_summary_prompt = False
                        st.rerun()
                    else:
                        st.error(f"Failed to save instruction: {resp.status_code}")
                except Exception as e:
                    st.error(f"Error saving instruction: {str(e)}")

    if st.session_state.get("awaiting_delivery_address_prompt"):
        _render_delivery_address_flow()
        st.stop()

    if st.session_state.get("awaiting_order_summary_prompt"):
        _render_order_summary_flow()
        st.stop()

    if st.session_state.selected_option_text:
        st.info(f"Selected command copied to input: {st.session_state.selected_option_text}")

# ==================== PROFILE TAB ====================
with tab3:
    st.subheader("👤 User Profile")
    
    if st.button("Reload Profile"):
        try:
            profile = _load_user_profile(force=True)
            if profile:
                st.success("Profile loaded!")
        except Exception as e:
            st.error(f"Error: {str(e)}")
    
    if st.session_state.user_profile:
        profile = st.session_state.user_profile
        
        st.write(f"**User ID:** {profile.get('user_id')}")
        
        st.subheader("🎯 Preferences")
        preferences = profile.get("preferences", {})
        addresses = profile.get("delivery_addresses", []) or []
        selected_address_id = profile.get("selected_delivery_address_id")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**Favorite Foods:** {', '.join(preferences.get('favorite_foods', [])) or 'None'}")
            st.write(f"**Disliked Foods:** {', '.join(preferences.get('disliked_foods', [])) or 'None'}")
            st.write(f"**Preferred Cuisines:** {', '.join(preferences.get('preferred_cuisines', [])) or 'None'}")
            st.write(f"**Spicy Level:** {preferences.get('spicy_level') or 'Not set'}")
        
        with col2:
            st.write(f"**Budget Range:** {preferences.get('budget_range') or 'Not set'}")
            st.write(f"**Dietary Style:** {preferences.get('dietary_style') or 'Not set'}")
            st.write(f"**Dietary Restrictions:** {', '.join(preferences.get('dietary_restrictions', [])) or 'None'}")
            st.write(f"**Order Frequency:** {preferences.get('order_frequency') or 'Not set'}")
            st.write(f"**Order Time:** {preferences.get('order_time') or 'Not set'}")
            st.write(f"**Allergies:** {', '.join(preferences.get('allergies', [])) or 'None'}")
            st.write(f"**Favorite Drinks:** {', '.join(preferences.get('favorite_drinks', [])) or 'None'}")

        delivery_address = profile.get("delivery_address", {}) or {}
        st.subheader("📍 Delivery Address")
        st.write(f"**Type:** {delivery_address.get('address_type') or 'Not set'}")
        st.write(f"**Street Address:** {delivery_address.get('street_address') or 'Not set'}")
        st.write(f"**City:** {delivery_address.get('city') or 'Not set'}")
        st.write(f"**ZIP Code:** {delivery_address.get('zip_code') or 'Not set'}")
        st.write(f"**Onboarding Completed:** {'Yes' if profile.get('onboarding_completed') else 'No'}")

        if addresses:
            st.subheader("📚 Saved Addresses")
            for address in addresses:
                marker = "(Selected)" if address.get("address_id") == selected_address_id else ""
                st.write(
                    f"- **{address.get('address_type') or 'Address'}** {marker} | {address.get('street_address') or ''}, {address.get('city') or ''} {address.get('zip_code') or ''}"
                )
        
        # Display raw JSON
        st.subheader("📊 Full Profile (JSON)")
        st.json(profile)
    else:
        st.info("Click 'Reload Profile' to see your profile details")

# ==================== CART TAB ====================
with tab4:
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