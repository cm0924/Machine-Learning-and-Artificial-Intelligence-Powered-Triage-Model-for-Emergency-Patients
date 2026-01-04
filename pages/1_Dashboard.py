import streamlit as st
import database
import pandas as pd
import time
from datetime import datetime

# ---------------------------------------------------------
# SECURITY CHECK
# ---------------------------------------------------------
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ Access Restricted. Redirecting to Login...")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()
    
st.set_page_config(page_title="ED Live Track Board", layout="wide", page_icon="🏥")

# --- CSS STYLING ---
st.markdown("""
<style>
    .block-container {padding-top: 1.5rem; padding-bottom: 3rem;}
    div[data-testid="metric-container"] {
        background-color: #f8f9fa; border: 1px solid #dee2e6;
        padding: 10px; border-radius: 8px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    .action-bar {
        background-color: #e3f2fd; padding: 15px;
        border-radius: 10px; border-left: 5px solid #2196f3;
        margin-top: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 1. LOAD DATA & MAPPING
# ---------------------------------------------------------
df_patients = database.get_all_patients()
active_patients = df_patients[df_patients['status'] != 'Discharged'].copy()

# Fix Stale Selection
if 'selected_patient_id' in st.session_state and st.session_state.selected_patient_id is not None:
    valid_ids = active_patients['id'].tolist()
    if st.session_state.selected_patient_id not in valid_ids:
        st.session_state.selected_patient_id = None
        st.rerun()

# Map Patients to Departments
beds_df = database.get_all_beds()
patient_dept_map = dict(zip(beds_df['current_patient_id'], beds_df['department']))

def get_patient_dept(pid):
    return patient_dept_map.get(pid, "Emergency")

active_patients['current_dept'] = active_patients['id'].apply(get_patient_dept)

# Metrics Data
total_beds = len(beds_df)
er_beds_free = len(beds_df[(beds_df['department'] == 'Emergency') & (beds_df['status'] == 'Available')])
md_list = [""] + database.get_available_staff("doctor")

# ---------------------------------------------------------
# 2. HEADER & KPI BOARD
# ---------------------------------------------------------

# --- KPI METRICS CALCULATION ---
# 1. Waiting: Status is 'Waiting'
waiting_count = len(active_patients[active_patients['status'] == 'Waiting'])

# 2. In Treatment: STRICTLY 'In-Treatment' (Excludes ICU/Ward 'Admitted')
in_treatment_count = len(active_patients[active_patients['status'] == 'In-Treatment'])

# 3. Total ER Load (Waiting + In Treatment)
er_total_load = waiting_count + in_treatment_count

col_brand, col_clock, col_refresh = st.columns([6, 2, 1], vertical_alignment="bottom")
with col_brand:
    st.title("🏥 ED Live Track Board")
    # UPDATED: Uses er_total_load instead of all active patients
    st.caption(f"System Status: ONLINE • {er_total_load} Active ER Encounters") 
with col_clock:
    st.markdown(f"**{datetime.now().strftime('%d %b %Y')}**")
    st.markdown(f"**{datetime.now().strftime('%H:%M')}**")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Waiting Room", waiting_count, "To Triage", delta_color="inverse")

# UPDATED: Uses in_treatment_count
m2.metric("In Treatment", in_treatment_count, "ER Beds Active") 

est_wait = int((waiting_count * 15) / max(1, len(md_list)-1))
m3.metric("Est. Wait Time", f"{est_wait} min", "Avg", delta_color="inverse" if est_wait > 30 else "normal")

bed_color = "normal" if er_beds_free > 3 else "inverse"
m4.metric("ER Bed Capacity", f"{er_beds_free} Free", f"Total: {total_beds}", delta_color=bed_color)

nedocs = min(200, (er_total_load / 20) * 100) # Updated calculation base
m5.metric("Crowding Score", f"{int(nedocs)}", "Load Index", delta_color="inverse" if nedocs > 80 else "normal")

st.write("---")

# ---------------------------------------------------------
# 3. THE TRACK BOARD (Context Filtered)
# ---------------------------------------------------------
# Layout: Toolbar Row (Title Left, Filter Right) - This fixes the alignment
c_track_title, c_track_filter = st.columns([6, 2], vertical_alignment="bottom")

with c_track_title:
    st.subheader("📋 Patient Tracking")

with c_track_filter:
    # Filter is now clearly separated above the tabs
    view_context = st.selectbox(
        "Department View", 
        ["Emergency", "ICU", "Ward", "All Operations"],
        index=0,
        help="Select 'Emergency' to see only ER patients. Transferring a patient to ICU removes them from this view."
    )

# FILTER LOGIC
if view_context == "All Operations":
    filtered_active = active_patients
else:
    if view_context == "Emergency":
        filtered_active = active_patients[
            (active_patients['current_dept'] == 'Emergency') | 
            (active_patients['status'] == 'Waiting')
        ]
    else:
        filtered_active = active_patients[active_patients['current_dept'] == view_context]

# Split Data based on Filter
waiting_queue = filtered_active[filtered_active['status'] == 'Waiting']
in_progress = filtered_active[filtered_active['status'] != 'Waiting']

# Render Tabs (Full Width)
tab_wait, tab_active = st.tabs([f"⏳ Waiting ({len(waiting_queue)})", f"🛏️ Floor ({len(in_progress)})"])

selected_id = None

# --- TAB 1: WAITING ROOM ---
with tab_wait:
    if not waiting_queue.empty:
        all_users = database.get_all_users()
        name_map = dict(zip(all_users['username'], all_users['full_name']))
        
        def format_acuity(val):
            if val == 1: return "🔴 Level 1 (Resus)"
            if val == 2: return "🟠 Level 2 (Emergent)"
            if val == 3: return "🟡 Level 3 (Urgent)"
            return f"🟢 Level {val}"

        display_q = waiting_queue[['id', 'arrival_time', 'name', 'triage_level', 'complaint', 'triage_nurse']].copy()
        display_q['triage_nurse'] = display_q['triage_nurse'].map(name_map).fillna(display_q['triage_nurse'])
        display_q['triage_level'] = display_q['triage_level'].apply(format_acuity)

        event_q = st.dataframe(
            display_q,
            column_config={
                "id": st.column_config.NumberColumn("MRN", width="small"),
                "arrival_time": st.column_config.DatetimeColumn("Arrival", format="h:mm a"),
                "triage_level": st.column_config.TextColumn("Acuity", width="medium"),
                "complaint": "Chief Complaint",
                "triage_nurse": "Triage Nurse"
            },
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="grid_waiting"
        )
        if len(event_q.selection.rows) > 0:
            selected_id = display_q.iloc[event_q.selection.rows[0]]['id']
    else:
        st.success(f"✅ {view_context} Waiting Queue is Empty.")

# --- TAB 2: ACTIVE FLOOR ---
with tab_active:
    if not in_progress.empty:
        def get_loc(pid): return database.get_patient_bed(pid)
        
        display_a = in_progress[['id', 'name', 'triage_level', 'assigned_md', 'assigned_nurse', 'status']].copy()
        display_a['Location'] = display_a['id'].apply(get_loc)
        display_a = display_a[['Location', 'name', 'triage_level', 'assigned_md', 'assigned_nurse', 'status', 'id']]

        event_a = st.dataframe(
            display_a,
            column_config={
                "Location": st.column_config.TextColumn("Room/Bed", width="small"),
                "id": st.column_config.NumberColumn("MRN", width="small"),
                "triage_level": st.column_config.NumberColumn("KTAS", width="small"),
                "assigned_md": "Provider",
                "assigned_nurse": "Nurse",
                "status": st.column_config.SelectboxColumn("Status", options=["In-Treatment", "Admitted"]),
            },
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="grid_active"
        )
        if len(event_a.selection.rows) > 0:
            selected_id = display_a.iloc[event_a.selection.rows[0]]['id']
    else:
        st.info(f"No active patients on the {view_context} floor.")

# ---------------------------------------------------------
# 4. ACTION COMMAND STRIP
# ---------------------------------------------------------
@st.dialog("🏥 Initiate Encounter")
def show_treatment_popup(patient_id, name):
    st.write(f"Assigning Care Team for **{name}**")
    
    d_mds = [""] + database.get_available_staff("doctor")
    d_nurses = [""] + database.get_available_staff("nurse")
    d_nppa = [""] + database.get_available_staff("nppa")
    
    beds = database.get_available_beds_list()
    bed_map = {f"{r['bed_label']} ({r['department']})": r['id'] for i, r in beds.iterrows()}
    
    with st.form("tx_form"):
        c1, c2 = st.columns(2)
        with c1:
            s_bed = st.selectbox("Assign Bed", ["No Bed"] + list(bed_map.keys()))
            s_md = st.selectbox("Provider (MD)", d_mds)
        with c2:
            s_rn = st.selectbox("Primary Nurse", d_nurses)
            s_app = st.selectbox("Mid-Level (APP)", d_nppa)
        
        note = st.text_area("HPI Note", placeholder="Initial assessment...")
        
        if st.form_submit_button("✅ Activate", type="primary"):
            bid = bed_map.get(s_bed) if s_bed != "No Bed" else None
            user = st.session_state.get('username', 'Unknown')
            
            success = database.start_treatment_detailed(
                patient_id, s_md, s_app, s_rn, bid, note, 
                author_username=user
            )
            if success:
                st.success("Started")
                st.session_state.selected_patient_id = None
                time.sleep(0.5)
                st.rerun()

@st.dialog("⇄ Transfer Patient")
def show_transfer_popup(patient_id, name, current_loc):
    st.write(f"Transferring **{name}** from **{current_loc}**")
    st.caption("Use this to move patients between beds (Internal or ICU Transfer).")
    
    beds = database.get_available_beds_list()
    bed_map = {f"{r['bed_label']} ({r['department']})": r['id'] for i, r in beds.iterrows()}
    
    with st.form("transfer_form"):
        dest = st.selectbox("Destination Bed", list(bed_map.keys()))
        reason = st.text_input("Reason", placeholder="e.g. ICU Upgrade")
        
        if st.form_submit_button("Confirm Transfer"):
            user = st.session_state.get('username', 'Unknown')
            if database.transfer_patient(patient_id, bed_map[dest], reason, author_username=user):
                st.success("Transfer Complete")
                st.rerun()

@st.dialog("✅ Final Disposition")
def show_discharge_popup(patient_id, name):
    st.write(f"End encounter for **{name}**?")
    st.info("""
    💡 **Workflow Tip:**
    - To **Admit to a specific Room** (ICU/Ward), use the **'Transfer / Move'** button instead.
    - Use this menu for **Discharge Home** or transfers outside this hospital.
    """)
    
    dispo = st.selectbox("Decision", [
        "Home (Discharge)", 
        "Transfer to External Facility", 
        "Left Without Being Seen (LWBS)",
        "Admit (No Bed Assigned / Holding)"
    ])
    
    if st.button("Finalize Encounter", type="primary"):
        db_disp = "Home"
        if "Admit" in dispo: db_disp = "Admit"
        elif "Transfer" in dispo: db_disp = "Transfer"
        elif "LWBS" in dispo: db_disp = "LWBS"
        
        with st.spinner("Processing..."):
            if database.discharge_patient_and_free_bed(patient_id, db_disp):
                st.success("Finalized")
                st.session_state.selected_patient_id = None
                time.sleep(1)
                st.rerun()

# ACTION STRIP RENDER
if selected_id:
    st.session_state.selected_patient_id = int(selected_id)
    pt = df_patients[df_patients['id'] == selected_id].iloc[0]
    curr_loc = database.get_patient_bed(selected_id)
    
    st.markdown(f"""
    <div class="action-bar">
        <h3 style="margin:0; color:#0d47a1;">⚙️ Selected: {pt['name']}</h3>
        <p style="margin:0; color:#555;">MRN: {selected_id} &bull; Location: <b>{curr_loc}</b> &bull; Status: {pt['status']}</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.write("") 
    
    ac1, ac2, ac3, ac4 = st.columns(4)
    
    with ac1:
        if st.button("📂 Open Chart", use_container_width=True, type="primary"):
            st.switch_page("pages/4_Patient_Details.py")
            
    with ac2:
        if pt['status'] == "Waiting":
            if st.button("▶️ Start Treatment", use_container_width=True):
                show_treatment_popup(selected_id, pt['name'])
        else:
            if st.button("⇄ Transfer / Move", use_container_width=True, help="Move to a different bed (ER or ICU)"):
                show_transfer_popup(selected_id, pt['name'], curr_loc)

    with ac3:
         if st.button("🛏️ Bed Manager", use_container_width=True):
             st.switch_page("pages/8_Bed_Manager.py")

    with ac4:
        if pt['status'] != "Waiting":
            if st.button("✅ Disposition", use_container_width=True, type="secondary", help="End encounter (Admit/Home)"):
                show_discharge_popup(selected_id, pt['name'])
        else:
             st.button("🚫 Cancel", use_container_width=True, disabled=True)

else:
    st.markdown("""
    <div style="text-align:center; padding: 40px; color:#aaa; border: 2px dashed #ddd; border-radius:10px; margin-top:20px;">
        👇 Select a patient from the <b>Waiting Queue</b> or <b>Active Floor</b> to view actions.
    </div>
    """, unsafe_allow_html=True)

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