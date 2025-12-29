import streamlit as st
import pandas as pd
import numpy as np
import joblib
import ollama
import time
import database
import speech_recognition as sr
import difflib
import json
import re
from datetime import date, datetime

# ---------------------------------------------------------
# SECURITY CHECK
# ---------------------------------------------------------
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

current_nurse = st.session_state.get('username', 'Unknown')

# ---------------------------------------------------------
# 1. SETUP & CONFIGURATION
# ---------------------------------------------------------
st.set_page_config(page_title="Triage Assessment", page_icon="🩺", layout="wide")

# CLEAN CATEGORIES (Matches Training Data)
CLEAN_COMPLAINTS = [
    'Abdominal Pain', 'Altered Mental Status', 'Back Pain', 'Bleeding (General)', 
    'Chest Pain', 'Diarrhea/GI Issue', 'Dizziness', 'Eye Problem', 'Fever', 
    'Headache', 'Musculoskeletal Pain', 'Nausea/Vomiting', 'Neurological Deficit', 
    'Other', 'Palpitation', 'Psychiatric', 'Respiratory/Dyspnea', 'Seizure', 
    'Skin/Allergy', 'Syncope', 'Trauma/Injury', 'Urinary Issue'
]

# CLINICAL MAPPINGS (UI Text -> Model/DB Integer)
ARRIVAL_MAP = {"Ambulance": 1, "Walk-in": 2, "Transfer": 3}
INJURY_MAP = {"No": 1, "Yes": 2}
MENTAL_MAP = {"Alert": 1, "Verbal": 2, "Pain": 3, "Unresponsive": 4}
PAIN_MAP = {"No": 0, "Yes": 1}

# --- LOAD AI MODEL ---
@st.cache_resource
def load_system():
    try:
        package = joblib.load('ktas_deployment_pipeline.pkl') 
        return package
    except FileNotFoundError:
        st.error("System Error: 'ktas_deployment_pipeline.pkl' not found.")
        return None

system_package = load_system()
if system_package:
    model = system_package['model']
    model_features = system_package['features']
else:
    st.stop()

# --- SESSION STATE INITIALIZATION ---
if 'form_name' not in st.session_state: st.session_state.form_name = ""
if 'form_dob' not in st.session_state: st.session_state.form_dob = date(1990, 1, 1)
if 'form_gender_idx' not in st.session_state: st.session_state.form_gender_idx = 0
if 'form_complaint_idx' not in st.session_state: st.session_state.form_complaint_idx = 4 
if 'triage_result' not in st.session_state: st.session_state.triage_result = None

def reset_form():
    st.session_state.triage_result = None
    st.session_state.form_name = ""
    st.rerun()

def calculate_age(born):
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

# ---------------------------------------------------------
# 2. AI SPEECH FUNCTIONS
# ---------------------------------------------------------
def recognize_speech():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        st.toast("🎤 Listening... (Describe patient & vitals)")
        try:
            audio = r.listen(source, timeout=5)
            text = r.recognize_google(audio)
            return text
        except Exception as e:
            st.error(f"Voice Error: {e}")
            return None

def extract_data_from_voice(text):
    prompt = f"""
    Extract clinical entities from: "{text}"
    Return ONLY raw JSON with keys:
    - "name": (string)
    - "age": (int)
    - "gender": ("Male"/"Female")
    - "symptom": (string, pick closest match from: {CLEAN_COMPLAINTS}) 
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        content = response['message']['content']
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception as e:
        print(f"LLM Error: {e}")
    return None

def get_ai_explanation(context, triage_level, confidence):
    prompt = f"""
    Act as a senior triage nurse. Review this AI prediction.
    Patient: {context['Age']}yo {context['Sex']} | Complaint: {context['Chief_complain']}
    Vitals: BP {context['SBP']}/{context['DBP']}, HR {context['HR']}, SpO2 {context['Saturation']}%
    Signs: Mental-{context['Mental']}, Pain-{context['NRS_pain']}/10
    
    Prediction: KTAS Level {triage_level} ({confidence:.1f}%)
    
    1. Agree/Disagree?
    2. Clinical Reasoning (Brief).
    3. Immediate Action.
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
    except:
        return "AI Explanation Service Unavailable."

