import streamlit as st
import pandas as pd
import database
import plotly.express as px
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

st.set_page_config(page_title="Clinical QA", layout="wide", page_icon="🛡️")

# --- CUSTOM CSS FOR POLISH ---
st.markdown("""
<style>
    .feedback-box {
        background-color: var(--secondary-background-color);
        color: var(--text-color);
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #4a90e2;
        font-size: 16px;
        line-height: 1.5;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# AI HELPER: QUALITATIVE ANALYSIS
# ---------------------------------------------------------
def analyze_nurse_behavior(nurse_name, discordant_df):
    if discordant_df.empty:
        return "No disagreements found. The Clinician and AI are in perfect sync."
    
    # Prepare data for AI
    sample = discordant_df.head(5)[['complaint', 'triage_level', 'ai_level', 'nurse_notes']].to_dict(orient='records')
    text_data = "\n".join([f"- Case: {s['complaint']} | Human Lvl: {s['triage_level']} vs AI Lvl: {s['ai_level']} | Note: {str(s['nurse_notes'])}" for s in sample])
    
    prompt = f"""
    You are a Mentor for Emergency Nurses. 
    Analyze these disagreements between Clinician '{nurse_name}' and the AI Model.
    
    Data (Disagreements):
    {text_data}
    
    Task: Write a simple, encouraging feedback summary (max 3 sentences).
    1. What is the trend? (e.g., "You tend to rate chest pain more seriously than the AI.")
    2. Was the human right?
    3. Suggest a quick tip.
    
    Use simple, professional language.
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
    except Exception as e:
        return f"⚠️ AI Analysis Service Unavailable. Error: {e}"

# ---------------------------------------------------------
# 1. LOAD & FILTER DATA
# ---------------------------------------------------------
df = database.get_all_patients()
if df.empty:
    st.info("No records available.")
    st.stop()

# --- ROLE-BASED ACCESS ---
current_user = st.session_state.get('username', 'Unknown')
user_role = st.session_state.get('user_role', 'nurse')

# Map Usernames to Real Names
users_df = database.get_all_users()
name_map = dict(zip(users_df['username'], users_df['full_name']))
df['triage_nurse_display'] = df['triage_nurse'].map(name_map).fillna(df['triage_nurse'])
available_nurses = df['triage_nurse_display'].unique()

st.sidebar.title("🛡️ Audit Controls")

if user_role == 'admin':
    selected_nurse_name = st.sidebar.selectbox("Select Staff Member", available_nurses)
else:
    my_full_name = name_map.get(current_user, current_user)
    st.sidebar.info(f"Viewing Performance: **{my_full_name}**")
    selected_nurse_name = my_full_name

# Filter Data
nurse_df = df[df['triage_nurse_display'] == selected_nurse_name].copy()

if nurse_df.empty:
    st.warning(f"No records found for **{selected_nurse_name}**.")
    st.stop()

# ---------------------------------------------------------
# 2. LOGIC: SIMPLIFIED VERDICTS (FIXED & APPLIED)
# ---------------------------------------------------------
def judge_decision(row):
    # 1. Agreement
    if row['triage_level'] == row['ai_level']:
        return "Agreed"

    # --- DEFINITION OF "SICK" (ADMITTED) ---
    # We convert to lowercase and check for keywords to handle 
    # "Admitted to ICU", "Admitted to Ward", "Transfer", etc.
    dispo = str(row['final_disposition']).lower()
    
    # Patient is "Sick" if they went to: Admit, ICU, Ward, Transfer, Surgery
    patient_was_sick = any(keyword in dispo for keyword in ['admit', 'icu', 'ward', 'transfer', 'surgery'])
    
    # --- LOGIC MAPPING TO DOCUMENTATION TABLE ---
    
    human_score = row['triage_level']
    ai_score = row['ai_level']
    
    # Note: KTAS 1 = Highest Priority, KTAS 5 = Lowest Priority.
    # Therefore, Lower Number = "Stricter" / Higher Number = "Relaxed"
    
    human_stricter = human_score < ai_score  # e.g., Human 2, AI 4
    human_relaxed  = human_score > ai_score  # e.g., Human 4, AI 2

    # CASE A: Human Saved Patient
    # Logic: Human was Stricter AND Patient was Sick (Admitted)
    if human_stricter and patient_was_sick:
        return "✅ Human Saved Patient"
        
    # CASE B: Critical Miss
    # Logic: Human was Relaxed (Missed it) AND Patient was Sick (Admitted)
    if human_relaxed and patient_was_sick:
        return "❌ Critical Miss (Under-Triage)"
        
    # CASE C: Human Over-Cautious
    # Logic: Human was Stricter AND Patient went Home (Not Sick)
    if human_stricter and not patient_was_sick:
        return "⚠️ Human Over-Cautious"
        
    # CASE D: AI False Alarm
    # Logic: Human was Relaxed AND Patient went Home (Not Sick)
    if human_relaxed and not patient_was_sick:
        return "✅ AI False Alarm (Human Correct)"
    
    return "Inconclusive"

# ---------------------------------------------------------
# CRITICAL FIX: APPLY THE LOGIC BEFORE CALCULATING METRICS
# ---------------------------------------------------------
# This line creates the 'audit_result' column. 
# Without this, the next section will crash.
nurse_df['audit_result'] = nurse_df.apply(judge_decision, axis=1)

# ---------------------------------------------------------
# 3. DASHBOARD HEADER
# ---------------------------------------------------------
st.title(f"Clinical Quality Assurance: {selected_nurse_name}")
st.markdown("### 🎯 Accuracy & Decision Quality")

# KPI CALCS
total_cases = len(nurse_df)
consensus = len(nurse_df[nurse_df['audit_result'] == "Agreed"])
dangerous = len(nurse_df[nurse_df['audit_result'] == "❌ Critical Miss (Under-Triage)"])
saves = len(nurse_df[nurse_df['audit_result'] == "✅ Human Saved Patient"])

with st.container(border=True):
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Patients", total_cases)
    k2.metric("AI Agreement Rate", f"{(consensus/total_cases)*100:.1f}%")
    k3.metric("Human 'Saves'", saves, "Caught AI Errors", delta_color="normal")
    k4.metric("Critical Misses", dangerous, "Under-Estimated", delta_color="inverse")

st.divider()

# ---------------------------------------------------------
# 4. CHART & AI FEEDBACK
# ---------------------------------------------------------
col_left, col_right = st.columns([1.5, 1])

with col_left:
    st.subheader("📊 Outcomes of Disagreements")
    st.caption("What happened when the Human disagreed with the AI?")
    
    discordant = nurse_df[nurse_df['audit_result'] != "Agreed"]
    
    if not discordant.empty:
        chart_data = discordant['audit_result'].value_counts().reset_index()
        chart_data.columns = ['Result', 'Count']
        
        fig = px.bar(
            chart_data,
            x='Result', y='Count',
            color='Result',
            color_discrete_map={
                "✅ Human Saved Patient": "#2ecc71",       # Green
                "✅ AI False Alarm (Human Correct)": "#27ae60", # Dark Green
                "⚠️ Human Over-Cautious": "#f1c40f",       # Yellow
                "❌ Critical Miss (Under-Triage)": "#e74c3c"    # Red
            },
            text_auto=True
        )
        fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Number of Cases")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.success("🎉 Perfect Agreement! No disagreements to analyze.")

with col_right:
    st.subheader("🤖 AI Mentor Feedback")
    st.caption("Automated coaching based on decision patterns.")
    
    if st.button("📝 Generate Feedback", type="primary", use_container_width=True):
        with st.spinner("Analyzing patterns..."):
            feedback = analyze_nurse_behavior(selected_nurse_name, discordant)
            
            st.markdown(f"""
            <div class="feedback-box">
                <strong style="font-size:18px;">📋 Mentor Notes</strong>
                <hr style="margin: 10px 0; border-color: rgba(0,0,0,0.1);">
                {feedback}
            </div>
            """, unsafe_allow_html=True)
            
            if dangerous > 0:
                st.error("⚠️ **Tip:** Review Sepsis Protocols.")
            elif saves > 3:
                st.success("🌟 **Great Job:** You consistently catch critical cases the AI misses.")
    else:
        st.info("Click above to generate a coaching summary.")

# ---------------------------------------------------------
# 5. DATA TABLE
# ---------------------------------------------------------
st.write("")
st.subheader("🔍 Case Details")
st.dataframe(
    # Added 'id' as the first column
    nurse_df[['id', 'arrival_time', 'complaint', 'triage_level', 'ai_level', 'final_disposition', 'audit_result']],
    column_config={
        "id": st.column_config.NumberColumn("MRN", width="small"), # <--- New Config
        "arrival_time": st.column_config.DatetimeColumn("Date", format="MMM DD HH:mm"),
        "audit_result": st.column_config.TextColumn("Verdict", width="medium"),
        "triage_level": st.column_config.NumberColumn("Human Lvl", width="small"),
        "ai_level": st.column_config.NumberColumn("AI Lvl", width="small"),
        "final_disposition": "Outcome"
    },
    use_container_width=True,
    hide_index=True
)

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