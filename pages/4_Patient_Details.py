import streamlit as st
import database
import pandas as pd
import time
from fpdf import FPDF
import base64
import ollama

# ---------------------------------------------------------
# SECURITY CHECK
# ---------------------------------------------------------
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

st.set_page_config(page_title="Patient Chart", layout="wide", page_icon="🗂️")

# ---------------------------------------------------------
# HELPER: TEXT SANITIZER FOR PDF
# ---------------------------------------------------------
def clean_text(text):
    """Replaces incompatible Unicode characters for FPDF."""
    if text is None: return ""
    text = str(text)
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', 
        "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00A0": " "
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text.encode('latin-1', 'replace').decode('latin-1')

# ---------------------------------------------------------
# MAPPING DICTIONARIES
# ---------------------------------------------------------
ARRIVAL_MAP = {1: "Ambulance", 2: "Walk-in", 3: "Transfer"}
MENTAL_MAP = {1: "Alert", 2: "Verbal", 3: "Pain", 4: "Unresponsive"}
INJURY_MAP = {1: "No", 2: "Yes"}
PAIN_MAP = {0: "No", 1: "Yes"}

REV_ARRIVAL = {v: k for k, v in ARRIVAL_MAP.items()}
REV_MENTAL = {v: k for k, v in MENTAL_MAP.items()}
REV_INJURY = {v: k for k, v in INJURY_MAP.items()}
REV_PAIN = {v: k for k, v in PAIN_MAP.items()}

# ---------------------------------------------------------
# PDF GENERATOR
# ---------------------------------------------------------
def create_pdf(patient, bed_label):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=clean_text("General Hospital - Clinical Encounter Record"), ln=1, align='C')
    pdf.ln(5)
    
    # Demographics
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 8, txt=clean_text(f"Patient: {patient['name']} (MRN: {patient['id']})"), ln=1)
    pdf.cell(200, 8, txt=clean_text(f"DOB: {patient.get('dob', 'N/A')} | Age/Sex: {patient['age']} / {patient['gender']}"), ln=1)
    pdf.cell(200, 8, txt=clean_text(f"Location: {bed_label} | Status: {patient['status']}"), ln=1)
    pdf.cell(200, 8, txt=clean_text(f"Arrival: {patient['arrival_time']}"), ln=1)
    pdf.line(10, 55, 200, 55)
    pdf.ln(10)
    
    # Clinical Assessment
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt=clean_text("Triage Assessment"), ln=1)
    pdf.set_font("Arial", size=11)
    pdf.cell(200, 8, txt=clean_text(f"Chief Complaint: {patient['complaint']}"), ln=1)
    pdf.cell(200, 8, txt=clean_text(f"Arrival Mode: {ARRIVAL_MAP.get(patient['arrival_mode'], 'Unknown')}"), ln=1)
    pdf.cell(200, 8, txt=clean_text(f"Trauma/Injury: {INJURY_MAP.get(patient['injury'], 'No')}"), ln=1)
    pdf.cell(200, 8, txt=clean_text(f"Mental Status: {MENTAL_MAP.get(patient['mental'], 'Alert')}"), ln=1)
    pdf.cell(200, 8, txt=clean_text(f"Pain: {PAIN_MAP.get(patient['pain'], 'No')} (NRS: {patient['nrs_pain']}/10)"), ln=1)
    pdf.ln(5)
    
    # Vitals
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt=clean_text("Vital Signs"), ln=1)
    pdf.set_font("Arial", size=11)
    pdf.cell(200, 8, txt=clean_text(f"BP: {patient['sbp']}/{patient['dbp']} mmHg"), ln=1)
    pdf.cell(200, 8, txt=clean_text(f"HR: {patient['hr']} bpm | RR: {patient['rr']} /min"), ln=1)
    pdf.cell(200, 8, txt=clean_text(f"SpO2: {patient['saturation']}% | Temp: {patient['bt']} C"), ln=1)
    pdf.ln(5)

    # Audit & Decision
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt=clean_text("Clinical Decision & Audit"), ln=1)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 8, txt=clean_text(f"Final Acuity: KTAS Level {patient['triage_level']}"), ln=1)
    pdf.cell(200, 8, txt=clean_text(f"AI Suggestion: Level {patient['ai_level']} ({patient['confidence']}%)"), ln=1)
    match_status = "ACCEPTED" if patient['ai_level'] == patient['triage_level'] else "OVERRIDDEN"
    pdf.cell(200, 8, txt=clean_text(f"Status: {match_status}"), ln=1)
    pdf.ln(5)

    # Notes
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt=clean_text("Clinical Log & Notes"), ln=1)
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 6, txt=clean_text(f"{patient['nurse_notes']}"))
    
    return pdf.output(dest='S').encode('latin-1', 'replace')

