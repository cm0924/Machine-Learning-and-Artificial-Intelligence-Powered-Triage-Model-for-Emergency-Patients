# pages/4_Patient_Details.py
import streamlit as st
import database
import pandas as pd
import time
from fpdf import FPDF
import base64

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
# PDF GENERATOR
# ---------------------------------------------------------
def create_pdf(patient, bed_label):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Hospital Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="General Hospital - Clinical Encounter", ln=1, align='C')
    pdf.ln(5)
    
    # Patient Demographics Box
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 8, txt=f"Patient: {patient['name']} (ID: {patient['id']})", ln=1)
    pdf.cell(200, 8, txt=f"Age/Sex: {patient['age']} / {patient['gender']}", ln=1)
    pdf.cell(200, 8, txt=f"Location: {bed_label} | Status: {patient['status']}", ln=1)
    pdf.cell(200, 8, txt=f"Arrival: {patient['arrival_time']}", ln=1)
    pdf.line(10, 55, 200, 55)
    pdf.ln(10)
    
    # Clinical Data
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Clinical Assessment", ln=1)
    pdf.set_font("Arial", size=11)
    pdf.multi_cell(0, 8, txt=f"Chief Complaint: {patient['complaint']}")
    pdf.cell(200, 8, txt=f"Triage Level: KTAS {patient['triage_level']}", ln=1)
    pdf.ln(5)
    
    # Vitals
    pdf.cell(200, 10, txt=f"Vitals: BP {patient['sbp']}/{patient['dbp']} | HR {patient['hr']} | RR {patient['rr']} | SpO2 {patient['saturation']}% | T {patient['bt']}C", ln=1)
    pdf.ln(5)

    # Documentation
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Provider Documentation", ln=1)
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 6, txt=f"Attending: {patient['assigned_md']}\n\nClinical Log:\n{patient['nurse_notes']}")
    
    return pdf.output(dest='S').encode('latin-1')

# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------
if 'selected_patient_id' not in st.session_state:
    st.warning("⚠️ No patient selected.")
    if st.button("⬅️ Return to Dashboard"): st.switch_page("pages/1_Dashboard.py")
    st.stop()

pid = st.session_state['selected_patient_id']
patient = database.get_patient_by_id(pid)

if not patient:
    st.error("Patient record not found.")
    st.stop()

# Get Bed Location
bed_loc = database.get_patient_bed(pid)

# Staff Lists for Dropdowns
md_list = [""] + database.get_staff_by_role("doctor")
nppa_list = [""] + database.get_staff_by_role("nppa")
nurse_list = [""] + database.get_staff_by_role("nurse")

def get_index(options, value):
    try: return options.index(value)
    except: return 0

# ---------------------------------------------------------
# 1. EHR HEADER (The "Story Board")
# ---------------------------------------------------------
# Color coding based on Acuity (Triage Level)
acuity_color = {1: "#d32f2f", 2: "#f57c00", 3: "#fbc02d", 4: "#388e3c", 5: "#1976d2"}.get(patient['triage_level'], "#555")

# Status Badge Color
status_color = "red" if patient['status'] == "Waiting" else "blue" if patient['status'] == "In-Treatment" else "green"

