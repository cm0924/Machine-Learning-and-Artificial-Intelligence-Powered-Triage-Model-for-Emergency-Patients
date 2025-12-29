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

# ---------------------------------------------------------
# AI HELPERS
# ---------------------------------------------------------
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
            # Using vertical_alignment="bottom" ensures button lines up with dropdown
            c_top1, c_top2 = st.columns([2, 1], vertical_alignment="bottom")
            with c_top1:
                n_type = st.selectbox("Note Type", ["Progress Note", "Nursing Note", "Procedure Note", "Discharge Summary"], key="note_type_input")
            
            with c_top2:
                # Dynamic AI Button
                if n_type == "Discharge Summary":
                    if st.button("✨ Auto-Summarize", help="Generate full summary from chart"):
                        with st.spinner("AI Generating..."):
                            logs = patient['nurse_notes'] if patient['nurse_notes'] else ""
                            summary = generate_ai_summary(patient, logs)
                            st.session_state.current_note = summary
                            st.rerun() # Refresh to show text
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
                u_md = st.selectbox("MD", md_list, index=get_index(md_list, patient['assigned_md']))
                u_nppa = st.selectbox("APP", nppa_list, index=get_index(nppa_list, patient['assigned_nppa']))
                u_nurse = st.selectbox("RN", nurse_list, index=get_index(nurse_list, patient['assigned_nurse']))
                if st.form_submit_button("Save Team"):
                    database.assign_staff(pid, u_md, u_nppa, u_nurse)
                    st.success("Updated")
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

# === TAB 4: HISTORY ===
with t4:
    st.markdown(f"### Medical History: {patient['name']}")
    st.caption(f"Searching for records matching Name + DOB ({patient.get('dob', 'Unknown')})")
    history = database.get_patient_history(patient['name'], patient.get('dob'))
    
    if not history.empty:
        past_visits = history[history['id'] != pid]
        if not past_visits.empty:
            st.dataframe(past_visits, column_config={"arrival_time": "Date", "complaint": "Chief Complaint", "triage_level": "KTAS", "final_disposition": "Outcome"}, use_container_width=True)
        else:
            st.info("No prior visits found.")
    else:
        st.warning("No records found.")

# ---------------------------------------------------------
# FOOTER ACTIONS
# ---------------------------------------------------------
st.markdown("---")
ac1, ac2, ac3 = st.columns([1, 1, 1])

with ac1:
    if st.button("⬅️ Back to Dashboard", use_container_width=True):
        st.switch_page("pages/1_Dashboard.py")

with ac2:
    pdf_bytes = create_pdf(patient, bed_loc)
    b64 = base64.b64encode(pdf_bytes).decode('latin-1')
    href = f'<a href="data:application/octet-stream;base64,{b64}" download="Medical_Record_{pid}.pdf" style="text-decoration:none; width:100%; display:inline-block; text-align:center; background-color:#555; color:white; padding:10px; border-radius:5px;">📄 Download PDF Chart</a>'
    st.markdown(href, unsafe_allow_html=True)

with ac3:
    if patient['status'] != "Discharged":
        if st.button("✅ Discharge Patient", type="primary", use_container_width=True):
            try: database.discharge_patient_and_free_bed(pid)
            except: database.discharge_patient(pid)
            st.success("Patient Discharged.")
            time.sleep(1)
            st.switch_page("pages/1_Dashboard.py")
    else:
        st.info("Patient already discharged.")