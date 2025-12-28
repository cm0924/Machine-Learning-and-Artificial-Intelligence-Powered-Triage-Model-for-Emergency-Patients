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
# 1. SETUP & SESSION STATE
# ---------------------------------------------------------
st.set_page_config(page_title="Clinical Decision Support", page_icon="🩺", layout="wide")

# THE LIST OF CLEAN CATEGORIES (Must match your Training Data exactly!)
CLEAN_COMPLAINTS = [
    'Abdominal Pain', 'Altered Mental Status', 'Back Pain', 'Bleeding (General)', 
    'Chest Pain', 'Diarrhea/GI Issue', 'Dizziness', 'Eye Problem', 'Fever', 
    'Headache', 'Musculoskeletal Pain', 'Nausea/Vomiting', 'Neurological Deficit', 
    'Other', 'Palpitation', 'Psychiatric', 'Respiratory/Dyspnea', 'Seizure', 
    'Skin/Allergy', 'Syncope', 'Trauma/Injury', 'Urinary Issue'
]

# --- UPDATED LOADING FUNCTION ---
@st.cache_resource
def load_system():
    try:
        # Load the dictionary containing {model, features}
        package = joblib.load('ktas_deployment_pipeline.pkl') 
        return package
    except FileNotFoundError:
        st.error("System Error: 'ktas_deployment_pipeline.pkl' not found. Please run your notebook to save it.")
        return None

system_package = load_system()

if system_package:
    model = system_package['model']
    model_features = system_package['features']
else:
    st.stop()

# Initialize Session State
if 'form_name' not in st.session_state: st.session_state.form_name = "Unknown"
if 'form_age' not in st.session_state: st.session_state.form_age = 30
if 'form_gender_idx' not in st.session_state: st.session_state.form_gender_idx = 0
if 'form_complaint_idx' not in st.session_state: st.session_state.form_complaint_idx = 4 # Default to Chest Pain
if 'triage_result' not in st.session_state: st.session_state.triage_result = None

def reset_form():
    st.session_state.triage_result = None
    st.rerun()

# ---------------------------------------------------------
# 2. AI FUNCTIONS (Voice, LLM)
# ---------------------------------------------------------

def recognize_speech():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        st.toast("🎤 Listening... (e.g., 'Male 50 years old with severe chest pain')")
        try:
            audio = r.listen(source, timeout=5)
            text = r.recognize_google(audio)
            return text
        except Exception as e:
            st.error(f"Voice Error: {e}")
            return None

def extract_data_from_voice(text):
    """ Uses LLM to parse voice text into JSON """
    prompt = f"""
    Extract clinical entities from: "{text}"
    Return ONLY raw JSON (no markdown) with keys:
    - "name": (string)
    - "age": (int)
    - "gender": ("Male"/"Female")
    - "symptom": (string, pick closest match from: {CLEAN_COMPLAINTS}) 
    
    Example: {{"name": "Ali", "age": 50, "gender": "Male", "symptom": "Chest Pain"}}
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
    """ Generates the 'Why' using the LLM with FULL Context """
    prompt = f"""
    Act as a senior triage nurse. Review this AI prediction.
    
    Patient Demographics: {context['Age']}yo {context['Sex']} ({context['Arrival_mode']})
    Chief Complaint: {context['Chief_complain']}
    
    Clinical Signs:
    - Mental Status: {context['Mental']}
    - Trauma/Injury: {context['Injury']}
    - Pain: {context['Pain']} (Scale: {context['NRS_pain']}/10)
    
    Vitals: 
    - BP: {context['SBP']}/{context['DBP']} mmHg
    - HR: {context['HR']} bpm
    - RR: {context['RR']} /min
    - Temp: {context['BT']} °C
    - SpO2: {context['Saturation']}%
    
    Derived Markers:
    - Shock Index: {context['Shock_Index']} (Normal < 0.7)
    - Pulse Pressure: {context['Pulse_Pressure']} (Normal 30-50)
    
    AI Model Prediction: KTAS Level {triage_level} ({confidence:.1f}% confidence)
    
    Task:
    1. Do you AGREE or DISAGREE with Level {triage_level}?
    2. Explain your reasoning using the Vitals and Signs above.
    3. List 2 immediate nursing actions.
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
    except:
        return "AI Explanation Service Unavailable."

# ---------------------------------------------------------
# 3. SIDEBAR INPUTS
# ---------------------------------------------------------
st.sidebar.title("📝 Triage Input")

if st.sidebar.button("🎙️ AI Scribe (Voice Fill)", type="primary"):
    text = recognize_speech()
    if text:
        st.toast(f"Heard: '{text}'")
        data = extract_data_from_voice(text)
        if data:
            st.session_state.form_name = data.get('name', 'Unknown')
            st.session_state.form_age = int(data.get('age', 30))
            
            # Match Gender
            g_str = data.get('gender', 'Male').lower()
            st.session_state.form_gender_idx = 0 if 'fe' in g_str else 1
            
            # Fuzzy Match Symptom to our CLEAN list
            s_str = data.get('symptom', '')
            matches = difflib.get_close_matches(s_str, CLEAN_COMPLAINTS, n=1, cutoff=0.4)
            if matches:
                st.session_state.form_complaint_idx = CLEAN_COMPLAINTS.index(matches[0])
            st.rerun()