@st.dialog("⇄ Transfer / Change Room")
def show_transfer_dialog_ehr(patient_id, current_bed_label):
    st.write(f"Current Location: **{current_bed_label}**")
    
    # Get available beds
    beds_df = database.get_available_beds_list()
    # Create a map: "ICU-01 (ICU)" -> ID 5
    bed_map = {f"{row['bed_label']} ({row['department']})": row['id'] for i, row in beds_df.iterrows()}
    
    with st.form("transfer_form_ehr"):
        new_bed_label = st.selectbox("Select Destination", list(bed_map.keys()))
        reason = st.text_input("Reason for Transfer", placeholder="e.g. ICU Upgrade, Isolation, Patient Request")
        
        if st.form_submit_button("Confirm Transfer"):
            if not reason:
                st.error("Please enter a reason.")
            else:
                new_bed_id = bed_map[new_bed_label]
                
                # --- GET CURRENT USER ---
                current_user = st.session_state.get('username', 'Unknown')
                
                # --- PASS TO DATABASE ---
                success = database.transfer_patient(
                    patient_id, 
                    new_bed_id, 
                    reason, 
                    author_username=current_user # <--- NEW
                )
                
                if success:
                    st.success("Transfer Complete!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Transfer Failed.")

# ---------------------------------------------------------
# AI HELPERS
# ---------------------------------------------------------
# In pages/4_Patient_Details.py (AI HELPERS section)
def generate_illness_script(patient, logs):
    """Generates a short, high-density summary for the History Table."""
    prompt = f"""
    Act as a Senior Resident Doctor. Write a "Clinical Synopsis" (Illness Script) for:
    Patient: {patient['name']} ({patient['age']} {patient['gender']})
    Complaint: {patient['complaint']}
    Acquity: KTAS {patient['triage_level']}
    Clinical Notes: {logs}
    
    Task: Write a single, concise paragraph (max 4 sentences).
    Include:
    1. The definitive diagnosis (or leading hypothesis).
    2. Key interventions (e.g., "Given IV fluids", "Sutured", "CT Negative").
    3. The outcome.
    
    Do NOT use bullet points. Do NOT write a full letter. Just the medical facts.
    """
    try:
        # Make sure 'gemini-3-flash-preview:cloud' is available in your Ollama
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
    except Exception as e:
        return f"Summary unavailable. Error: {e}"
    
def generate_ai_summary(patient, logs):
    prompt = f"""
    Act as a Medical Doctor. Write a formal Hospital Discharge Summary for:
    Patient: {patient['name']} ({patient['age']} {patient['gender']})
    Chief Complaint: {patient['complaint']}
    Triage Acuity: KTAS Level {patient['triage_level']}
    Vitals: BP {patient['sbp']}/{patient['dbp']}, HR {patient['hr']}, SpO2 {patient['saturation']}%
    Notes: {logs}
    Format: Diagnosis, Hospital Course, Discharge Instructions, Follow-up.
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
    except Exception as e:
        return f"Error: {e}"

def generate_care_plan(complaint, vitals):
    prompt = f"""
    Act as an Emergency Physician. Suggest a standard initial workup/plan for:
    Complaint: {complaint} | Vitals: {vitals}
    Return ONLY a bulleted list of orders (Labs, Imaging, Meds). Brief.
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
    except Exception as e:
        return "Plan service unavailable."

# ---------------------------------------------------------
# LOAD DATA & CONTEXT
# ---------------------------------------------------------
if 'selected_patient_id' not in st.session_state:
    st.warning("⚠️ No patient selected.")
    if st.button("⬅️ Return to Dashboard"): st.switch_page("pages/1_Dashboard.py")
    st.stop()