# ---------------------------------------------------------
# 3. SIDEBAR: PATIENT IDENTIFICATION
# ---------------------------------------------------------
st.sidebar.title("🆔 Patient ID")

# Voice Trigger
if st.sidebar.button("🎙️ AI Scribe", type="primary"):
    text = recognize_speech()
    if text:
        st.toast(f"Heard: '{text}'")
        data = extract_data_from_voice(text)
        if data:
            st.session_state.form_name = data.get('name', 'Unknown')
            # If AI hears age, we estimate DOB for the form
            est_age = int(data.get('age', 30))
            est_year = date.today().year - est_age
            st.session_state.form_dob = date(est_year, 1, 1)
            
            g_str = data.get('gender', 'Male').lower()
            st.session_state.form_gender_idx = 0 if 'fe' in g_str else 1
            
            s_str = data.get('symptom', '')
            matches = difflib.get_close_matches(s_str, CLEAN_COMPLAINTS, n=1, cutoff=0.4)
            if matches:
                st.session_state.form_complaint_idx = CLEAN_COMPLAINTS.index(matches[0])
            st.rerun()

st.sidebar.divider()

# Identification Fields
patient_name = st.sidebar.text_input("Full Name", value=st.session_state.form_name)
dob = st.sidebar.date_input("Date of Birth", value=st.session_state.form_dob)
gender = st.sidebar.selectbox("Sex", ["Male", "Female"], index=st.session_state.form_gender_idx)

# Auto-Calculate Age
current_age = calculate_age(dob)
st.sidebar.info(f"Calculated Age: **{current_age} years**")

# ---------------------------------------------------------
# 4. MAIN CLINICAL INTERFACE
# ---------------------------------------------------------
st.title("🏥 Triage Assessment")

# --- ROW 1: PRIMARY SURVEY (Subjective) ---
st.subheader("1. Primary Survey")
c1, c2, c3, c4 = st.columns(4)

with c1:
    arrival_mode_txt = st.selectbox("🚑 Arrival Mode", list(ARRIVAL_MAP.keys()))
with c2:
    chief_complaint_text = st.selectbox("🤒 Chief Complaint", options=CLEAN_COMPLAINTS, index=st.session_state.form_complaint_idx)
with c3:
    injury_txt = st.selectbox("🤕 Trauma / Injury", list(INJURY_MAP.keys()))
with c4:
    mental_txt = st.selectbox("🧠 Mental Status", list(MENTAL_MAP.keys()))

# --- ROW 2: VITALS & PAIN (Objective) ---
st.subheader("2. Vitals & Signs")
v1, v2, v3, v4, v5, v6 = st.columns(6)

sbp = v1.number_input("SBP (mmHg)", 0, 300, 120)
dbp = v2.number_input("DBP (mmHg)", 0, 200, 80)
hr = v3.number_input("Pulse (bpm)", 0, 300, 80)
rr = v4.number_input("Resp (bpm)", 0, 100, 20)
bt = v5.number_input("Temp (°C)", 30.0, 45.0, 36.5)
sat = v6.number_input("SpO2 (%)", 0, 100, 98)

# Pain Section (Slider + Logic)
st.write("---")
col_p1, col_p2 = st.columns([1, 3])
with col_p1:
    pain_txt = st.radio("Patient Reports Pain?", ["No", "Yes"], horizontal=True)
with col_p2:
    nrs_pain = st.slider("NRS Pain Scale (0-10)", 0, 10, 0, disabled=(pain_txt=="No"))

