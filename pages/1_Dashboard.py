# pages/1_Dashboard.py
import streamlit as st
import database
import pandas as pd
import time

# ---------------------------------------------------------
# SECURITY CHECK
# ---------------------------------------------------------
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()
    
st.set_page_config(page_title="ED Live Status", layout="wide", page_icon="🏥")

# --- HEADER & REFRESH ---
col_header, col_refresh = st.columns([5, 1])
with col_header:
    st.title("🏥 Emergency Department Status Board")
with col_refresh:
    st.write("##") # Spacer
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()

# ---------------------------------------------------------
# 1. LOAD DATA & CALCULATE METRICS
# ---------------------------------------------------------
# A. Get Patients
df_patients = database.get_all_patients()
active_patients = df_patients[df_patients['status'] != 'Discharged'].copy()
waiting_patients = active_patients[active_patients['status'] == 'Waiting']

# B. Get Staff Lists
md_list = [""] + database.get_staff_by_role("doctor") # Updated to match DB role 'doctor'
# Note: If you don't have distinct NP/PA roles in DB yet, we just handle what exists
nppa_list = [""] # Placeholder if not in DB yet
nurse_list = [""] + database.get_staff_by_role("nurse")

# C. Get Real-Time Bed Data
beds_df = database.get_all_beds()

# Calculate Available Beds by Department
er_beds_total = len(beds_df[beds_df['department'] == 'Emergency'])
er_beds_free = len(beds_df[(beds_df['department'] == 'Emergency') & (beds_df['status'] == 'Available')])

icu_beds_free = len(beds_df[(beds_df['department'] == 'ICU') & (beds_df['status'] == 'Available')])
ward_beds_free = len(beds_df[(beds_df['department'] == 'Ward') & (beds_df['status'] == 'Available')])

# D. Calculate Wait Time Logic
doc_count = max(1, len(md_list) - 1)
est_wait = int((len(waiting_patients) * 15) / doc_count)

# ---------------------------------------------------------
# 2. STATUS BOARD (KPIs)
# ---------------------------------------------------------
st.markdown("### 📊 Real-Time Metrics")

# Custom CSS for cards
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

# Metric 1: Active Patients
m1.metric("Active Patients", len(active_patients), "Current Load")

# Metric 2: Waiting Room
m2.metric("Waiting Room", len(waiting_patients), "Needs Triage", delta_color="inverse")

# Metric 3: Wait Time
m3.metric("Est. Wait Time", f"{est_wait} min", "Avg per patient")

# Metric 4: BEDS (The Logic You Requested)
# We prioritize ER. If ER beds are low (< 3), we show red.
bed_delta_color = "normal" if er_beds_free > 3 else "inverse"
m4.metric(
    label="🚨 ER Beds Free", 
    value=f"{er_beds_free} / {er_beds_total}", 
    delta=f"ICU: {icu_beds_free} | Ward: {ward_beds_free}",
    delta_color=bed_delta_color 
)

# Metric 5: Staff
m5.metric("Staff On-Duty", len(md_list) + len(nurse_list) - 2, "MDs + Nurses")

st.markdown("---")

# ---------------------------------------------------------
# 3. PATIENT TRACKING (Interactive Selection)
# ---------------------------------------------------------
st.subheader(f"📋 Patient Queue ({len(waiting_patients)} Waiting)")

selected_patient_id = None

if not active_patients.empty:
    # We display a cleaner version of the table
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
# 4. ACTION BAR
# ---------------------------------------------------------
st.markdown("---")

if selected_patient_id:
    # Fetch specific patient name safely
    p_data = active_patients[active_patients['id'] == selected_patient_id]
    if not p_data.empty:
        p_name = p_data.iloc[0]['name']
        
        st.markdown(f"### ⚙️ Actions for: **{p_name}** (ID: {selected_patient_id})")
        
        col_a, col_b, col_c = st.columns(3)
        
        # 1. VIEW CHART
        with col_a:
            if st.button("📂 Open Medical Chart", type="primary", use_container_width=True):
                # Note: Ensure you have pages/4_Patient_Details.py created or change this link
                st.switch_page("pages/5_Patient_Details.py") 
                
        # 2. DISCHARGE
        with col_b:
            if st.button("✅ Treat & Discharge", use_container_width=True):
                database.discharge_patient(selected_patient_id)
                # Also free up the bed if they had one (Optional logic, but good for data integrity)
                # For now, simplistic discharge:
                st.toast(f"{p_name} discharged!", icon="👋")
                time.sleep(1)
                st.rerun()
                
        # 3. ASSIGN BED LINK
        with col_c:
            if st.button("🛏️ Go to Bed Manager", use_container_width=True):
                st.switch_page("pages/4_Bed_Manager.py")
    else:
        st.error("Selected patient no longer active.")
else:
    st.caption("👆 **Select a patient** from the list above to view actions.")
    
# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("👤 User: " + str(st.session_state.get('user_role', 'Staff').title()))

if st.sidebar.button("🚪 Log Out", type="secondary", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.selected_patient_id = None
    st.switch_page("app.py")