pid = st.session_state['selected_patient_id']
patient = database.get_patient_by_id(pid)

if not patient:
    st.error("Patient record not found.")
    if st.button("⬅️ Return to Dashboard"): st.switch_page("pages/1_Dashboard.py")
    st.stop()

bed_loc = database.get_patient_bed(pid)

# NEW CODE: Uses the filtered list
md_opts = [""] + database.get_available_staff("doctor")
nppa_opts = [""] + database.get_available_staff("nppa")
nurse_opts = [""] + database.get_available_staff("nurse")

def get_index(options, value):
    try: return options.index(value)
    except: return 0

# Name Alert
all_active = database.get_all_patients()
active_names = all_active[all_active['status'] != 'Discharged']['name'].tolist()
is_duplicate = active_names.count(patient['name']) > 1

# ---------------------------------------------------------
# 1. EHR HEADER ("Story Board") - FIXED & FLATTENED
# ---------------------------------------------------------
acuity_color = {1: "#d32f2f", 2: "#f57c00", 3: "#fbc02d", 4: "#388e3c", 5: "#1976d2"}.get(patient['triage_level'], "#555")

# Ensure alert_badge is a safe string
alert_badge = f'<span style="background-color:red; color:white; padding:2px 8px; font-size:14px; border-radius:5px;">🚨 NAME ALERT</span>' if is_duplicate else ""

# Safe variables for display
p_dob = patient.get('dob', 'Unknown')
p_age = patient['age']
p_sex = patient['gender']
p_mrn = patient['id']
p_loc = bed_loc
p_status = patient['status']
p_ktas = patient['triage_level']

# CRITICAL FIX: NO INDENTATION in the HTML string below
header_html = f"""
<div style="border-left: 10px solid {acuity_color}; border-radius: 5px; padding: 15px; background-color: #f9f9f9; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 20px;">
<div style="display: flex; justify-content: space-between; align-items: flex-start;">
<div>
<div style="display: flex; align-items: center; gap: 10px;">
<h2 style="margin:0; padding:0; color: #333;">{patient['name']}</h2>
{alert_badge}
</div>
<div style="margin-top: 5px; color: #555; font-size: 16px;">
<b>DOB:</b> {p_dob} ({p_age}y) &nbsp;&bull;&nbsp; 
<b>Sex:</b> {p_sex} &nbsp;&bull;&nbsp; 
<b>MRN:</b> #{p_mrn}
</div>
</div>
<div style="text-align: right;">
<span style="background-color: {acuity_color}; color: white; padding: 5px 15px; border-radius: 15px; font-weight: bold; font-size: 14px;">
KTAS Level {p_ktas}
</span>
<div style="margin-top: 8px; font-weight: bold; color: #333; font-size: 18px;">📍 {p_loc}</div>
<div style="color: #666; font-size: 14px;">{p_status}</div>
</div>
</div>
</div>
"""

st.markdown(header_html, unsafe_allow_html=True)
st.write("")

# ---------------------------------------------------------
# 2. MAIN TABS
# ---------------------------------------------------------
t1, t2, t3, t4 = st.tabs(["📝 Clinical Assessment", "🩺 Documentation & Orders", "🤖 AI Audit Trail", "🕒 History"])