# ---------------------------------------------------------
# 5. PREDICTION LOGIC
# ---------------------------------------------------------
st.write("##")
if st.button("🔍 Run Clinical Decision Support", type="primary", use_container_width=True):
    with st.spinner("Analyzing Clinical Data..."):
        time.sleep(0.5)
        
        # A. MAP UI INPUTS TO MODEL VALUES
        val_arrival = ARRIVAL_MAP[arrival_mode_txt]
        val_injury = INJURY_MAP[injury_txt]
        val_mental = MENTAL_MAP[mental_txt]
        val_pain = PAIN_MAP[pain_txt]
        val_sex_int = 0 if gender == "Male" else 1 # Matching training (0=Male, 1=Female usually, verify your specific model training)
        
        # Note: Check your specific model training for Sex. 
        # Usually: 0=Female, 1=Male OR 1=Male, 2=Female. 
        # Based on previous snippets: Input_data['Sex'] = 1 if gender == 2 else 0 -> implies 2 was Male? 
        # I will assume: 0=Female, 1=Male for standard, adjust if your specific pickle differs.
        # ADAPTING TO YOUR PREVIOUS CODE SNIPPET LOGIC:
        # prev code: input_data['Sex'] = 1 if gender == 2 else 0 (where 2 was Male)
        # Here gender is "Male"/"Female". 
        model_sex = 1 if gender == "Male" else 0 

        # B. PREPARE DATAFRAME
        input_data = pd.DataFrame(0, index=[0], columns=model_features)
        
        input_data['Sex'] = model_sex
        input_data['Age'] = current_age
        input_data['Arrival mode'] = val_arrival
        input_data['Injury'] = 1 if val_injury == 2 else 0 # Fix: Model trained 0/1 or 1/2? Usually 0/1. 
        # Previous code said: "Model expects 1 (No) and 2 (Yes)"
        # So we keep that logic:
        input_data['Injury'] = val_injury 
        
        input_data['Mental'] = val_mental
        input_data['Pain'] = val_pain
        input_data['NRS_pain'] = nrs_pain if pain_txt == "Yes" else 0
        input_data['SBP'] = sbp
        input_data['DBP'] = dbp
        input_data['HR'] = hr
        input_data['RR'] = rr
        input_data['BT'] = bt
        input_data['Saturation'] = sat
        
        # One-Hot Encoding
        target_col = f"Chief_complain_Cleaned_{chief_complaint_text}"
        if target_col in input_data.columns:
            input_data[target_col] = 1
        elif 'Chief_complain_Cleaned_Other' in input_data.columns:
            input_data['Chief_complain_Cleaned_Other'] = 1

        # C. PREDICT
        probs = model.predict_proba(input_data)[0]
        
        # Safety Net Logic
        if probs[0] > 0.25: # >25% chance of Level 1
            ai_level = 1
            reason = "⚠️ Safety Net: High Probability of Critical Resuscitation"
        else:
            top_idx = np.argmax(probs)
            ai_level = int(top_idx + 1)
            reason = ""
            
        conf = float(probs[ai_level-1] * 100)

        # D. EXPLAIN
        context = {
            'Age': current_age, 'Sex': gender, 
            'Chief_complain': chief_complaint_text,
            'Arrival_mode': arrival_mode_txt,
            'Injury': injury_txt, 'Mental': mental_txt,
            'Pain': pain_txt, 'NRS_pain': nrs_pain,
            'SBP': sbp, 'DBP': dbp, 'HR': hr, 'RR': rr, 'BT': bt, 'Saturation': sat,
            'Shock_Index': round(hr/max(1, sbp), 2),
            'Pulse_Pressure': sbp - dbp
        }
        
        explanation = get_ai_explanation(context, ai_level, conf)

        st.session_state.triage_result = {
            "level": ai_level, "conf": conf, "reason": reason, 
            "explanation": explanation, "context": context
        }

