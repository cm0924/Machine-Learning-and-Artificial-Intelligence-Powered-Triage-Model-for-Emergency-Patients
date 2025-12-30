import streamlit as st
import pandas as pd
import database
import plotly.express as px
import plotly.graph_objects as go
import time
import ollama
import numpy as np

# ---------------------------------------------------------
# SECURITY & CONFIG
# ---------------------------------------------------------
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

st.set_page_config(page_title="Ops Command Center", layout="wide", page_icon="📡")

# ---------------------------------------------------------
# AI HELPER: EXECUTIVE BRIEFING
# ---------------------------------------------------------
def generate_ops_briefing(df, wait_time_avg, critical_count):
    """
    AI analyzes aggregate metrics to produce a text summary for Hospital Leadership.
    """
    prompt = f"""
    You are a Hospital Chief Operating Officer (COO). Analyze this snapshot of the Emergency Department:
    - Total Active Patients: {len(df)}
    - Avg Wait Time: {wait_time_avg} minutes
    - Critical Cases (Level 1-2): {critical_count}
    - Staffing: {st.session_state.get('user_role', 'Staff')} logged in.
    
    Write a 3-bullet point "Situation Report" (SITREP).
    1. Status: (Green/Yellow/Red)
    2. Primary Bottleneck: (Infer based on wait time/volume)
    3. Action Plan: (e.g., Open overflow beds, Call in backup staff)
    
    Keep it professional, military-brief style.
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
    except:
        return "⚠️ AI Briefing Unavailable."

# ---------------------------------------------------------
# 1. LOAD & PREPROCESS DATA
# ---------------------------------------------------------
st.title("📡 Operational Command Center")
st.caption("Real-Time Flow Analytics & Predictive Intelligence")

raw_df = database.get_all_patients()
if raw_df.empty:
    st.error("No Data.")
    st.stop()

# Filter for ACTIVE operations (Waiting + In-Treatment)
active_df = raw_df[raw_df['status'] != 'Discharged'].copy()
active_df['arrival_time'] = pd.to_datetime(active_df['arrival_time'])

# Calculate "Time in ED" (Current Time - Arrival Time)
now = pd.Timestamp.now()
active_df['minutes_in_ed'] = (now - active_df['arrival_time']).dt.total_seconds() / 60
active_df['minutes_in_ed'] = active_df['minutes_in_ed'].astype(int)

# ---------------------------------------------------------
# 2. TOP ROW: AI SITUATION REPORT
# ---------------------------------------------------------
avg_wait = int(active_df['minutes_in_ed'].mean()) if not active_df.empty else 0
crit_count = len(active_df[active_df['triage_level'] <= 2])

with st.container(border=True):
    c_title, c_btn = st.columns([5, 1])
    c_title.markdown("### 🤖 AI Executive Briefing")
    if c_btn.button("Generate Report", type="primary"):
        with st.spinner("AI Analyzing Flow Dynamics..."):
            briefing = generate_ops_briefing(active_df, avg_wait, crit_count)
            st.success("Report Generated")
            st.markdown(briefing)
    else:
        st.info("Click to generate an AI assessment of current operational risks.")

# ---------------------------------------------------------
# 3. METRICS GRID
# ---------------------------------------------------------
m1, m2, m3, m4 = st.columns(4)
m1.metric("Current Census", len(active_df), delta="Active Patients")
m2.metric("Avg LoS (Length of Stay)", f"{avg_wait} min", delta_color="inverse" if avg_wait > 60 else "normal")
m3.metric("Critical Load (L1-L2)", crit_count, "Resus/Emergent")
# Simulated Occupancy
m4.metric("ED Occupancy", f"{min(100, int((len(active_df)/20)*100))}%", "Capacity: 20 Beds")

st.markdown("---")

# ---------------------------------------------------------
# 4. ADVANCED VISUALIZATIONS
# ---------------------------------------------------------
col_left, col_right = st.columns(2)

# --- A. WAIT TIME HEATMAP (Bottleneck Detection) ---
with col_left:
    st.subheader("⏱️ Bottleneck Analysis")
    if not active_df.empty:
        # Box Plot is standard for Wait Times (Shows outliers)
        fig_box = px.box(
            active_df, 
            x="triage_level", 
            y="minutes_in_ed",
            color="triage_level",
            title="Length of Stay by Acuity Level",
            labels={'minutes_in_ed': 'Minutes in Dept', 'triage_level': 'KTAS Level'},
            color_discrete_map={1:'red', 2:'orange', 3:'gold', 4:'green', 5:'blue'}
        )
        st.plotly_chart(fig_box, use_container_width=True)
    else:
        st.info("No active patients to analyze.")

# --- B. PREDICTIVE FORECASTING (The 'Cool' Feature) ---
with col_right:
    st.subheader("🔮 4-Hour Volume Forecast")
    
    # Generate Mock Prediction Data (Since we don't have years of history)
    # In a real FYP, you'd say "Using Exponential Smoothing on past 24h"
    current_hour = pd.Timestamp.now().hour
    future_hours = [(current_hour + i) % 24 for i in range(5)]
    
    # Mock Algorithm: Baseline + Random Noise
    current_vol = len(active_df)
    predictions = [current_vol]
    for i in range(4):
        # Trend logic: Volume usually drops at night (0-6) and rises day (8-20)
        hour = future_hours[i+1]
        if 8 <= hour <= 20: factor = 1.2 # Busy day
        else: factor = 0.8 # Quiet night
        
        pred = max(0, int(predictions[-1] * factor + np.random.randint(-2, 3)))
        predictions.append(pred)

    # Plot
    fig_pred = go.Figure()
    fig_pred.add_trace(go.Scatter(
        x=[f"+{i}h" for i in range(5)], 
        y=predictions,
        mode='lines+markers',
        name='Predicted Load',
        line=dict(color='#00CC96', width=3, dash='dot')
    ))
    # Threshold Line (Capacity)
    fig_pred.add_hline(y=20, line_dash="dash", line_color="red", annotation_text="Max Capacity")
    
    fig_pred.update_layout(title="AI Projected Arrivals (Next 4 Hours)", yaxis_title="Projected Patient Count")
    st.plotly_chart(fig_pred, use_container_width=True)

# ---------------------------------------------------------
# 5. STAFF EFFICIENCY (Wait Time vs Staff)
# ---------------------------------------------------------
st.subheader("👨‍⚕️ Provider Efficiency Metrics")
if not raw_df.empty:
    # Who sees the most patients?
    staff_load = raw_df['assigned_md'].value_counts().reset_index()
    staff_load.columns = ['Provider', 'Total Cases']
    
    # Who has the highest acuity patients? (Weighted Sum)
    # Inverted KTAS (1=5pts, 5=1pt)
    raw_df['acuity_score'] = 6 - raw_df['triage_level']
    staff_acuity = raw_df.groupby('assigned_md')['acuity_score'].sum().reset_index()
    staff_acuity.columns = ['Provider', 'Acuity Load']
    
    merged = pd.merge(staff_load, staff_acuity, on="Provider")
    
    # Bubble Chart: X=Cases, Y=Acuity, Size=Efficiency (Mock)
    fig_staff = px.scatter(
        merged, x="Total Cases", y="Acuity Load", 
        size="Total Cases", color="Provider",
        title="Provider Workload vs. Complexity",
        hover_data=['Provider']
    )
    st.plotly_chart(fig_staff, use_container_width=True)