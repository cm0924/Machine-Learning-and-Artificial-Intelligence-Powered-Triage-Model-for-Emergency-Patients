# pages/4_Patient_Details.py
import streamlit as st
import database
import pandas as pd
import time
from fpdf import FPDF
import base64

if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

st.set_page_config(page_title="Patient Details", layout="wide", page_icon="🗂️")

# ---------------------------------------------------------
# PDF GENERATOR FUNCTION
# ---------------------------------------------------------
def create_pdf(patient):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Emergency Department - Clinical Report", ln=1, align='C')
    pdf.ln(10)
    
    # Patient Info
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Patient Name: {patient['name']}", ln=1)
    pdf.cell(200, 10, txt=f"ID: {patient['id']}   |   Age/Sex: {patient['age']} / {patient['gender']}", ln=1)
    pdf.cell(200, 10, txt=f"Arrival Time: {patient['arrival_time']}", ln=1)
    pdf.line(10, 50, 200, 50)
    pdf.ln(10)
    
    # Clinical Info
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt=f"Final Triage Level: KTAS {patient['triage_level']}", ln=1)
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, txt=f"Chief Complaint: {patient['complaint']}")
    pdf.ln(5)
    
    # Vitals
    pdf.cell(200, 10, txt="Vital Signs:", ln=1)
    pdf.cell(50, 10, txt=f"BP: {patient['sbp']}/{patient['dbp']}", border=1)
    pdf.cell(50, 10, txt=f"HR: {patient['hr']}", border=1)
    pdf.cell(50, 10, txt=f"RR: {patient['rr']}", border=1)
    pdf.cell(40, 10, txt=f"SpO2: {patient['saturation']}%", border=1, ln=1)
    
    # Staff & Notes
    pdf.ln(10)
    pdf.cell(200, 10, txt=f"Attending MD: {patient['assigned_md']}", ln=1)
    pdf.ln(5)
    pdf.multi_cell(0, 10, txt=f"Clinical Notes:\n{patient['nurse_notes']}")
    
    return pdf.output(dest='S').encode('latin-1')

# ---------------------------------------------------------
# 1. LOAD PATIENT (CURRENT VISIT)
# ---------------------------------------------------------
if 'selected_patient_id' not in st.session_state:
    st.warning("⚠️ No patient selected.")
    if st.button("⬅️ Back"): st.switch_page("pages/1_Dashboard.py")
    st.stop()

current_id = st.session_state['selected_patient_id']
patient = database.get_patient_by_id(current_id)

if not patient:
    st.error("Record not found.")
    st.stop()

# 2. LOAD PATIENT HISTORY
history_df = database.get_patient_history(patient['name'])

# Staff Lists
md_list = [""] + database.get_staff_by_role("ED MD")
nppa_list = [""] + database.get_staff_by_role("ED NP/PA")
nurse_list = [""] + database.get_staff_by_role("Nurse")

def get_index(options, value):
    try: return options.index(value)
    except: return 0

# ---------------------------------------------------------
# HEADER (Dynamic Banner)
# ---------------------------------------------------------
color_map = {1: "#ff4b4b", 2: "#ffa500", 3: "#fca311", 4: "#28a745", 5: "#007bff"}
level = patient['triage_level']
color = color_map.get(level, "gray")

st.markdown(f"""
<div style="background-color: {color}; padding: 20px; border-radius: 10px; color: white; display: flex; justify-content: space-between; align-items: center;">
    <div>
        <h1 style="margin:0;">{patient['name']} (Edit Mode)</h1>
        <h3 style="margin:0;">{patient['age']} yo {patient['gender']}</h3>
    </div>
    <div style="text-align: right;">
        <h2 style="margin:0;">Level {level}</h2>
        <p style="margin:0;">ID: #{patient['id']}</p>
    </div>
</div>
""", unsafe_allow_html=True)
st.write("")

# ---------------------------------------------------------
# TABS LAYOUT
# ---------------------------------------------------------
tab1, tab2 = st.tabs(["📝 Current Visit Details", "🕒 Medical History Timeline"])

