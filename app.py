import streamlit as st
import os
import base64
import json
from datetime import datetime, timedelta
import urllib.parse
from PIL import Image
from openai import OpenAI

# 1. CONFIGURATION & SETUP
# ---------------------------------------------------------
# NOTE: In Streamlit Cloud, we get the key from st.secrets or os.environ
api_key = os.getenv("OPENAI_API_KEY") 
if not api_key and "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]

client = OpenAI(api_key=api_key)

st.set_page_config(page_title="Simcha Manager", page_icon="✡️")

# 2. HELPER FUNCTIONS
# ---------------------------------------------------------

def encode_image(image_file):
    """Encodes the uploaded image to base64 for OpenAI."""
    return base64.b64encode(image_file.getvalue()).decode('utf-8')

def generate_google_calendar_link(title, start_dt, end_dt, location, details):
    """Generates a clickable Google Calendar URL."""
    base_url = "https://www.google.com/calendar/render?action=TEMPLATE"
    fmt = "%Y%m%dT%H%M%S"
    dates = f"{start_dt.strftime(fmt)}/{end_dt.strftime(fmt)}"
    
    params = {
        "text": title,
        "dates": dates,
        "location": location,
        "details": details,
    }
    return f"{base_url}&{urllib.parse.urlencode(params)}"

def analyze_simcha(image_base64, current_date_str):
    """Sends image to GPT-4o to extract details."""
    system_prompt = f"""
    You are a helpful assistant for an Orthodox Jewish user.
    Today's date is: {current_date_str}.
    
    RULES:
    1. Extract Event Type, Celebrant Name, Location.
    2. Extract Date & Time. 
       - CRITICAL: Convert Hebrew dates (e.g., "3rd of Kislev") to the correct Gregorian Date (YYYY-MM-DD) for the upcoming occurrence.
    3. Determine if it is a "Shabbos Event" (Sholom Zochor, Kiddush, Aufruf). Set "is_shabbos_event": true if yes.
    
    Return ONLY valid JSON:
    {{
        "event_type": "String",
        "celebrant": "String",
        "location": "String",
        "date": "YYYY-MM-DD",
        "time": "HH:MM",
        "is_shabbos_event": boolean,
        "summary": "Short 1 sentence summary"
    }}
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": "Please analyze this invitation."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
            ]}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# 3. STREAMLIT UI
# ---------------------------------------------------------
st.title("✡️ Simcha Manager")

if not api_key:
    st.error("OpenAI API Key is missing! Please add it in Streamlit Secrets.")
    st.stop()

uploaded_file = st.file_uploader("Upload Invitation Image", type=['jpg', 'png', 'jpeg'])

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption='Uploaded Invitation', use_container_width=True)
    
    if st.button("Analyze Invitation"):
        with st.spinner("Reading Hebrew dates and details..."):
            try:
                base64_image = encode_image(uploaded_file)
                current_date = datetime.now().strftime("%Y-%m-%d")
                data = analyze_simcha(base64_image, current_date)
                st.session_state['simcha_data'] = data
            except Exception as e:
                st.error(f"Error: {e}")

if 'simcha_data' in st.session_state:
    data = st.session_state['simcha_data']
    st.markdown("---")
    st.subheader("🎉 Event Details")
    
    col1, col2 = st.columns(2)
    with col1:
        e_type = st.text_input("Event Type", data.get('event_type'))
        e_date_obj = datetime.strptime(data.get('date'), "%Y-%m-%d")
        e_date = st.date_input("Date", e_date_obj)
        is_shabbos = st.checkbox("Is this Shabbos?", data.get('is_shabbos_event'))
    with col2:
        e_name = st.text_input("Celebrant", data.get('celebrant'))
        try:
            time_obj = datetime.strptime(data.get('time'), "%H:%M").time()
        except:
            time_obj = datetime.strptime("12:00", "%H:%M").time()
        e_time = st.time_input("Time", time_obj)
        e_loc = st.text_input("Location", data.get('location'))

    st.markdown("---")
    attending = st.radio("Are you attending?", ["Yes", "Maybe", "No"])
    need_gift = st.radio("Need a gift?", ["Yes", "No"], index=1)

    if attending in ["Yes", "Maybe"]:
        start_dt = datetime.combine(e_date, e_time)
        end_dt = start_dt + timedelta(hours=2)
        
        link = generate_google_calendar_link(f"{e_type}: {e_name}", start_dt, end_dt, e_loc, "Simcha Manager")
        st.markdown(f"### [🗓️ Add to Google Calendar]({link})")
        
        if need_gift == "Yes":
            # Gift logic
            if is_shabbos:
                 # Backtrack to Friday
                friday_date = e_date - timedelta(days=(e_date.weekday() - 4))
                gift_start = datetime.combine(friday_date, datetime.strptime("10:00", "%H:%M").time())
            else:
                gift_start = datetime.combine(e_date - timedelta(days=1), datetime.strptime("10:00", "%H:%M").time())
                
            gift_link = generate_google_calendar_link(f"Buy Gift: {e_name}", gift_start, gift_start + timedelta(minutes=30), "Store", "Reminder")
            st.markdown(f"### [🎁 Add Gift Reminder]({gift_link})")
