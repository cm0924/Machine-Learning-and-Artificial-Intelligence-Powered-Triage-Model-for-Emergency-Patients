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
    st.warning("⚠️ Access Restricted. Redirecting...")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

current_nurse = st.session_state.get('full_name', 'Unknown')

# ---------------------------------------------------------
# 1. CONFIGURATION & STYLING
# ---------------------------------------------------------
st.set_page_config(page_title="Triage Assessment", page_icon="🩺", layout="wide")

st.markdown("""
<style>
    .block-container {padding-top: 1.5rem; padding-bottom: 3rem;}
    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        background-color: white; border-radius: 8px; padding: 20px;
        border: 1px solid #e0e0e0; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .triage-card {
        border-left: 10px solid #333; background-color: #f8f9fa;
        padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .age-box {
        text-align: center; background-color: #e3f2fd; padding: 10px;
        border-radius: 8px; border: 1px solid #90caf9; color: #0d47a1 !important;
    }
    .age-label {font-size: 12px; font-weight: bold; text-transform: uppercase; color: #1565c0 !important;}
    .age-value {font-size: 28px; font-weight: 800; line-height: 1.2;}
    
    /* Make Audio Input Compact */
    div[data-testid="stAudioInput"] {
        margin-top: 0px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# MAPPINGS & MODEL LOADING
# ---------------------------------------------------------
CLEAN_COMPLAINTS = [
    'Abdominal Pain', 'Altered Mental Status', 'Back Pain', 'Bleeding (General)', 
    'Chest Pain', 'Diarrhea/GI Issue', 'Dizziness', 'Eye Problem', 'Fever', 
    'Headache', 'Musculoskeletal Pain', 'Nausea/Vomiting', 'Neurological Deficit', 
    'Other', 'Palpitation', 'Psychiatric', 'Respiratory/Dyspnea', 'Seizure', 
    'Skin/Allergy', 'Syncope', 'Trauma/Injury', 'Urinary Issue'
]

ARRIVAL_MAP = {"Ambulance": 1, "Walk-in": 2, "Transfer": 3}
INJURY_MAP = {"No": 1, "Yes": 2}
MENTAL_MAP = {"Alert": 1, "Verbal": 2, "Pain": 3, "Unresponsive": 4}
PAIN_MAP = {"No": 0, "Yes": 1}

@st.cache_resource
def load_system():
    try:
        return joblib.load('ktas_deployment_pipeline.pkl') 
    except FileNotFoundError:
        st.error("System Error: AI Model not found.")
        return None

system_package = load_system()
if system_package:
    model = system_package['model']
    model_features = system_package['features']
else:
    st.stop()

# --- SESSION STATE INITIALIZATION ---
defaults = {
    'form_name': "", 'form_dob': date(1990, 1, 1), 'form_gender_idx': 0,
    'form_arrival_idx': 1, 'form_complaint_idx': 4, 'form_injury_idx': 0, 'form_mental_idx': 0,
    'form_sbp': 120, 'form_dbp': 80, 'form_hr': 80, 'form_rr': 20, 'form_bt': 36.5, 'form_sat': 98,
    'form_pain_txt': "No", 'form_nrs': 0
}

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

if 'triage_result' not in st.session_state: st.session_state.triage_result = None

def reset_form():
    for key, val in defaults.items():
        st.session_state[key] = val
    st.session_state.triage_result = None
    st.rerun()

def calculate_age(born):
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

# ---------------------------------------------------------
# 2. AI HELPERS (UPDATED)
# ---------------------------------------------------------
def transcribe_audio_file(audio_bytes):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(audio_bytes) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data)
            return text
    except Exception as e:
        print(f"Transcription Error: {e}")
        return None

def extract_full_clinical_data(text):
    prompt = f"""
    Extract clinical data from this dictation: "{text}"
    Return valid JSON with these keys (use null if not found):
    - "name": string
    - "age": int
    - "gender": "Male" or "Female"
    - "symptom": string (Map to closest: {CLEAN_COMPLAINTS})
    - "arrival": "Ambulance", "Walk-in", "Transfer"
    - "injury": "Yes" or "No"
    - "mental": "Alert", "Verbal", "Pain", or "Unresponsive"
    - "sbp": int
    - "dbp": int
    - "hr": int
    - "rr": int
    - "temp": float
    - "spo2": int
    - "pain_score": int
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        content = response['message']['content']
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match: return json.loads(json_match.group(0))
    except: pass
    return None

# --- UPDATED FUNCTION FOR "THIRD PERSON VIEW" ---
# --- UPDATED AI EXPLANATION FUNCTION ---
def get_ai_explanation(context, triage_level, confidence):
    prompt = f"""
    Act as a Senior Clinical Auditor. 
    You have received a patient case and a prediction from an XGBoost Algorithm (KTAS Protocol).
    
    PATIENT CASE DATA:
    - Demographics: {context['Age']} year old {context['Sex']}
    - Arrival Mode: {context['Arrival']}
    - Chief Complaint: {context['Chief_complain']}
    - Physical Trauma/Injury: {context['Injury']}
    
    VITALS & SIGNS:
    - Hemodynamics: BP {context['SBP']}/{context['DBP']} mmHg, HR {context['HR']} bpm
    - Respiratory: RR {context['RR']} /min, SpO2 {context['Saturation']}%
    - Thermoregulation: Temp {context['BT']} °C
    - Neuro/Pain: Mental Status "{context['Mental']}", Pain Score {context['NRS_pain']}/10 ({context['Pain']})
    
    ALGORITHM PREDICTION: 
    - KTAS Level {triage_level} (Confidence: {confidence:.1f}%)
    
    TASK:
    1. Independent Analysis: Evaluate the severity based on the Vitals (Stability) and Complaint (Lethality).
    2. Audit: Compare your analysis with the Algorithm's prediction.
    3. Verdict: State if you AGREE or DISAGREE.
    
    OUTPUT FORMAT:
    1. **Auditor Verdict:** [AGREE] or [DISAGREE -> Suggest Level X]
    2. **Clinical Reasoning:** (Cite specific abnormal vitals or risk factors)
    3. **Recommendation:** (e.g., "Immediate Resus", "High-dependency bed", "Waiting Room")
    Keep it concise and professional.
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
    except:
        return "AI Explanation Service Unavailable."

# ---------------------------------------------------------
# 3. REVIEW DIALOG
# ---------------------------------------------------------
@st.dialog("📝 Review Extracted Data")
def review_voice_data(extracted_data):
    st.caption("Verify the AI-extracted values before populating the chart.")
    
    with st.form("review_form"):
        c1, c2 = st.columns(2)
        with c1:
            r_name = st.text_input("Name", value=extracted_data.get('name') or "")
            r_age = st.number_input("Est. Age", value=int(extracted_data.get('age') or 30))
            e_sex = extracted_data.get('gender') or "Male"
            r_sex = st.selectbox("Sex", ["Male", "Female"], index=0 if e_sex == "Male" else 1)
            
        with c2:
            s_sym = extracted_data.get('symptom') or ""
            match_sym = difflib.get_close_matches(str(s_sym), CLEAN_COMPLAINTS, n=1, cutoff=0.3)
            default_sym_idx = CLEAN_COMPLAINTS.index(match_sym[0]) if match_sym else 4
            r_sym = st.selectbox("Complaint", CLEAN_COMPLAINTS, index=default_sym_idx)
            
            s_arr = extracted_data.get('arrival') or "Walk-in"
            # Ensure s_arr is in list, else default to Walk-in
            try:
                arr_idx = list(ARRIVAL_MAP.keys()).index(s_arr)
            except ValueError:
                arr_idx = 1
            r_arr = st.selectbox("Arrival", list(ARRIVAL_MAP.keys()), index=arr_idx)

        st.markdown("---")
        # Added Trauma & Mental to Review
        c3, c4 = st.columns(2)
        with c3:
            s_inj = extracted_data.get('injury') or "No"
            inj_idx = 1 if s_inj == "Yes" else 0
            r_inj = st.selectbox("Trauma/Injury?", list(INJURY_MAP.keys()), index=inj_idx)
        with c4:
            s_men = extracted_data.get('mental') or "Alert"
            try:
                men_idx = list(MENTAL_MAP.keys()).index(s_men)
            except ValueError:
                men_idx = 0
            r_men = st.selectbox("Mental Status", list(MENTAL_MAP.keys()), index=men_idx)

        st.markdown("---")
        st.markdown("###### Vitals & Signs")
        v1, v2, v3 = st.columns(3)
        r_sbp = v1.number_input("SBP", value=int(extracted_data.get('sbp') or 120))
        r_dbp = v2.number_input("DBP", value=int(extracted_data.get('dbp') or 80))
        r_hr = v3.number_input("HR", value=int(extracted_data.get('hr') or 80))
        
        v4, v5, v6 = st.columns(3)
        r_rr = v4.number_input("RR", value=int(extracted_data.get('rr') or 20))
        r_bt = v5.number_input("Temp", value=float(extracted_data.get('temp') or 36.5))
        r_sat = v6.number_input("SpO2", value=int(extracted_data.get('spo2') or 98))
        
        r_pain = st.slider("Pain Score", 0, 10, int(extracted_data.get('pain_score') or 0))

        if st.form_submit_button("✅ Confirm & Populate Chart", type="primary"):
            st.session_state.form_name = r_name
            st.session_state.form_dob = date(date.today().year - r_age, 1, 1)
            st.session_state.form_gender_idx = 0 if r_sex == "Male" else 1
            st.session_state.form_complaint_idx = CLEAN_COMPLAINTS.index(r_sym)
            st.session_state.form_arrival_idx = list(ARRIVAL_MAP.keys()).index(r_arr)
            st.session_state.form_injury_idx = list(INJURY_MAP.keys()).index(r_inj)
            st.session_state.form_mental_idx = list(MENTAL_MAP.keys()).index(r_men)
            
            st.session_state.form_sbp = r_sbp
            st.session_state.form_dbp = r_dbp
            st.session_state.form_hr = r_hr
            st.session_state.form_rr = r_rr
            st.session_state.form_bt = r_bt
            st.session_state.form_sat = r_sat
            st.session_state.form_nrs = r_pain
            st.session_state.form_pain_txt = "Yes" if r_pain > 0 else "No"
            
            st.rerun()

# ---------------------------------------------------------
# 4. MAIN INTERFACE
# ---------------------------------------------------------
st.title("🩺 Clinical Triage Intake")
st.caption(f"Attending Nurse: {current_nurse} | {date.today().strftime('%d %B %Y')}")

# --- SECTION 1: PATIENT IDENTIFICATION ---
with st.container(border=True):
    st.markdown("#### 1. Patient Identification")
    
    c_mic, c_name, c_dob, c_sex, c_age = st.columns([1.2, 2.8, 2, 1.5, 1], vertical_alignment="bottom")
    
    with c_mic:
        st.write("🎙️ **AI Voice Scribe**")
        audio_val = st.audio_input("Record", label_visibility="collapsed")
        
        if audio_val is not None:
            if 'last_processed_audio' not in st.session_state or st.session_state.last_processed_audio != audio_val:
                st.session_state.last_processed_audio = audio_val
                
                with st.spinner("Transcribing & Extracting Clinical Data..."):
                    text = transcribe_audio_file(audio_val)
                    if text:
                        st.toast(f"Heard: {text[:30]}...")
                        data = extract_full_clinical_data(text)
                        if data:
                            review_voice_data(data)
                        else:
                            st.error("No clinical entities found.")
                    else:
                        st.error("Could not understand audio.")

    with c_name:
        patient_name = st.text_input("Full Name", value=st.session_state.form_name, placeholder="Last, First", help="Enter the patient's legal name.")
    
    with c_dob:
        dob = st.date_input("Date of Birth", value=st.session_state.form_dob, min_value=date(1900, 1, 1), max_value=date.today())
    
    with c_sex:
        gender = st.selectbox("Sex", ["Male", "Female"], index=st.session_state.form_gender_idx)
    
    with c_age:
        current_age = calculate_age(dob)
        st.markdown(f"""
        <div class="age-box">
            <div class="age-label">Age</div>
            <div class="age-value">{current_age}</div>
        </div>
        """, unsafe_allow_html=True)

st.write("") 

# --- SECTION 2: PRIMARY SURVEY ---
with st.container(border=True):
    st.markdown("#### 2. Primary Assessment")
    c1, c2, c3, c4 = st.columns(4)
    with c1: 
        arrival_mode_txt = st.selectbox("🚑 Arrival", list(ARRIVAL_MAP.keys()), index=st.session_state.form_arrival_idx)
    with c2: 
        chief_complaint_text = st.selectbox("🤒 Complaint", CLEAN_COMPLAINTS, index=st.session_state.form_complaint_idx)
    with c3: 
        injury_txt = st.selectbox("🤕 Physical Injury / Trauma?", list(INJURY_MAP.keys()), index=st.session_state.form_injury_idx)
    with c4: 
        mental_txt = st.selectbox("🧠 Mental", list(MENTAL_MAP.keys()), index=st.session_state.form_mental_idx)

st.write("") 

# --- SECTION 3: VITALS ---
with st.container(border=True):
    st.markdown("#### 3. Vital Signs & Pain Scale")
    
    v1, v2, v3, v4, v5, v6 = st.columns(6)
    sbp = v1.number_input("SBP (90-120)", 0, 300, st.session_state.form_sbp, help="Systolic BP")
    dbp = v2.number_input("DBP (60-80)", 0, 200, st.session_state.form_dbp, help="Diastolic BP")
    hr = v3.number_input("HR (60-100)", 0, 300, st.session_state.form_hr, help="Heart Rate")
    rr = v4.number_input("RR (12-20)", 0, 100, st.session_state.form_rr, help="Resp. Rate")
    bt = v5.number_input("Temp (36.5-37.5)", 30.0, 45.0, st.session_state.form_bt, step=0.1)
    sat = v6.number_input("SpO2 (>95%)", 0, 100, st.session_state.form_sat)

    st.markdown("---")
    
    col_p1, col_p2 = st.columns([1, 4], vertical_alignment="center")
    with col_p1:
        pain_idx = 0 if st.session_state.form_pain_txt == "No" else 1
        pain_txt = st.radio("Pain Present?", ["No", "Yes"], index=pain_idx, horizontal=True)
    with col_p2:
        nrs_disable = True if pain_txt == "No" else False
        nrs_pain = st.slider("NRS Scale (0-10)", 0, 10, st.session_state.form_nrs, disabled=nrs_disable)

# ---------------------------------------------------------
# 5. CDS ACTION
# ---------------------------------------------------------
st.write("##")
col_action_l, col_action_c, col_action_r = st.columns([1, 2, 1])

with col_action_c:
    if st.button("🔍 Run Clinical Decision Support", type="primary", use_container_width=True):
        if not patient_name:
            st.toast("⚠️ Patient Name Required", icon="❌")
        else:
            with st.spinner("AI Analyzing Protocol..."):
                time.sleep(0.5)
                
                # PREDICTION LOGIC
                val_arrival = ARRIVAL_MAP[arrival_mode_txt]
                val_injury = INJURY_MAP[injury_txt]
                val_mental = MENTAL_MAP[mental_txt]
                val_pain = PAIN_MAP[pain_txt]
                model_sex = 1 if gender == "Male" else 0 

                input_data = pd.DataFrame(0, index=[0], columns=model_features)
                input_data['Sex'] = model_sex
                input_data['Age'] = current_age
                input_data['Arrival mode'] = val_arrival
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
                
                target_col = f"Chief_complain_Cleaned_{chief_complaint_text}"
                if target_col in input_data.columns: input_data[target_col] = 1
                elif 'Chief_complain_Cleaned_Other' in input_data.columns: input_data['Chief_complain_Cleaned_Other'] = 1

                probs = model.predict_proba(input_data)[0]
                
                if probs[0] > 0.25: 
                    ai_level = 1
                    reason = "⚠️ CRITICAL: AI detects high probability of Level 1 (Resuscitation)."
                else:
                    ai_level = int(np.argmax(probs) + 1)
                    reason = ""
                    
                conf = float(probs[ai_level-1] * 100)

                context = {
                    'Age': current_age, 
                    'Sex': gender, 
                    'Chief_complain': chief_complaint_text,
                    'Arrival': arrival_mode_txt, # Added
                    'Injury': injury_txt,        # Added
                    'Mental': mental_txt, 
                    'Pain': pain_txt,            # Added
                    'NRS_pain': nrs_pain,
                    'SBP': sbp, 
                    'DBP': dbp, 
                    'HR': hr, 
                    'RR': rr, 
                    'BT': bt,                    # Added
                    'Saturation': sat
                }
                
                # Pass full context to the new function
                explanation = get_ai_explanation(context, ai_level, conf)

                st.session_state.triage_result = {
                    "level": ai_level, "conf": conf, "reason": reason, 
                    "explanation": explanation, "context": context
                }

# ---------------------------------------------------------
# 6. RESULT DISPLAY
# ---------------------------------------------------------
if st.session_state.triage_result:
    res = st.session_state.triage_result
    color_map = {1: "#d32f2f", 2: "#f57c00", 3: "#fbc02d", 4: "#388e3c", 5: "#1976d2"}
    lvl = res['level']
    border_col = color_map.get(lvl, '#888')
    
    st.markdown("---")
    col_card, col_details = st.columns([1, 2])
    
    with col_card:
        st.markdown(f"""
        <div class="triage-card" style="border-left: 15px solid {border_col};">
            <h5 style="margin:0; color: #555;">RECOMMENDED KTAS</h5>
            <h1 style="font-size: 90px; margin:0; line-height: 1; color: {border_col};">Level {lvl}</h1>
            <p style="margin-top:10px; color: #333;"><b>Confidence:</b> {res['conf']:.1f}%</p>
        </div>
        """, unsafe_allow_html=True)
        if res['reason']: st.error(res['reason'], icon="🚨")

    with col_details:
        st.markdown("##### 💡 Clinical Reasoning (AI Generated)")
        st.info(res['explanation'])

    st.markdown("### 📋 Final Disposition")
    c_btn1, c_btn2, c_btn3 = st.columns(3)
    
    # ACCEPT Logic
    if c_btn1.button("✅ ACCEPT & ADMIT", type="primary", use_container_width=True):
        dob_str = dob.strftime("%Y-%m-%d")
        database.add_patient(
            name=patient_name, dob=dob_str, age=current_age, gender=gender,
            arrival_mode=ARRIVAL_MAP[arrival_mode_txt], injury=INJURY_MAP[injury_txt], 
            complaint=chief_complaint_text, mental=MENTAL_MAP[mental_txt], 
            pain=PAIN_MAP[pain_txt], nrs_pain=nrs_pain,
            sbp=sbp, dbp=dbp, hr=hr, rr=rr, bt=bt, saturation=sat,
            final_level=res['level'],   # Nurse Agrees -> Final is same as AI
            ai_level=res['level'],      # SAVE AI OPINION
            conf=res['conf'], 
            explanation=res['explanation'], notes="Auto-Accepted via Triage Console",
            triage_nurse=current_nurse, status="Waiting"
        )
        st.success(f"Patient {patient_name} admitted.")
        time.sleep(1.5)
        reset_form()

    # HOLD Logic
    if c_btn2.button("⏸️ PLACE ON HOLD", use_container_width=True):
        st.warning("Patient saved to 'Hold' list.")
        time.sleep(1)
        reset_form()

    # OVERRIDE Logic
    with st.expander("⚠️ Clinical Override"):
        with st.form("override_form"):
            ov_level = st.selectbox("Correct Level", [1, 2, 3, 4, 5], index=res['level']-1)
            ov_notes = st.text_area("Justification")
            if st.form_submit_button("💾 Save Override"):
                dob_str = dob.strftime("%Y-%m-%d")
                database.add_patient(
                    name=patient_name, dob=dob_str, age=current_age, gender=gender,
                    arrival_mode=ARRIVAL_MAP[arrival_mode_txt], injury=INJURY_MAP[injury_txt], 
                    complaint=chief_complaint_text, mental=MENTAL_MAP[mental_txt], 
                    pain=PAIN_MAP[pain_txt], nrs_pain=nrs_pain,
                    sbp=sbp, dbp=dbp, hr=hr, rr=rr, bt=bt, saturation=sat,
                    final_level=ov_level,       # Nurse OVERRIDES -> Final is different
                    ai_level=res['level'],      # SAVE AI OPINION
                    conf=res['conf'], 
                    explanation=res['explanation'], notes=f"OVERRIDE: {ov_notes}",
                    triage_nurse=current_nurse, status="Waiting"
                )
                st.success("Override Saved.")
                time.sleep(1.5)
                reset_form()

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