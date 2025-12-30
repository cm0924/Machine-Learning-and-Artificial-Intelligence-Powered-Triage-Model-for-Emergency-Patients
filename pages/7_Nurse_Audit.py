import streamlit as st
import pandas as pd
import database
import plotly.express as px
import plotly.graph_objects as go
import time
import ollama

# ---------------------------------------------------------
# SECURITY & SETUP
# ---------------------------------------------------------
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

st.set_page_config(page_title="Clinical Quality Audit", layout="wide", page_icon="🛡️")

# ---------------------------------------------------------
# AI HELPER: QUALITATIVE ANALYSIS
# ---------------------------------------------------------
def analyze_nurse_behavior(nurse_name, discordant_df):
    """
    Uses AI to read the notes of cases where Nurse Disagreed with AI
    to find clinical reasoning patterns.
    """
    if discordant_df.empty:
        return "No discordant cases to analyze."
    
    # Prepare a mini-text dump of the disagreements
    # Limit to 5 records to save context window
    sample = discordant_df.head(5)[['complaint', 'triage_level', 'ai_level', 'nurse_notes']].to_dict(orient='records')
    text_data = "\n".join([f"- Case: {s['complaint']} | Nurse Lvl: {s['triage_level']} vs AI Lvl: {s['ai_level']} | Note: {s['nurse_notes']}" for s in sample])
    
    prompt = f"""
    You are a Clinical Quality Auditor. Analyze these triage overrides by Nurse {nurse_name}.
    
    Data (Disagreements):
    {text_data}
    
    Task: Write a 3-sentence professional feedback summary.
    1. Identify the clinical pattern (e.g., "The nurse prioritizes patient pain over vitals").
    2. Assess if the rationale seems valid.
    3. Suggest a training topic if needed.
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
    except:
        return "⚠️ AI Analysis Service Unavailable."

# ---------------------------------------------------------
# 1. LOAD & FILTER DATA
# ---------------------------------------------------------
df = database.get_all_patients()
if df.empty:
    st.error("No data available.")
    st.stop()

# Clean Data
df['triage_nurse'] = df['triage_nurse'].fillna('Unassigned')
nurses = df['triage_nurse'].unique()

# SIDEBAR CONTROLS
st.sidebar.title("🛡️ Quality Audit")
selected_nurse = st.sidebar.selectbox("Select Clinician", nurses)

# Filter for this nurse
nurse_df = df[df['triage_nurse'] == selected_nurse].copy()

# ---------------------------------------------------------
# 2. LOGIC: WHO WAS RIGHT? (The "Gold Standard" Proxy)
# ---------------------------------------------------------
# We use 'final_disposition' (Admit/Home) as the "Truth".
# High Acuity (1-3) SHOULD result in Admit/ICU.
# Low Acuity (4-5) SHOULD result in Discharge/Home.

def judge_decision(row):
    # Skip if they agreed
    if row['triage_level'] == row['ai_level']:
        return "Consensus"

    # Define "Sick" based on Outcome
    is_sick = row['final_disposition'] in ['Admit', 'ICU', 'Surgery', 'Transfer']
    
    # 1. Nurse SAVE (Nurse was stricter, and patient WAS sick)
    # Nurse < AI (Lower number = Sicker)
    if row['triage_level'] < row['ai_level'] and is_sick:
        return "✅ Nurse Save (Safety Net)"
        
    # 2. Nurse OVER-REACTION (Nurse was stricter, but patient went Home)
    if row['triage_level'] < row['ai_level'] and not is_sick:
        return "⚠️ Over-Triage (Resource Drain)"
        
    # 3. Dangerous MISS (Nurse was relaxed, but patient WAS sick)
    # Nurse > AI
    if row['triage_level'] > row['ai_level'] and is_sick:
        return "❌ Dangerous Under-Triage"
        
    # 4. AI False Alarm (Nurse was relaxed, and patient went Home)
    if row['triage_level'] > row['ai_level'] and not is_sick:
        return "✅ Nurse Correct (AI False Alarm)"
    
    return "Inconclusive"

nurse_df['audit_result'] = nurse_df.apply(judge_decision, axis=1)

# ---------------------------------------------------------
# 3. DASHBOARD HEADER
# ---------------------------------------------------------
st.title(f"Clinical Performance: {selected_nurse}")
st.markdown("### 🎯 Accuracy & Liability Analysis")

# KPI CALCS
total_cases = len(nurse_df)
consensus = len(nurse_df[nurse_df['audit_result'] == "Consensus"])
dangerous = len(nurse_df[nurse_df['audit_result'] == "❌ Dangerous Under-Triage"])
saves = len(nurse_df[nurse_df['audit_result'] == "✅ Nurse Save (Safety Net)"])

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Cases Triage", total_cases)
k2.metric("AI Consensus Rate", f"{(consensus/total_cases)*100:.1f}%")
k3.metric("Safety Net 'Saves'", saves, "Nurse Correctly Overrode AI", delta_color="normal")
k4.metric("Risk Events", dangerous, "Nurse Missed / AI Caught", delta_color="inverse")

st.divider()

# ---------------------------------------------------------
# 4. DEEP DIVE: THE "DISAGREEMENT" ANALYSIS
# ---------------------------------------------------------
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("📊 Audit Outcomes (Discordant Cases)")
    st.caption("Analyzing only cases where Nurse and AI disagreed.")
    
    # Filter only disagreements for the chart
    discordant = nurse_df[nurse_df['audit_result'] != "Consensus"]
    
    if not discordant.empty:
        fig = px.bar(
            discordant['audit_result'].value_counts().reset_index(),
            x='audit_result', y='count',
            color='audit_result',
            title="Outcome of Clinical Overrides",
            color_discrete_map={
                "✅ Nurse Save (Safety Net)": "green",
                "✅ Nurse Correct (AI False Alarm)": "lightgreen",
                "⚠️ Over-Triage (Resource Drain)": "orange",
                "❌ Dangerous Under-Triage": "red"
            }
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Perfect agreement! No discordant cases to analyze.")

with col_right:
    st.subheader("🤖 AI Performance Coach")
    st.caption("Generative analysis of triage notes in discordant cases.")
    
    if st.button("📝 Generate Feedback Report", type="primary"):
        with st.spinner("Analyzing clinical reasoning patterns..."):
            # Pass the discordant dataframe to the AI
            feedback = analyze_nurse_behavior(selected_nurse, discordant)
            
            st.success("Analysis Complete")
            st.markdown(f"""
            <div style="background-color:#f0f2f6; padding:15px; border-radius:10px; border-left: 5px solid #4a90e2;">
                <b>🤖 AI Auditor Notes:</b><br><br>
                {feedback}
            </div>
            """, unsafe_allow_html=True)
            
            # Simulated Action Plan
            if dangerous > 0:
                st.error("⚠️ ACTION REQUIRED: Assign 'Sepsis Detection' training module.")
            else:
                st.success("✅ No remedial training required.")

# ---------------------------------------------------------
# 5. DETAILED LOG
# ---------------------------------------------------------
st.subheader("🔍 Case Drill-Down")
st.dataframe(
    nurse_df[['arrival_time', 'complaint', 'triage_level', 'ai_level', 'final_disposition', 'audit_result']],
    column_config={
        "audit_result": st.column_config.TextColumn("Audit Verdict", width="medium"),
        "triage_level": st.column_config.NumberColumn("Nurse Lvl", width="small"),
        "ai_level": st.column_config.NumberColumn("AI Lvl", width="small"),
        "final_disposition": "Outcome"
    },
    use_container_width=True
)