# =========================================================
# TAB 1: FULLY EDITABLE FORM
# =========================================================
with tab1:
    with st.form("full_edit_form"):
        # ROW 1: DEMOGRAPHICS
        st.subheader("📝 Demographics & Intake")
        r1c1, r1c2, r1c3 = st.columns([1, 1, 2])
        new_name = r1c1.text_input("Name", value=patient['name'])
        new_age = r1c2.number_input("Age", 0, 120, patient['age'])
        new_gender = r1c2.selectbox("Gender", ["Male", "Female"], index=0 if patient['gender'] == "Male" else 1)
        new_complaint = r1c3.text_input("Chief Complaint", value=patient['complaint'])

        st.divider()

        # ROW 2: VITALS
        st.subheader("🩺 Clinical Vitals")
        v1, v2, v3, v4, v5, v6 = st.columns(6)
        new_sbp = v1.number_input("SBP", 0, 300, patient['sbp'])
        new_dbp = v2.number_input("DBP", 0, 200, patient['dbp'])
        new_hr = v3.number_input("Pulse", 0, 300, patient['hr'])
        new_rr = v4.number_input("Resp", 0, 100, patient['rr'])
        new_bt = v5.number_input("Temp", 30.0, 45.0, patient['bt'])
        new_sat = v6.number_input("SpO2", 0, 100, patient['saturation'])

        st.divider()

        # ROW 3: TRIAGE & STAFF
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("🤖 AI Analysis")
            st.caption(f"Original Prediction: Level {patient['ai_level']} ({patient['confidence']:.1f}%)")
            if patient['ai_explanation']: 
                st.info(patient['ai_explanation'])
            else: 
                st.warning("No AI explanation recorded.")

        with col2:
            st.subheader("🏥 Staff & Decision")
            new_level = st.selectbox("Triage Level", [1, 2, 3, 4, 5], index=patient['triage_level']-1)
            new_md = st.selectbox("Assigned MD", options=md_list, index=get_index(md_list, patient['assigned_md']))
            new_nppa = st.selectbox("NP / PA", options=nppa_list, index=get_index(nppa_list, patient['assigned_nppa']))
            new_nurse = st.selectbox("Nurse", options=nurse_list, index=get_index(nurse_list, patient['assigned_nurse']))
            new_notes = st.text_area("Clinical Notes", value=patient['nurse_notes'] if patient['nurse_notes'] else "")

        st.write("##")
        if st.form_submit_button("💾 Save All Changes", type="primary", use_container_width=True):
            database.update_full_patient_record(
                current_id, new_name, new_age, new_gender, new_complaint,
                new_sbp, new_dbp, new_hr, new_rr, new_bt, new_sat,
                new_level, new_md, new_nppa, new_nurse, new_notes
            )
            st.success("✅ Patient record updated successfully!")
            time.sleep(1)
            st.rerun()

# =========================================================
# TAB 2: HISTORY TIMELINE
# =========================================================
with tab2:
    st.subheader(f"Medical History for: {patient['name']}")
    other_visits = history_df[history_df['id'] != current_id]
    
    if not other_visits.empty:
        for index, visit in other_visits.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 3, 2, 2])
                c1.markdown(f"**Date:**\n{visit['arrival_time']}")
                c2.markdown(f"**Complaint:**\n{visit['complaint']}")
                lvl_color = {1: "red", 2: "orange", 3: "#fca311", 4: "green", 5: "blue"}.get(visit['triage_level'], "grey")
                c3.markdown(f"**Level:** <span style='color:{lvl_color}; font-size:20px; font-weight:bold'>{visit['triage_level']}</span>", unsafe_allow_html=True)
                if c4.button("📂 View Record", key=f"hist_{visit['id']}"):
                    st.session_state['selected_patient_id'] = int(visit['id'])
                    st.rerun()
    else:
        st.info("No previous medical history found.")

# ---------------------------------------------------------
# FOOTER ACTIONS
# ---------------------------------------------------------
st.markdown("---")
c1, c2, c3 = st.columns([1, 2, 1])

with c1:
    if st.button("⬅️ Back to Dashboard"): st.switch_page("pages/1_Dashboard.py")

with c2:
    # PDF Button
    pdf_data = create_pdf(patient)
    b64 = base64.b64encode(pdf_data).decode('latin-1')
    href = f'<div style="text-align:center"><a href="data:application/octet-stream;base64,{b64}" download="Report_{patient["name"]}.pdf" style="text-decoration:none; background-color:#4CAF50; color:white; padding:10px 20px; border-radius:5px;">📄 Download PDF Report</a></div>'
    st.markdown(href, unsafe_allow_html=True)

with c3:
    if st.button("🗑️ Discharge / Archive"):
        database.discharge_patient(current_id)
        st.toast("Discharged.")
        time.sleep(1)
        st.switch_page("pages/1_Dashboard.py")