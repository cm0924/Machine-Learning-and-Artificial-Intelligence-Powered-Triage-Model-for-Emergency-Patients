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

# --- FIX: STALE DATA CLEANER ---
# If the browser remembers a patient ID that no longer exists in the DB (e.g., after DB reset), clear it.
if 'selected_patient_id' in st.session_state and st.session_state.selected_patient_id is not None:
    valid_ids = active_patients['id'].tolist()
    if st.session_state.selected_patient_id not in valid_ids:
        st.toast("⚠️ Data was reset. Clearing selection.")
        st.session_state.selected_patient_id = None
        st.rerun()
# -------------------------------

waiting_patients = active_patients[active_patients['status'] == 'Waiting']

# B. Get Staff Lists
md_list = [""] + database.get_staff_by_role("doctor")
nppa_list = [""] + database.get_staff_by_role("nppa")
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

bed_delta_color = "normal" if er_beds_free > 3 else "inverse"
m4.metric(
    label="🚨 ER Beds Free", 
    value=f"{er_beds_free} / {er_beds_total}", 
    delta=f"ICU: {icu_beds_free} | Ward: {ward_beds_free}",
    delta_color=bed_delta_color 
)

m5.metric("Staff On-Duty", len(md_list) + len(nurse_list) - 2, "MDs + Nurses")

st.markdown("---")

# ---------------------------------------------------------
# 3. PATIENT TRACKING (Interactive Selection)
# ---------------------------------------------------------
st.subheader(f"📋 Patient Queue ({len(waiting_patients)} Waiting)")

selected_patient_id = None