st.markdown(f"""
<div style="border: 2px solid {acuity_color}; border-radius: 10px; padding: 15px; background-color: #f9f9f9; margin-bottom: 20px;">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <span style="font-size: 24px; font-weight: bold; color: #333;">{patient['name']}</span>
            <span style="font-size: 18px; color: #666; margin-left: 10px;">{patient['age']} {patient['gender']}</span>
        </div>
        <div style="text-align: right;">
            <span style="background-color: {acuity_color}; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold;">KTAS {patient['triage_level']}</span>
            <span style="background-color: {status_color}; color: white; padding: 5px 10px; border-radius: 5px; font-weight: bold; margin-left: 5px;">{patient['status'].upper()}</span>
        </div>
    </div>
    <hr style="margin: 10px 0;">
    <div style="display: flex; gap: 30px; font-size: 14px; color: #444;">
        <div><strong>🆔 MRN:</strong> #{patient['id']}</div>
        <div><strong>📍 Location:</strong> {bed_loc}</div>
        <div><strong>🚑 Arrival:</strong> {patient['arrival_time']}</div>
        <div><strong>🤒 Complaint:</strong> {patient['complaint']}</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. MAIN CHART CONTENT (Tabs)
# ---------------------------------------------------------
t1, t2, t3 = st.tabs(["🩺 Documentation & Orders", "📊 Vitals & Demographics", "🕒 History"])

# === TAB 1: DOCUMENTATION (Where the "Work" happens) ===
with t1:
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.subheader("📝 Clinical Log")
        st.info("💡 **Note:** Timestamps for treatment start are recorded below in the log.")
        
        # We display the current notes as a Read-Only "Log" first
        if patient['nurse_notes']:
            st.text_area("Existing Logs (Read Only)", value=patient['nurse_notes'], height=150, disabled=True)
        else:
            st.caption("No notes recorded yet.")
            
        # New Entry Area
        new_note_entry = st.text_area("➕ Add New Progress Note", height=100, placeholder="Type update here...")
        
        if st.button("Append Note"):
            if new_note_entry:
                timestamp = time.strftime("%H:%M")
                updated_notes = (patient['nurse_notes'] or "") + f"\n[{timestamp}] {new_note_entry}"
                database.update_full_patient_record(
                    pid, patient['name'], patient['age'], patient['gender'], patient['complaint'],
                    patient['sbp'], patient['dbp'], patient['hr'], patient['rr'], patient['bt'], patient['saturation'],
                    patient['triage_level'], patient['assigned_md'], patient['assigned_nppa'], patient['assigned_nurse'], 
                    updated_notes
                )
                st.success("Note added.")
                st.rerun()

    with c2:
        st.subheader("👨‍⚕️ Care Team")
        with st.form("team_form"):
            u_md = st.selectbox("Attending MD", md_list, index=get_index(md_list, patient['assigned_md']))
            u_nppa = st.selectbox("Mid-Level", nppa_list, index=get_index(nppa_list, patient['assigned_nppa']))
            u_nurse = st.selectbox("Primary Nurse", nurse_list, index=get_index(nurse_list, patient['assigned_nurse']))
            
            if st.form_submit_button("Update Team"):
                database.assign_staff(pid, u_md, u_nppa, u_nurse)
                st.success("Team Updated")
                st.rerun()

# === TAB 2: VITALS & EDIT (The Form) ===
with t2:
    with st.form("vitals_form"):
        st.subheader("Edit Clinical Data")
        col_a, col_b = st.columns(2)
        with col_a:
            u_sbp = st.number_input("SBP", value=patient['sbp'])
            u_dbp = st.number_input("DBP", value=patient['dbp'])
            u_hr = st.number_input("Heart Rate", value=patient['hr'])
        with col_b:
            u_rr = st.number_input("Resp. Rate", value=patient['rr'])
            u_sat = st.number_input("SpO2 (%)", value=patient['saturation'])
            u_bt = st.number_input("Temp (°C)", value=patient['bt'])
            
        if st.form_submit_button("Update Vitals"):
            # Preserves existing notes, just updates vitals
            database.update_full_patient_record(
                pid, patient['name'], patient['age'], patient['gender'], patient['complaint'],
                u_sbp, u_dbp, u_hr, u_rr, u_bt, u_sat,
                patient['triage_level'], patient['assigned_md'], patient['assigned_nppa'], patient['assigned_nurse'], 
                patient['nurse_notes']
            )
            st.success("Vitals Updated")
            st.rerun()

# === TAB 3: HISTORY ===
with t3:
    history = database.get_patient_history(patient['name'])
    st.dataframe(history[['arrival_time', 'complaint', 'triage_level', 'final_disposition']], use_container_width=True)

# ---------------------------------------------------------
# BOTTOM ACTION BAR
# ---------------------------------------------------------
st.markdown("---")
ac1, ac2, ac3 = st.columns([1, 1, 1])

with ac1:
    if st.button("⬅️ Back to Dashboard", use_container_width=True):
        st.switch_page("pages/1_Dashboard.py")

with ac2:
    # PDF Logic
    pdf_bytes = create_pdf(patient, bed_loc)
    b64 = base64.b64encode(pdf_bytes).decode('latin-1')
    href = f'<a href="data:application/octet-stream;base64,{b64}" download="Record_{pid}.pdf" style="text-decoration:none; width:100%; display:inline-block; text-align:center; background-color:#555; color:white; padding:10px; border-radius:5px;">📄 Download PDF Report</a>'
    st.markdown(href, unsafe_allow_html=True)

with ac3:
    if patient['status'] != "Discharged":
        if st.button("✅ Discharge Patient", type="primary", use_container_width=True):
            # We assume database.discharge_patient_and_free_bed exists from previous steps
            # If not, use standard discharge
            try:
                database.discharge_patient_and_free_bed(pid)
            except:
                database.discharge_patient(pid)
            st.success("Patient Discharged.")
            time.sleep(1)
            st.switch_page("pages/1_Dashboard.py")
    else:
        st.info("Patient already discharged.")