# === TAB 1: CLINICAL EDIT ===
with t1:
    with st.form("clinical_edit_form"):
        st.subheader("1. Demographics")
        c1, c2, c3, c4 = st.columns(4)
        u_name = c1.text_input("Name", value=patient['name'])
        c2.text_input("DOB", value=patient.get('dob', ''), disabled=True) 
        u_age = c3.number_input("Age", 0, 120, patient['age'])
        u_gender = c4.selectbox("Gender", ["Male", "Female"], index=0 if patient['gender'] == "Male" else 1)
        
        st.subheader("2. Triage Assessment")
        col_a, col_b, col_c, col_d = st.columns(4)
        u_complaint = col_a.text_input("Chief Complaint", value=patient['complaint'])
        curr_arr = ARRIVAL_MAP.get(patient['arrival_mode'], "Walk-in")
        u_arrival_str = col_b.selectbox("Arrival Mode", list(ARRIVAL_MAP.values()), index=list(ARRIVAL_MAP.values()).index(curr_arr))
        curr_inj = INJURY_MAP.get(patient['injury'], "No")
        u_injury_str = col_c.selectbox("Trauma / Injury?", list(INJURY_MAP.values()), index=list(INJURY_MAP.values()).index(curr_inj))
        curr_men = MENTAL_MAP.get(patient['mental'], "Alert")
        u_mental_str = col_d.selectbox("Mental Status", list(MENTAL_MAP.values()), index=list(MENTAL_MAP.values()).index(curr_men))
        
        col_e, col_f = st.columns([1, 3])
        curr_pain = PAIN_MAP.get(patient['pain'], "No")
        u_pain_str = col_e.selectbox("Pain Reported?", list(PAIN_MAP.values()), index=list(PAIN_MAP.values()).index(curr_pain))
        u_nrs = col_f.slider("NRS Pain Scale (0-10)", 0, 10, patient['nrs_pain'])
        
        st.divider()
        st.subheader("3. Vital Signs")
        v1, v2, v3, v4, v5, v6 = st.columns(6)
        u_sbp = v1.number_input("SBP", value=patient['sbp'])
        u_dbp = v2.number_input("DBP", value=patient['dbp'])
        u_hr = v3.number_input("Heart Rate", value=patient['hr'])
        u_rr = v4.number_input("Resp. Rate", value=patient['rr'])
        u_bt = v5.number_input("Temp (°C)", value=patient['bt'])
        u_sat = v6.number_input("SpO2 (%)", value=patient['saturation'])

        st.divider()
        st.subheader("4. Acuity Classification")
        u_level = st.selectbox("KTAS Level", [1, 2, 3, 4, 5], index=patient['triage_level']-1)
        
        if st.form_submit_button("💾 Save Clinical Updates", type="primary", use_container_width=True):
            db_arrival = REV_ARRIVAL[u_arrival_str]
            db_injury = REV_INJURY[u_injury_str]
            db_mental = REV_MENTAL[u_mental_str]
            db_pain = REV_PAIN[u_pain_str]
            
            database.update_full_patient_record(
                pid, u_name, u_age, u_gender, u_complaint,
                db_arrival, db_injury, db_mental, db_pain, u_nrs,
                u_sbp, u_dbp, u_hr, u_rr, u_bt, u_sat,
                u_level, patient['assigned_md'], patient['assigned_nppa'], patient['assigned_nurse'], patient['nurse_notes']
            )
            st.success("✅ Patient record updated successfully!")
            time.sleep(1)
            st.rerun()

