import streamlit as st
import os
import base64
import json
import urllib.parse
from datetime import datetime, timedelta
from PIL import Image
from openai import OpenAI
from streamlit_calendar import calendar

# 1. CONFIGURATION & SETUP
api_key = os.getenv("OPENAI_API_KEY") 
if not api_key and "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]

client = OpenAI(api_key=api_key)
DB_FILE = "simchos.json"

st.set_page_config(page_title="Simcha Manager", page_icon="✡️", layout="wide")

if 'simcha_data' not in st.session_state:
    st.session_state['simcha_data'] = {}

# 2. DATA STORAGE
def load_db():
    if not os.path.exists(DB_FILE): return []
    try:
        with open(DB_FILE, "r") as f: return json.load(f)
    except: return []

def save_to_db(new_event):
    events = load_db()
    events.append(new_event)
    with open(DB_FILE, "w") as f: json.dump(events, f, indent=4)

# 3. HELPER FUNCTIONS
def encode_image(image_file):
    return base64.b64encode(image_file.getvalue()).decode('utf-8')

def generate_google_calendar_link(title, start_dt, end_dt, location, details):
    base_url = "https://www.google.com/calendar/render?action=TEMPLATE"
    fmt = "%Y%m%dT%H%M%S"
    dates = f"{start_dt.strftime(fmt)}/{end_dt.strftime(fmt)}"
    params = { "text": title, "dates": dates, "location": location, "details": details }
    return f"{base_url}&{urllib.parse.urlencode(params)}"

def analyze_simcha(image_base64, current_date_str):
    system_prompt = f"""
    You are a helpful assistant for an Orthodox Jewish user. Today is {current_date_str}.
    RULES:
    1. Extract Event Type, Celebrant Name, Location.
    2. Extract Date & Time. Convert Hebrew dates to Gregorian (YYYY-MM-DD).
    3. Determine if it is a "Shabbos Event". Set "is_shabbos_event": true if yes.
    Return JSON: {{ "event_type": "", "celebrant": "", "location": "", "date": "YYYY-MM-DD", "time": "HH:MM", "is_shabbos_event": boolean }}
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": "Analyze this."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
            ]}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# 4. STREAMLIT UI
st.title("✡️ Simcha Manager")

if not api_key:
    st.warning("⚠️ API Key missing in Secrets.")
    st.stop()

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📷 Scan Invite", "✍️ Manual Entry", "🗓️ Calendar View"])

# === TAB 1: SCAN ===
with tab1:
    uploaded_file = st.file_uploader("Upload Invitation", type=['jpg', 'png', 'jpeg'])
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, width=300)
        if st.button("Analyze Invitation"):
            with st.spinner("Reading details..."):
                try:
                    b64 = encode_image(uploaded_file)
                    today = datetime.now().strftime("%Y-%m-%d")
                    data = analyze_simcha(b64, today)
                    st.session_state['simcha_data'] = data
                    st.session_state['has_data'] = True
                    st.rerun()
                except Exception as e: st.error(f"Error: {e}")

# === TAB 2: MANUAL ===
with tab2:
    if st.button("Start Blank Entry"):
        st.session_state['simcha_data'] = {
            "event_type": "", "celebrant": "", "location": "", 
            "date": datetime.now().strftime("%Y-%m-%d"), 
            "time": "19:00", "is_shabbos_event": False
        }
        st.session_state['has_data'] = True
        st.rerun()

# === PROCESSING ===
if st.session_state.get('has_data'):
    st.markdown("---")
    st.subheader("📝 Review & Save")
    data = st.session_state['simcha_data']
    
    with st.form("simcha_form"):
        c1, c2 = st.columns(2)
        with c1:
            e_type = st.text_input("Event Type", value=data.get('event_type', ''))
            try: d_val = datetime.strptime(str(data.get('date')), "%Y-%m-%d")
            except: d_val = datetime.now()
            e_date = st.date_input("Date", value=d_val)
            is_shabbos = st.checkbox("Is this Shabbos?", value=data.get('is_shabbos_event', False))
        with c2:
            e_name = st.text_input("Celebrant", value=data.get('celebrant', ''))
            try: t_val = datetime.strptime(str(data.get('time')), "%H:%M").time()
            except: t_val = datetime.strptime("19:00", "%H:%M").time()
            e_time = st.time_input("Time", value=t_val)
            e_loc = st.text_input("Location", value=data.get('location', ''))

        st.markdown("#### Actions")
        col_a, col_b = st.columns(2)
        with col_a: attending = st.radio("Are you attending?", ["Yes", "Maybe", "No"], horizontal=True)
        with col_b: need_gift = st.radio("Need a gift?", ["Yes", "No"], index=1, horizontal=True)
        submitted = st.form_submit_button("✅ Save & Generate Links")

    if submitted:
        # SAVE
        new_record = {
            "title": f"{e_type}: {e_name}",
            "start": f"{e_date}T{e_time}",
            "location": e_loc,
            "attending": attending
        }
        save_to_db(new_record)
        st.success("Saved to Simcha Calendar!")

        # LINKS
        if attending in ["Yes", "Maybe"]:
            start_dt = datetime.combine(e_date, e_time)
            end_dt = start