if not active_patients.empty:
    # --- NAME ALERT LOGIC ---
    name_counts = active_patients['name'].value_counts()
    duplicates = name_counts[name_counts > 1].index.tolist()

    def flag_name(row):
        name = row['name']
        if name in duplicates: return f"🚨 {name} (NAME ALERT)"
        return name

    display_df = active_patients[['id', 'arrival_time', 'name', 'triage_level', 'status', 'assigned_md', 'assigned_nurse']].copy()
    display_df['name'] = display_df.apply(flag_name, axis=1)

    event = st.dataframe(
        display_df,
        column_config={
            "id": st.column_config.NumberColumn("ID", width="small"),
            "arrival_time": st.column_config.DatetimeColumn("Arrival", format="h:mm a"),
            "name": st.column_config.TextColumn("Patient Name", help="🚨 indicates duplicate names."),
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
# DIALOGS (Popups)
# ---------------------------------------------------------

# A. TREATMENT POPUP
@st.dialog("🏥 Initiate Treatment Protocol")
def show_treatment_popup(patient_id, current_name):
    st.write(f"Assigning Care Team for **{current_name}**")
    
    md_opts = [""] + database.get_available_staff("doctor")
    nppa_opts = [""] + database.get_available_staff("nppa")
    nurse_opts = [""] + database.get_available_staff("nurse")
    
    beds_df = database.get_available_beds_list()
    bed_map = {f"{row['bed_label']} ({row['department']})": row['id'] for i, row in beds_df.iterrows()}
    bed_options = ["No Bed Assignment"] + list(bed_map.keys())

    with st.form("treatment_form"):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**👨‍⚕️ Care Team**")
            sel_md = st.selectbox("Attending Physician (MD)", md_opts)
            sel_nppa = st.selectbox("Mid-Level (NP/PA)", nppa_opts)
            sel_nurse = st.selectbox("Primary Nurse", nurse_opts)
        with col2:
            st.markdown("**📍 Location & Time**")
            sel_bed_label = st.selectbox("Assign Room/Bed", bed_options)
            start_time = st.time_input("Provider Start Time", value="now")
            
        initial_note = st.text_area("Initial Provider Note", placeholder="e.g. Patient seen, assessment started...")
        
        if st.form_submit_button("✅ Confirm & Start", type="primary"):
            selected_bed_id = bed_map.get(sel_bed_label) if sel_bed_label != "No Bed Assignment" else None
            success = database.start_treatment_detailed(
                patient_id=patient_id, md=sel_md, nppa=sel_nppa, nurse=sel_nurse,
                bed_id=selected_bed_id, notes=f" (Started at {start_time}) - {initial_note}"
            )
            if success:
                st.toast("Treatment Protocol Initiated!", icon="👨‍⚕️")
                time.sleep(1)
                st.cache_data.clear() 
                st.rerun()
            else:
                st.error("Database Error.")

# B. TRANSFER / CHANGE ROOM POPUP (NEW)
@st.dialog("⇄ Transfer Patient / Change Room")
def show_transfer_popup(patient_id, current_name, current_loc):
    st.write(f"Transferring **{current_name}**")
    st.info(f"📍 Current Location: **{current_loc}**")
    
    # Available Beds
    beds_df = database.get_available_beds_list()
    bed_map = {f"{row['bed_label']} ({row['department']})": row['id'] for i, row in beds_df.iterrows()}
    
    with st.form("transfer_form"):
        new_bed_label = st.selectbox("Select New Destination", list(bed_map.keys()))
        reason = st.text_input("Reason for Transfer", placeholder="e.g. Isolation required, Upgrade to ICU...")
        
        if st.form_submit_button("⇄ Confirm Transfer"):
            new_bed_id = bed_map[new_bed_label]
            
            # PASS THE REASON HERE
            success = database.transfer_patient(patient_id, new_bed_id, reason) 
            
            if success:
                st.success(f"Patient moved to {new_bed_label}")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Transfer Failed.")

# ---------------------------------------------------------
# 4. ACTION BAR (Updated with Safe Discharge)
# ---------------------------------------------------------
st.markdown("---")

# --- IMPROVED DISPOSITION DIALOG ---
@st.dialog("🏥 Clinical Disposition (End Encounter)")
def confirm_discharge(patient_id, name, bed_label):
    st.write(f"Finalizing encounter for **{name}** in **{bed_label}**.")
    
    # 1. THE CRITICAL CHOICE
    # This determines "Who was right" in the Nurse Audit
    outcome = st.selectbox(
        "Where is the patient going?",
        [
            "Home (Discharge)", 
            "Admit to Ward (General Medicine)", 
            "Admit to ICU (Critical Care)", 
            "Transfer to Other Facility",
            "Left Without Being Seen (LWBS)"
        ]
    )
    
    st.info("📝 An AI Clinical Synopsis will be auto-generated based on this outcome.")
    
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("✅ Finalize & Release Bed", type="primary", use_container_width=True):
            with st.spinner(f"Processing {outcome}..."):
                
                # Map the user friendly string to database short-codes
                db_disp = "Home"
                if "Ward" in outcome: db_disp = "Admit"
                elif "ICU" in outcome: db_disp = "ICU"
                elif "Transfer" in outcome: db_disp = "Transfer"
                elif "LWBS" in outcome: db_disp = "LWBS"
                
                success = database.discharge_patient_and_free_bed(patient_id, disposition=db_disp)
                
                if success:
                    st.success(f"Patient moved to: {db_disp}")
                    st.session_state.selected_patient_id = None
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Database Error.")
    
    with col_no:
        if st.button("❌ Cancel", use_container_width=True):
            st.rerun()

if selected_patient_id:
    # Fetch latest data
    p_data = df_patients[df_patients['id'] == selected_patient_id]
    
    if not p_data.empty:
        p_row = p_data.iloc[0]
        p_name = p_row['name']
        p_status = p_row['status']
        
        # FEATURE: DISPLAY CURRENT ROOM
        current_bed = database.get_patient_bed(selected_patient_id)
        
        st.markdown(f"### ⚙️ Patient: **{p_name}**")
        
        # Info Bar
        c_info1, c_info2 = st.columns([1, 4])
        c_info1.info(f"📍 **{current_bed}**")
        c_info2.caption(f"Status: {p_status} | MRN: {selected_patient_id}")
        
        col_a, col_b, col_c, col_d = st.columns(4)
        
        # 1. CHART
        with col_a:
            if st.button("📂 Open Chart", type="primary", use_container_width=True):
                st.switch_page("pages/4_Patient_Details.py")

        # 2. WORKFLOW (Start/Discharge)
        with col_b:
            if p_status == "Waiting":
                if st.button("👨‍⚕️ Start Treatment", use_container_width=True):
                    show_treatment_popup(selected_patient_id, p_name)
            else:
                # UPDATED: Call the dialog instead of direct function
                if st.button("✅ Discharge", use_container_width=True):
                    confirm_discharge(selected_patient_id, p_name, current_bed)

        # 3. TRANSFER
        with col_c:
            if st.button("⇄ Change Room", use_container_width=True):
                show_transfer_popup(selected_patient_id, p_name, current_bed)

        # 4. BED MANAGER
        with col_d:
            if st.button("🛏️ Bed Grid", use_container_width=True):
                st.switch_page("pages/9_Bed_Manager.py")
                
    else:
        # If patient was just discharged, this might hit if logic is fast
        st.session_state.selected_patient_id = None
        st.rerun()
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