# pages/3_Staff_Directory.py
import streamlit as st
import database
import pandas as pd
import time

st.set_page_config(page_title="Staff Directory", page_icon="📋", layout="wide")

# 1. AUTH CHECK
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

st.title("📋 Live Staff Directory")
st.markdown("Real-time tracking of staff availability, location, and shift workload.")

col_ref, col_blank = st.columns([1, 5])
if col_ref.button("🔄 Refresh Board"):
    st.rerun()

# 2. FETCH DATA
df = database.get_staff_status_report()

if not df.empty:
    df = df.rename(columns={"full_name": "Staff Name", "role": "Role"})
    
    # 3. RENDER TABS
    t1, t2, t3, t4 = st.tabs(["👨‍⚕️ Physicians", "💊 APP / Mid-Level", "👩‍⚕️ Nurses", "🛡️ Admin"])
    
    def render_staff_grid(role_key):
        filtered = df[df['Role'] == role_key].copy()
        
        # Sort by Status (Busy first) then Name
        filtered = filtered.sort_values(by=['Status', 'Staff Name'], ascending=[False, True])
        
        # Add Emoji for visual scanning
        filtered['Status'] = filtered['Status'].apply(
            lambda x: f"🟢 {x}" if x == "Available" else f"🔴 {x}"
        )
        
        st.dataframe(
            filtered[['Staff Name', 'Status', 'Location', 'Patients Seen']],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Status": st.column_config.TextColumn("Availability"),
                "Location": st.column_config.TextColumn("Current Location"),
                "Patients Seen": st.column_config.ProgressColumn(
                    "Shift Workload",
                    help="Total patients treated/assigned since database start.",
                    format="%d",
                    min_value=0,
                    max_value=15, # Cap at 15 for visual scaling
                ),
            }
        )

    with t1:
        render_staff_grid("doctor") 
    with t2:
        render_staff_grid("nppa")
    with t3:
        render_staff_grid("nurse")
    with t4:
        render_staff_grid("admin")

else:
    st.error("No staff found in database.")