# ---------------------------------------------------------
# 6. RESULTS & DISPOSITION
# ---------------------------------------------------------
if st.session_state.triage_result:
    res = st.session_state.triage_result
    st.markdown("---")
    
    # Visual Result
    c_res, c_exp = st.columns([1, 2])
    with c_res:
        color_map = {1: "#d32f2f", 2: "#f57c00", 3: "#fbc02d", 4: "#388e3c", 5: "#1976d2"}
        lvl = res['level']
        st.markdown(f"""
        <div style="background-color: {color_map.get(lvl, '#888')}; padding: 20px; border-radius: 10px; text-align: center; color: white;">
            <h4 style="margin:0;">RECOMMENDED KTAS</h4>
            <h1 style="font-size: 80px; margin:0; font-weight:bold;">{lvl}</h1>
            <p>Confidence: {res['conf']:.1f}%</p>
        </div>
        """, unsafe_allow_html=True)
        if res['reason']: st.error(res['reason'])
    
    with c_exp:
        st.subheader("💡 Model Reasoning")
        st.info(res['explanation'])

    # DISPOSITION BUTTONS
    st.subheader("📋 Disposition & Save")
    col_a, col_b, col_c = st.columns(3)
    
    # 1. ACCEPT
    if col_a.button("✅ ACCEPT & ADMIT", type="primary", use_container_width=True):
        if not patient_name:
            st.error("Missing Patient Name")
        else:
            # Prepare formatted DOB string for DB
            dob_str = dob.strftime("%Y-%m-%d")
            
            # Map values back to Integers for DB
            db_arrival = ARRIVAL_MAP[arrival_mode_txt]
            db_injury = INJURY_MAP[injury_txt]
            db_mental = MENTAL_MAP[mental_txt]
            db_pain = PAIN_MAP[pain_txt]
            
            database.add_patient(
                name=patient_name, dob=dob_str, age=current_age, gender=gender,
                arrival_mode=db_arrival, injury=db_injury, complaint=chief_complaint_text,
                mental=db_mental, pain=db_pain, nrs_pain=nrs_pain,
                sbp=sbp, dbp=dbp, hr=hr, rr=rr, bt=bt, saturation=sat,
                final_level=res['level'], ai_level=res['level'], conf=res['conf'], 
                explanation=res['explanation'], notes="Auto-Accepted via Triage Console",
                triage_nurse=current_nurse, status="Waiting"
            )
            st.success("Patient Admitted to Queue.")
            time.sleep(1)
            reset_form()

    # 2. HOLD
    if col_b.button("⏸️ PLACE ON HOLD", use_container_width=True):
        if not patient_name: st.error("Missing Name")
        else:
            dob_str = dob.strftime("%Y-%m-%d")
            db_arrival = ARRIVAL_MAP[arrival_mode_txt]
            db_injury = INJURY_MAP[injury_txt]
            db_mental = MENTAL_MAP[mental_txt]
            db_pain = PAIN_MAP[pain_txt]

            database.add_patient(
                name=patient_name, dob=dob_str, age=current_age, gender=gender,
                arrival_mode=db_arrival, injury=db_injury, complaint=chief_complaint_text,
                mental=db_mental, pain=db_pain, nrs_pain=nrs_pain,
                sbp=sbp, dbp=dbp, hr=hr, rr=rr, bt=bt, saturation=sat,
                final_level=res['level'], ai_level=res['level'], conf=res['conf'], 
                explanation=res['explanation'], notes="Pending Review",
                triage_nurse=current_nurse, status="On Hold"
            )
            st.warning("Saved to Hold List.")
            time.sleep(1)
            reset_form()

    # 3. OVERRIDE
    with st.expander("⚠️ Clinical Override / Decline"):
        with st.form("override_form"):
            ov_level = st.selectbox("Assign Correct Level", [1, 2, 3, 4, 5], index=res['level']-1)
            ov_notes = st.text_area("Justification (Required for Audit)")
            
            if st.form_submit_button("💾 Save Override"):
                if not ov_notes:
                    st.error("Medical justification is required for override.")
                elif not patient_name:
                    st.error("Missing Patient Name")
                else:
                    dob_str = dob.strftime("%Y-%m-%d")
                    db_arrival = ARRIVAL_MAP[arrival_mode_txt]
                    db_injury = INJURY_MAP[injury_txt]
                    db_mental = MENTAL_MAP[mental_txt]
                    db_pain = PAIN_MAP[pain_txt]

                    database.add_patient(
                        name=patient_name, dob=dob_str, age=current_age, gender=gender,
                        arrival_mode=db_arrival, injury=db_injury, complaint=chief_complaint_text,
                        mental=db_mental, pain=db_pain, nrs_pain=nrs_pain,
                        sbp=sbp, dbp=dbp, hr=hr, rr=rr, bt=bt, saturation=sat,
                        final_level=ov_level, ai_level=res['level'], conf=res['conf'], 
                        explanation=res['explanation'], notes=f"OVERRIDE: {ov_notes}",
                        triage_nurse=current_nurse, status="Waiting"
                    )
                    st.success("Override Saved.")
                    time.sleep(1)
                    reset_form()