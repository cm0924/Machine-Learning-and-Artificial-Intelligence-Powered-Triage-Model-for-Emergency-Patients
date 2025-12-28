# pages/1_Dashboard.py
import streamlit as st
import database
import pandas as pd
import time

# ---------------------------------------------------------
# SECURITY CHECK (Add this to top of every page)
# ---------------------------------------------------------
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py") # Kicks them back to login
    st.stop()
    
st.set_page_config(page_title="ED Live Status", layout="wide", page_icon="🏥")

# --- HEADER & REFRESH ---
col_header, col_refresh = st.columns([5, 1])
with col_header:
    st.title("🏥 Emergency Department Status Board")
with col_refresh:
    st.write("##") # Spacer to align button
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()

# ---------------------------------------------------------
# 1. LOAD DATA & CALCULATE METRICS
# ---------------------------------------------------------
df = database.get_all_patients()

# Load Staff Lists
md_list = [""] + database.get_staff_by_role("ED MD")
nppa_list = [""] + database.get_staff_by_role("ED NP/PA")
nurse_list = [""] + database.get_staff_by_role("Nurse")

# Filter Active Patients
active_patients = df[df['status'] != 'Discharged'].copy()
waiting_patients = active_patients[active_patients['status'] == 'Waiting']

# Simulation Logic
TOTAL_BEDS = 20
occupied = len(active_patients) - len(waiting_patients)
dirty_beds = 2 
ready_beds = max(0, TOTAL_BEDS - occupied - dirty_beds)
doc_count = max(1, len(md_list) - 1)
est_wait = int((len(waiting_patients) * 15) / doc_count)

# ---------------------------------------------------------
# 2. STATUS BOARD (KPIs)
# ---------------------------------------------------------
st.markdown("### 📊 Real-Time Metrics")

# Custom CSS for "Card" look
st.markdown("""
<style>
    div[data-testid="metric-container"] {
        background-color: #ffffff;
        border: 1px solid #e6e6e6;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Active Patients", len(active_patients), "Current Load")
m2.metric("Waiting Room", len(waiting_patients), "Needs Triage", delta_color="inverse")
m3.metric("Est. Wait Time", f"{est_wait} min", "Avg per patient")
m4.metric("Beds Ready", ready_beds, f"Total Capacity: {TOTAL_BEDS}")
m5.metric("Staff On-Duty", len(md_list) + len(nurse_list) - 2, "MDs + Nurses")

st.markdown("---")

# ---------------------------------------------------------
# 3. PATIENT TRACKING (Interactive Selection)
# ---------------------------------------------------------
st.subheader(f"📋 Patient Queue ({len(waiting_patients)} Waiting)")

selected_patient_id = None

if not active_patients.empty:
    display_df = active_patients[['id', 'arrival_time', 'name', 'triage_level', 'status', 'assigned_md', 'assigned_nurse']]
    
    event = st.dataframe(
        display_df,
        column_config={
            "id": st.column_config.NumberColumn("ID", width="small"),
            "arrival_time": st.column_config.DatetimeColumn("Arrival", format="h:mm a"),
            "name": st.column_config.TextColumn("Patient Name"),
            "triage_level": st.column_config.NumberColumn("KTAS", width="small"),
            "status": st.column_config.SelectboxColumn("Status", options=["Waiting", "In-Treatment", "Admitted"]),
            "assigned_md": st.column_config.SelectboxColumn("ED MD", options=md_list),
            "assigned_nurse": st.column_config.SelectboxColumn("Nurse", options=nurse_list),
        },
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    if len(event.selection.rows) > 0:
        selected_index = event.selection.rows[0]
        selected_patient_id = display_df.iloc[selected_index]['id']
        st.session_state['selected_patient_id'] = int(selected_patient_id)

else:
    st.info("✅ No active patients in the system.")

# ---------------------------------------------------------
# 4. ACTION BAR (Bottom Controls)
# ---------------------------------------------------------
st.markdown("---")

if selected_patient_id:
    # Get Name
    p_name = active_patients[active_patients['id'] == selected_patient_id]['name'].values[0]
    
    st.markdown(f"### ⚙️ Actions for: **{p_name}** (ID: {selected_patient_id})")
    
    col_a, col_b, col_c = st.columns(3)
    
    # 1. VIEW DETAILS
    with col_a:
        if st.button("📂 Open Medical Chart", type="primary", use_container_width=True):
            st.switch_page("pages/4_Patient_Details.py")
            
    # 2. DISCHARGE
    with col_b:
        if st.button("✅ Treat & Discharge", use_container_width=True):
            database.discharge_patient(selected_patient_id)
            st.toast(f"{p_name} discharged!", icon="👋")
            time.sleep(1)
            st.rerun()
            
    # 3. ASSIGN BED
    with col_c:
        if st.button("🛏️ Assign Bed", use_container_width=True):
            database.update_patient_status(selected_patient_id, "In-Treatment")
            st.toast(f"Bed assigned to {p_name}.", icon="🛏️")
            time.sleep(1)
            st.rerun()
            
else:
    # Empty State (Helper Text)
    st.caption("👆 **Select a patient** from the list above to view actions (Open Chart / Discharge).")
    
# ---------------------------------------------------------
# SIDEBAR LOGOUT BUTTON
# ---------------------------------------------------------
st.sidebar.markdown("---") # Visual separator
st.sidebar.subheader("👤 User: " + st.session_state.get('user_role', 'Nurse'))

if st.sidebar.button("🚪 Log Out", type="secondary", use_container_width=True):
    # 1. Clear Session State
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.selected_patient_id = None
    
    # 2. Redirect to Login Page (app.py)
    st.switch_page("app.py")