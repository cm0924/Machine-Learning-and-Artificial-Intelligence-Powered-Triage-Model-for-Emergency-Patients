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
# DIALOG FUNCTION (The Popup Window)
# ---------------------------------------------------------
@st.dialog("🏥 Initiate Treatment Protocol")
def show_treatment_popup(patient_id, current_name):
    st.write(f"Assigning Care Team for **{current_name}**")
    
    # 1. Fetch Dropdown Options
    md_opts = [""] + database.get_staff_by_role("doctor")
    nppa_opts = [""] + database.get_staff_by_role("nppa")
    nurse_opts = [""] + database.get_staff_by_role("nurse")
    
    # Bed Options: Format as "ER-01 (Emergency)"
    beds_df = database.get_available_beds_list()
    bed_map = {f"{row['bed_label']} ({row['department']})": row['id'] for i, row in beds_df.iterrows()}
    bed_options = ["No Bed Assignment"] + list(bed_map.keys())

    # 2. Form Inputs
    with st.form("treatment_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**👨‍⚕️ Care Team**")
            sel_md = st.selectbox("Attending Physician (MD)", md_opts)
            sel_nppa = st.selectbox("Mid-Level (NP/PA)", nppa_opts)
            sel_nurse = st.selectbox("Primary Nurse", nurse_opts)
            
        with col2:
            st.markdown("**📍 Location & Time**")
            # If patient already has a bed, logic could be added to show it. 
            # For now, we show available beds to room them.
            sel_bed_label = st.selectbox("Assign Room/Bed", bed_options)
            
            # Time Recording
            start_time = st.time_input("Provider Start Time", value="now")
            
        initial_note = st.text_area("Initial Provider Note", placeholder="e.g. Patient seen, assessment started...")
        
        # 3. Submit
        if st.form_submit_button("✅ Confirm & Start", type="primary"):
            # Determine Bed ID
            selected_bed_id = bed_map.get(sel_bed_label) if sel_bed_label != "No Bed Assignment" else None
            
            # Save to DB
            success = database.start_treatment_detailed(
                patient_id=patient_id,
                md=sel_md,
                nppa=sel_nppa,
                nurse=sel_nurse,
                bed_id=selected_bed_id,
                notes=f" (Started at {start_time}) - {initial_note}"
            )
            
            if success:
                st.toast("Treatment Protocol Initiated!", icon="👨‍⚕️")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Database Error.")

# ---------------------------------------------------------
# 4. ACTION BAR (Updated Logic)
# ---------------------------------------------------------
st.markdown("---")

if selected_patient_id:
    # Fetch latest data
    p_data = df_patients[df_patients['id'] == selected_patient_id]
    
    if not p_data.empty:
        p_row = p_data.iloc[0]
        p_name = p_row['name']
        p_status = p_row['status']
        
        st.markdown(f"### ⚙️ Actions for: **{p_name}** (Status: {p_status})")
        
        col_a, col_b, col_c = st.columns(3)
        
        # 1. OPEN CHART
        with col_a:
            if st.button("📂 Open Medical Chart", type="primary", use_container_width=True):
                st.switch_page("pages/4_Patient_Details.py")

        # 2. WORKFLOW (The Popup Trigger)
        with col_b:
            if p_status == "Waiting":
                # BUTTON TRIGGERS THE POPUP
                if st.button("👨‍⚕️ Start Treatment", use_container_width=True):
                    show_treatment_popup(selected_patient_id, p_name)
            
            else:
                # Discharge Logic (Same as before)
                if st.button("✅ Discharge Patient", use_container_width=True):
                    database.discharge_patient_and_free_bed(selected_patient_id)
                    st.success(f"{p_name} discharged. Bed marked as 'Cleaning'.")
                    time.sleep(1.5)
                    st.rerun()

        # 3. BED MANAGER
        with col_c:
            if st.button("🛏️ Bed Manager", use_container_width=True):
                st.switch_page("pages/9_Bed_Manager.py")
                
    else:
        st.error("Patient data not found. Please refresh.")
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