# === TAB 2: DOCUMENTATION (REDESIGNED LAYOUT) ===
with t2:
    col_editor, col_history = st.columns([1.8, 1]) # Wider Editor

    # --- LEFT: NOTE WRITER (Bordered Window) ---
    with col_editor:
        with st.container(border=True):
            st.markdown("#### ✍️ Provider Documentation")
            
            # Row 1: Config & AI
            c_top1, c_top2 = st.columns([2, 1], vertical_alignment="bottom")
            with c_top1:
                n_type = st.selectbox("Note Type", ["Progress Note", "Nursing Note", "Procedure Note", "Discharge Summary"], key="note_type_input")
            
            with c_top2:
                # ---------------------------------------------------------
                # NEW: LOGIC TO HANDLE BOTH SUMMARY TYPES
                # ---------------------------------------------------------
                if n_type == "Discharge Summary":
                    # Option A: Full Document (For the Text Area / PDF)
                    if st.button("✨ Write Full Letter", help="Generates long-form Discharge Letter"):
                        with st.spinner("Writing Letter..."):
                            logs = patient['nurse_notes'] if patient['nurse_notes'] else ""
                            summary = generate_ai_summary(patient, logs) # Your OLD function (Long)
                            st.session_state.current_note = summary
                            st.rerun()
                            
                    # Option B: Database Abstract (For the History Column)
                    if st.button("📌 Update History Abstract", help="Generates short paragraph for History Tab"):
                        with st.spinner("Summarizing for DB..."):
                            logs = patient['nurse_notes'] if patient['nurse_notes'] else ""
                            # 1. Generate the Short Script
                            short_script = generate_illness_script(patient, logs) # Your NEW function (Short)
                            
                            # 2. Save DIRECTLY to database (don't put in text area)
                            database.update_full_patient_record(
                                pid, patient['name'], patient['age'], patient['gender'], patient['complaint'],
                                patient['arrival_mode'], patient['injury'], patient['mental'], patient['pain'], patient['nrs_pain'],
                                patient['sbp'], patient['dbp'], patient['hr'], patient['rr'], patient['bt'], patient['saturation'],
                                patient['triage_level'], patient['assigned_md'], patient['assigned_nppa'], patient['assigned_nurse'], 
                                patient['nurse_notes'], # Keep notes same
                                short_script # <--- SAVE TO clinical_summary COLUMN
                            )
                            st.toast("✅ History Abstract Updated!", icon="📌")
                            
                elif n_type == "Progress Note":
                    if st.button("💡 Care Plan", help="Suggest orders"):
                        vits = f"BP {patient['sbp']}/{patient['dbp']}, HR {patient['hr']}"
                        plan = generate_care_plan(patient['complaint'], vits)
                        st.session_state.current_note = st.session_state.get('current_note', '') + "\n" + plan
                        st.rerun()

            # Row 2: Macros (Toolbar)
            st.markdown("**Quick Actions:**")
            c_m1, c_m2, c_m3, c_m4 = st.columns(4)
            
            def append_macro(text):
                st.session_state.current_note = st.session_state.get('current_note', '') + text + "\n"
            
            if c_m1.button("🩺 Exam", use_container_width=True): 
                append_macro("Physical Exam: Alert & Oriented. Lungs clear. Heart RRR. Abd soft.")
            if c_m2.button("📊 Vitals", use_container_width=True): 
                append_macro(f"Vitals: BP {patient['sbp']}/{patient['dbp']}, HR {patient['hr']}, SpO2 {patient['saturation']}%")
            if c_m3.button("🧪 Sepsis -", use_container_width=True): 
                append_macro("Sepsis Screen Negative. No acute distress.")
            if c_m4.button("🧹 Clear", use_container_width=True): 
                st.session_state.current_note = ""
                st.rerun()

            # Row 3: Editor
            if 'current_note' not in st.session_state: st.session_state.current_note = ""
            
            st.text_area(
                "Note Content", 
                height=350, 
                key="current_note",
                label_visibility="collapsed",
                placeholder="Type clinical notes here..."
            )

            # Callback for Save
            def save_note_callback():
                content = st.session_state.current_note
                n_type = st.session_state.note_type_input
                if content:
                    timestamp = time.strftime("%Y-%m-%d %H:%M")
                    user = st.session_state.get('username', 'Staff')
                    role = st.session_state.get('user_role', '').title()
                    formatted = f"\n\n{'='*40}\n[{timestamp}] {n_type.upper()} by {user} ({role})\n{'='*40}\n{content}"
                    
                    updated = (patient['nurse_notes'] or "") + formatted
                    database.update_full_patient_record(
                        pid, patient['name'], patient['age'], patient['gender'], patient['complaint'],
                        patient['arrival_mode'], patient['injury'], patient['mental'], patient['pain'], patient['nrs_pain'],
                        patient['sbp'], patient['dbp'], patient['hr'], patient['rr'], patient['bt'], patient['saturation'],
                        patient['triage_level'], patient['assigned_md'], patient['assigned_nppa'], patient['assigned_nurse'], 
                        updated
                    )
                    st.toast("✅ Note Signed & Saved.")
                    st.session_state.current_note = ""

            # Row 4: Footer
            st.button("✅ Sign & Save Note", type="primary", use_container_width=True, on_click=save_note_callback)

    # --- RIGHT: HISTORY & TEAM ---
    with col_history:
        st.subheader("🕒 Timeline")
        raw_notes = patient['nurse_notes'] if patient['nurse_notes'] else ""
        if not raw_notes:
            st.info("No notes yet.")
        else:
            with st.container(height=450, border=True):
                st.text(raw_notes)
        
        st.write("---")
        with st.expander("👨‍⚕️ Update Team", expanded=False):
            with st.form("team_form_2"):
                # LOGIC FIX: Ensure the CURRENTLY assigned staff are in the list,
                # otherwise they disappear because they are technically "Busy".
                
                # 1. Prepare MD List
                current_md = patient['assigned_md']
                # Create a copy of available options so we don't mess up the global list
                active_md_opts = md_opts.copy() 
                if current_md and current_md not in active_md_opts:
                    active_md_opts.append(current_md)
                
                # 2. Prepare NPPA List
                current_nppa = patient['assigned_nppa']
                active_nppa_opts = nppa_opts.copy()
                if current_nppa and current_nppa not in active_nppa_opts:
                    active_nppa_opts.append(current_nppa)

                # 3. Prepare Nurse List
                current_nurse = patient['assigned_nurse']
                active_nurse_opts = nurse_opts.copy()
                if current_nurse and current_nurse not in active_nurse_opts:
                    active_nurse_opts.append(current_nurse)

                # 4. Render Dropdowns (Fixed variable names)
                u_md = st.selectbox("MD", active_md_opts, index=get_index(active_md_opts, current_md))
                u_nppa = st.selectbox("APP", active_nppa_opts, index=get_index(active_nppa_opts, current_nppa))
                u_nurse = st.selectbox("RN", active_nurse_opts, index=get_index(active_nurse_opts, current_nurse))
                
                if st.form_submit_button("Save Team"):
                    # Assuming you have a function to update just the team, 
                    # otherwise use update_full_patient_record logic
                    database.update_full_patient_record(
                        pid, patient['name'], patient['age'], patient['gender'], patient['complaint'],
                        patient['arrival_mode'], patient['injury'], patient['mental'], patient['pain'], patient['nrs_pain'],
                        patient['sbp'], patient['dbp'], patient['hr'], patient['rr'], patient['bt'], patient['saturation'],
                        patient['triage_level'], 
                        u_md, u_nppa, u_nurse, # <--- NEW VALUES
                        patient['nurse_notes']
                    )
                    st.success("Updated")
                    time.sleep(1)
                    st.rerun()