st.sidebar.divider()

# --- FORM ---
patient_name = st.sidebar.text_input("Name", value=st.session_state.form_name)
col1, col2 = st.sidebar.columns(2)
gender = col1.selectbox("Sex", [1, 2], 
                        index=st.session_state.form_gender_idx, 
                        format_func=lambda x: "Female" if x==1 else "Male")
age = col2.number_input("Age", 0, 120, value=st.session_state.form_age)

st.sidebar.subheader("Clinical Signs")
# Use the CLEAN list for the dropdown
chief_complaint_text = st.sidebar.selectbox("Chief Complaint", options=CLEAN_COMPLAINTS, index=st.session_state.form_complaint_idx)

arrival = st.sidebar.selectbox("Arrival", [1, 2, 3], format_func=lambda x: {1:"Ambulance", 2:"Walk-in", 3:"Transfer"}.get(x, x))

# FIX: Model expects 1 (No) and 2 (Yes) for Injury based on your data inspection
injury = st.sidebar.selectbox("Trauma?", [1, 2], format_func=lambda x: "No" if x==1 else "Yes") 

mental = st.sidebar.selectbox("Mental Status", [1, 2, 3, 4], format_func=lambda x: {1:"Alert", 2:"Verbal", 3:"Pain", 4:"Unresponsive"}.get(x, x))
pain = st.sidebar.selectbox("Pain?", [0, 1], format_func=lambda x: "No" if x==0 else "Yes")
nrs_pain = st.sidebar.slider("NRS Pain Scale", 0, 10, 0)

sbp = st.sidebar.number_input("SBP", 0, 300, 120)
dbp = st.sidebar.number_input("DBP", 0, 200, 80)
hr = st.sidebar.number_input("Pulse", 0, 300, 80)
rr = st.sidebar.number_input("Resp Rate", 0, 100, 20)
bt = st.sidebar.number_input("Temp (°C)", 30.0, 45.0, 36.5)
sat = st.sidebar.number_input("SpO2 (%)", 0, 100, 98)

# ---------------------------------------------------------
# 4. MAIN WORKFLOW (THE NEW BRAIN)
# ---------------------------------------------------------
st.title("🏥 Intelligent Triage System (XGBoost + Safety Net)")

if st.button("🔍 Generate Assessment", type="primary", use_container_width=True):
    with st.spinner("Predicting Triage Level..."):
        time.sleep(0.5)
        
        # 1. CREATE DATAFRAME FROM LOADED FEATURE LIST
        # The columns will match the 'Pure' model (No Shock Index column)
        input_data = pd.DataFrame(0, index=[0], columns=model_features)
        
        # 2. FILL VITALS & DEMOGRAPHICS
        input_data['Sex'] = 1 if gender == 2 else 0  
        input_data['Age'] = age
        input_data['Arrival mode'] = arrival
        input_data['Injury'] = 1 if injury == 2 else 0 
        input_data['Mental'] = mental
        input_data['Pain'] = pain     
        input_data['NRS_pain'] = nrs_pain
        input_data['SBP'] = sbp
        input_data['DBP'] = dbp
        input_data['HR'] = hr
        input_data['RR'] = rr
        input_data['BT'] = bt
        input_data['Saturation'] = sat
        
        # 3. ONE-HOT ENCODE CHIEF COMPLAINT
        target_col = f"Chief_complain_Cleaned_{chief_complaint_text}"
        
        if target_col in input_data.columns:
            input_data[target_col] = 1
        else:
            if 'Chief_complain_Cleaned_Other' in input_data.columns:
                input_data['Chief_complain_Cleaned_Other'] = 1

        # 4. CALCULATE DERIVED VALUES (For Explanation ONLY)
        # We calculate these for the Context dictionary, but we DO NOT add them 
        # to 'input_data' because the XGBoost model wasn't trained on them.
        safe_sbp = sbp if sbp > 0 else 1.0
        val_shock_index = hr / safe_sbp
        val_pulse_pressure = sbp - dbp
        
        # 5. PREDICT & APPLY SAFETY THRESHOLD
        # Now input_data has exactly 34 columns (matching training), so this works:
        probs = model.predict_proba(input_data)[0]
        
        # Safety Rule: If >25% chance of Level 1, Force Level 1
        if probs[0] > 0.25:
            ai_level = 1
            reason = "⚠️ Safety Net: High Risk of Shock/Resuscitation"
        else:
            top_idx = np.argmax(probs)
            ai_level = int(top_idx + 1)
            reason = ""
            
        conf = float(probs[ai_level-1] * 100)

        # 6. EXPLANATION GENERATION
        mental_map = {1:"Alert", 2:"Verbal", 3:"Pain", 4:"Unresponsive"}
        arrival_map = {1:"Ambulance", 2:"Walk-in", 3:"Transfer"}
        injury_map = {1:"No", 2:"Yes"}
        
        context = {
            'Age': age, 
            'Sex': 'Male' if gender==2 else 'Female', 
            'Chief_complain': chief_complaint_text,
            'Arrival_mode': arrival_map.get(arrival, "Unknown"),
            'Injury': injury_map.get(injury, "No"),
            'Mental': mental_map.get(mental, "Unknown"),
            'Pain': "Yes" if pain==1 else "No",
            'NRS_pain': nrs_pain,
            'SBP': sbp, 
            'DBP': dbp, 
            'HR': hr, 
            'RR': rr, 
            'BT': bt, 
            'Saturation': sat, 
            # We use the variables we calculated above, not input_data columns
            'Shock_Index': round(val_shock_index, 2),
            'Pulse_Pressure': round(val_pulse_pressure, 2)
        }
        
        explanation = get_ai_explanation(context, ai_level, conf)

        st.session_state.triage_result = {
            "level": ai_level, "conf": conf, "reason": reason, "explanation": explanation
        }

