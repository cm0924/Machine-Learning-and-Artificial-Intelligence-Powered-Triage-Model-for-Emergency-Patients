import streamlit as st
import database
import pandas as pd
import time

st.set_page_config(page_title="Staff Directory", page_icon="📋", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    div[data-testid="stMetricValue"] { font-size: 24px; }
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        border-radius: 4px 4px 0px 0px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# 1. AUTH CHECK
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ Access Restricted. Redirecting...")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

# 2. FETCH & PREP DATA
df = database.get_staff_status_report()

st.title("📋 Staff Command Center")
st.caption("Real-time Tracking of Personnel Location & Workload")

if df.empty:
    st.error("No staff records found in database.")
    st.stop()

# --- PRE-PROCESSING ---
# 1. Rename Columns for Display
df = df.rename(columns={"full_name": "Name", "role": "Role_DB", "Status": "Current_Status"})

# 2. Map Roles to Nice Names
role_map = {
    "doctor": "Physician (MD/DO)",
    "nppa": "APP (PA/NP)",
    "nurse": "Nursing (RN)",
    "admin": "Administration"
}
df['Role_Display'] = df['Role_DB'].map(role_map).fillna(df['Role_DB'])

# 3. Add Emoji Logic to Status
def format_status(val):
    if "Available" in val: return "🟢 Available"
    if "Busy" in val: return f"🔴 {val}" # Busy (Patient Name)
    return f"⚪ {val}"
    
df['Status_Display'] = df['Current_Status'].apply(format_status)

# ---------------------------------------------------------
# 3. HEADER METRICS (QUICK STATUS)
# ---------------------------------------------------------
# Calculate Available vs Total for each group
def get_stats(role_key):
    sub = df[df['Role_DB'] == role_key]
    total = len(sub)
    free = len(sub[sub['Current_Status'] == "Available"])
    return free, total

doc_free, doc_total = get_stats("doctor")
app_free, app_total = get_stats("nppa")
rn_free, rn_total = get_stats("nurse")

with st.container(border=True):
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Physicians Available", f"{doc_free}/{doc_total}", help="MDs ready for new patients")
    m2.metric("APPs Available", f"{app_free}/{app_total}", help="Mid-Levels ready")
    m3.metric("Nurses Available", f"{rn_free}/{rn_total}", help="RNs ready")
    
    if m4.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()

st.write("") # Spacer

# ---------------------------------------------------------
# 4. MAIN DIRECTORY & SEARCH
# ---------------------------------------------------------
col_search, col_blank = st.columns([1, 2])
search_term = col_search.text_input("🔍 Search Personnel", placeholder="Find by name...")

# Filter by Search
display_df = df.copy()
if search_term:
    display_df = display_df[display_df['Name'].str.contains(search_term, case=False)]

# TABS
t1, t2, t3, t4 = st.tabs(["👨‍⚕️ Physicians", "💊 APP / Mid-Level", "👩‍⚕️ Nurses", "🛡️ Admin"])

def render_grid(role_key):
    # Filter by Role
    subset = display_df[display_df['Role_DB'] == role_key].copy()
    
    if subset.empty:
        st.info("No staff found matching criteria.")
        return

    # Sort: Busy people on top (to see who is working), then alphabetical
    subset['is_busy'] = subset['Current_Status'].apply(lambda x: 0 if "Available" in x else 1)
    subset = subset.sort_values(by=['is_busy', 'Name'], ascending=[False, True])
    
    st.dataframe(
        subset[['Name', 'Status_Display', 'Location', 'Patients Seen']],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Name": st.column_config.TextColumn("Staff Member", width="medium"),
            "Status_Display": st.column_config.TextColumn("Live Status", width="medium"),
            "Location": st.column_config.TextColumn("Current Location", width="medium"),
            "Patients Seen": st.column_config.ProgressColumn(
                "Shift Workload",
                help="Cumulative encounters this shift",
                format="%d Patients",
                min_value=0,
                max_value=12, # Cap at 12 for visual scaling
            ),
        },
        height=(len(subset) + 1) * 35 + 3 # Dynamic Height
    )

with t1: render_grid("doctor")
with t2: render_grid("nppa")
with t3: render_grid("nurse")
with t4: render_grid("admin")

st.sidebar.markdown("---")
# Use get() with a default value just in case
name_display = st.session_state.get('full_name', 'Staff Member')
st.sidebar.caption(f"LOGGED IN AS: {name_display}")

if st.sidebar.button("🚪 Sign Out", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.username = None
    st.session_state.full_name = None # Clear it
    st.rerun()