# === TAB 3: AI AUDIT TRAIL ===
with t3:
    st.markdown("### 🤖 Clinical Decision Support Audit")
    st.info("This section preserves the AI analysis generated at the moment of triage.")
    
    ai_lvl = patient['ai_level']
    final_lvl = patient['triage_level']
    is_match = (ai_lvl == final_lvl)
    
    c_audit_1, c_audit_2 = st.columns([1, 2])
    with c_audit_1:
        st.markdown("#### Decision Analysis")
        if is_match:
            st.success("✅ **AI ACCEPTED**")
            st.write("Clinical staff agreed with the model.")
        else:
            st.error("⚠️ **CLINICAL OVERRIDE**")
            st.write(f"Staff overruled the AI.\n- AI Rec: **Level {ai_lvl}**\n- Final: **Level {final_lvl}**")
            
        st.divider()
        st.metric("Model Confidence", f"{patient['confidence']:.1f}%")
        st.write(f"**Triage Nurse:** {patient['triage_nurse']}")
        
    with c_audit_2:
        st.markdown("#### 🧠 Model Reasoning Snapshot")
        explanation_text = patient['ai_explanation'] if patient['ai_explanation'] else "No explanation data available."
        st.text_area("Clinical Justification (Read-Only)", value=explanation_text, height=300, disabled=True)