# ---------------------------------------------------------
# 5. DISPLAY RESULTS & ACTIONS
# ---------------------------------------------------------
if st.session_state.triage_result:
    res = st.session_state.triage_result
    st.divider()
    
    col_res, col_exp = st.columns([1, 2])
    
    with col_res:
        color_map = {1: "#d32f2f", 2: "#f57c00", 3: "#fbc02d", 4: "#388e3c", 5: "#1976d2"}
        lvl = res['level']
        st.markdown(f"""
        <div style="background-color: {color_map.get(lvl, '#888')}; padding: 20px; border-radius: 10px; text-align: center; color: white;">
            <h3 style="margin:0;">KTAS LEVEL</h3>
            <h1 style="font-size: 90px; margin:0; font-weight:bold;">{lvl}</h1>
            <p>Confidence: {res['conf']:.1f}%</p>
        </div>
        """, unsafe_allow_html=True)
        if res['reason']: st.error(res['reason'])

    with col_exp:
        st.subheader("🤖 AI Reasoning")
        st.info(res['explanation'])
        
    st.write("### 🩺 Clinical Action")
    
    # --- ACTION BUTTONS ---
    c1, c2, c3 = st.columns(3)
    
    # Button 1: Accept
    if c1.button("✅ ACCEPT", type="primary", use_container_width=True):
        database.add_patient(
            name=patient_name, age=age, gender="Male" if gender==2 else "Female",
            arrival_mode=arrival, injury=injury, complaint=chief_complaint_text,
            mental=mental, pain=pain, nrs_pain=nrs_pain,
            sbp=sbp, dbp=dbp, hr=hr, rr=rr, bt=bt, saturation=sat,
            final_level=res['level'], ai_level=res['level'], conf=res['conf'], 
            explanation=res['explanation'], notes="Auto-Accepted",
            triage_nurse=current_nurse, status="Waiting"
        )
        st.success("Patient Admitted to Queue!")
        time.sleep(1)
        reset_form()

    # Button 2: Place on Hold
    if c2.button("⏸️ HOLD", use_container_width=True):
        database.add_patient(
            name=patient_name, age=age, gender="Male" if gender==2 else "Female",
            arrival_mode=arrival, injury=injury, complaint=chief_complaint_text,
            mental=mental, pain=pain, nrs_pain=nrs_pain,
            sbp=sbp, dbp=dbp, hr=hr, rr=rr, bt=bt, saturation=sat,
            final_level=res['level'], ai_level=res['level'], conf=res['conf'], 
            explanation=res['explanation'], notes="Review Pending",
            triage_nurse=current_nurse, status="On Hold"
        )
        st.warning("Patient placed On Hold.")
        time.sleep(1)
        reset_form()

    # Button 3: Manual Override (Expander)
    with st.expander("⚠️ Override / Decline AI Prediction", expanded=False):
        with st.form("override_form"):
            new_level = st.selectbox("Select Correct Level", [1, 2, 3, 4, 5], index=res['level']-1)
            nurse_notes = st.text_area("Clinical Justification")
            
            if st.form_submit_button("💾 Save Manual Triage"):
                if not nurse_notes: 
                    st.error("Justification required.")
                else:
                    database.add_patient(
                        name=patient_name, age=age, gender="Male" if gender==2 else "Female",
                        arrival_mode=arrival, injury=injury, complaint=chief_complaint_text,
                        mental=mental, pain=pain, nrs_pain=nrs_pain,
                        sbp=sbp, dbp=dbp, hr=hr, rr=rr, bt=bt, saturation=sat,
                        final_level=new_level, ai_level=res['level'], conf=res['conf'], 
                        explanation=res['explanation'], notes=nurse_notes,
                        triage_nurse=current_nurse, status="Waiting"
                    )
                    st.success("Override Saved.")
                    time.sleep(1)
                    reset_form()