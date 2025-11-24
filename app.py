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

# 2. ROBUST DATA STORAGE
# ---------------------------------------------------------
def load_db():
    """Safely loads the database, handling errors if file is missing/corrupt."""
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, "r") as f:
            content = f.read()
            if not content: return [] # Handle empty file
            return json.loads(content)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_to_db(new_event):
    """Safely appends to the database."""
    events = load_db()
    # Add a unique ID based on timestamp to avoid duplicates/errors
    new_event['id'] = datetime.now().strftime("%Y%m%d%H%M%S")
    events.append(new_event)
    try:
        with open(DB_FILE, "w") as f:
            json.dump(events, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Could not save to disk: {e}")
        return False

# 3. HELPER FUNCTIONS
# ---------------------------------------------------------
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
# ---------------------------------------------------------
st.title("✡️ Simcha Manager")

if not api_key:
    st.warning("⚠️ API Key missing. Please check Streamlit Secrets.")
    st.stop()

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📷 Scan Invite", "✍️ Manual Entry", "🗓️ Simcha List"])

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

# === PROCESSING (Shared) ===
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
        submitted = st.form_submit_button("✅ Save to List")

    if submitted:
        new_record = {
            "title": f"{e_type}: {e_name}",
            "start": f"{e_date}T{e_time}",
            "location": e_loc,
            "attending": attending,
            "extendedProps": { "gift": need_gift, "shabbos": is_shabbos }
        }
        if save_to_db(new_record):
            st.success("Saved!")
            # Generate links but don't force them immediately
            start_dt = datetime.combine(e_date, e_time)
            end_dt = start_dt + timedelta(hours=3)
            event_link = generate_google_calendar_link(f"{e_type}: {e_name}", start_dt, end_dt, e_loc, "Simcha Manager")
            st.markdown(f"**Event Link:** [Add to Google Calendar]({event_link})")

# === TAB 3: LIST VIEW (Outlook/HebCal Style) ===
with tab3:
    st.header("📅 Simcha Schedule")
    events = load_db()
    
    if not events:
        st.info("No Simchos saved yet.")
    else:
        # Prepare events for calendar
        cal_events = []
        for e in events:
            # Color Logic: Green for Yes, Yellow for Maybe, Grey for No
            color = "#28a745" if e['attending'] == "Yes" else ("#ffc107" if e['attending'] == "Maybe" else "#6c757d")
            
            cal_events.append({ 
                "title": e['title'], 
                "start": e['start'], 
                "backgroundColor": color, 
                "borderColor": color,
                "allDay": False
            })
            
        # CONFIGURATION FOR LIST VIEW
        calendar_options = {
            "initialView": "listMonth", # <--- THIS MAKES IT A LIST
            "headerToolbar": {
                "left": "today prev,next",
                "center": "title",
                "right": "listMonth,dayGridMonth" # Button to toggle views
            },
            "views": {
                "listMonth": { "buttonText": "List View" },
                "dayGridMonth": { "buttonText": "Grid View" }
            }
        }
        
        calendar(events=cal_events, options=calendar_options)

    # ADD DOWNLOAD BUTTON (Backup)
    if events:
        st.markdown("---")
        st.download_button(
            label="📥 Download My Simchos (Backup)",
            data=json.dumps(events, indent=4),
            file_name="my_simchos.json",
            mime="application/json"
        )