# === TAB 4: HISTORY (TIMELINE VIEW) ===
# === TAB 4: HISTORY (TIMELINE VIEW) ===
with t4:
    st.markdown(f"### 🗂️ Medical Timeline: {patient['name']}")
    
    # 1. Fetch History
    # Note: We fetch ALL records for this person
    history = database.get_patient_history(patient['name'], patient.get('dob'))
    
    if not history.empty:
        st.caption(f"Total encounters found: {len(history)}")
        
        # 2. Iterate through ALL visits (including the current one)
        for index, row in history.iterrows():
            
            # Check if this row is the one we are currently looking at
            is_current = (row['id'] == int(pid))
            
            # Border style: Blue highlight if current, Gray if past
            b_style = "border: 2px solid #2196f3;" if is_current else "border: 1px solid #ddd;"
            bg_style = "background-color: #f8fbff;" if is_current else ""
            
            # Custom Container using HTML/CSS for distinction
            with st.container():
                st.markdown(f"<div style='{b_style} {bg_style} border-radius: 10px; padding: 15px; margin-bottom: 15px;'>", unsafe_allow_html=True)
                
                # A. HEADER ROW
                c_date, c_complaint, c_score, c_btn = st.columns([1.5, 3, 1, 1.5], vertical_alignment="center")
                
                try:
                    visit_date = pd.to_datetime(row['arrival_time']).strftime("%b %d, %Y")
                    visit_time = pd.to_datetime(row['arrival_time']).strftime("%H:%M")
                except:
                    visit_date = str(row['arrival_time'])
                    visit_time = ""

                with c_date:
                    if is_current:
                        st.markdown(f"**📍 {visit_date}** (Current)")
                    else:
                        st.write(f"**{visit_date}**")
                    st.caption(visit_time)
                
                with c_complaint:
                    st.write(f"🏥 **{row['complaint']}**")
                    st.caption(f"Outcome: {row['final_disposition']}")
                
                with c_score:
                    lvl = row['triage_level']
                    color = "#d32f2f" if lvl <= 2 else "#fbc02d" if lvl == 3 else "#388e3c"
                    st.markdown(f"<span style='color:{color}; font-weight:bold; border:1px solid {color}; padding:2px 6px; border-radius:4px;'>KTAS {lvl}</span>", unsafe_allow_html=True)
                
                with c_btn:
                    if is_current:
                        st.button("👁️ Viewing", key=f"curr_{row['id']}", disabled=True, use_container_width=True)
                    else:
                        if st.button("📂 Open", key=f"open_{row['id']}", use_container_width=True):
                            st.session_state['selected_patient_id'] = int(row['id'])
                            st.rerun()
                
                # B. THE SYNOPSIS (The AI Generated Part)
                summary_text = row.get('clinical_summary')
                
                # Logic to determine box color
                if pd.isna(summary_text) or summary_text == "":
                    summary_text = "No clinical summary recorded."
                    note_color = "#f0f2f6" # Gray
                else:
                    note_color = "#e3f2fd" # Blue (Shows data exists)

                st.markdown(
                    f"""
                    <div style="background-color: {note_color}; padding: 10px; border-radius: 5px; border-left: 5px solid #2196f3; font-size: 14px; color: #333; margin-top: 10px;">
                        <i><b>Clinical Synopsis:</b></i> {summary_text}
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
                st.markdown("</div>", unsafe_allow_html=True) # Close custom container

    else:
        st.warning("No records found in database.")

# ---------------------------------------------------------
# FOOTER ACTIONS (Updated)
# ---------------------------------------------------------
st.markdown("---")
# Change columns from 3 to 4 to fit the new button
ac1, ac2, ac3, ac4 = st.columns([1, 1, 1, 1])

with ac1:
    if st.button("⬅️ Dashboard", use_container_width=True):
        st.switch_page("pages/1_Dashboard.py")

with ac2:
    # PDF Logic (Keep existing)
    pdf_bytes = create_pdf(patient, bed_loc)
    b64 = base64.b64encode(pdf_bytes).decode('latin-1')
    href = f'<a href="data:application/octet-stream;base64,{b64}" download="Medical_Record_{pid}.pdf" style="text-decoration:none; width:100%; display:inline-block; text-align:center; background-color:#555; color:white; padding:10px; border-radius:5px;">📄 Download PDF</a>'
    st.markdown(href, unsafe_allow_html=True)

with ac3:
    # NEW TRANSFER BUTTON
    if st.button("⇄ Transfer", use_container_width=True, help="Change Bed Location"):
        show_transfer_dialog_ehr(pid, bed_loc)

with ac4:
    # Discharge Logic (Keep existing)
    if patient['status'] != "Discharged":
        if st.button("✅ Discharge", type="primary", use_container_width=True):
            database.discharge_patient_and_free_bed(pid)
            st.success("Discharged.")
            time.sleep(1)
            st.switch_page("pages/1_Dashboard.py")
    else:
        st.info("Discharged")