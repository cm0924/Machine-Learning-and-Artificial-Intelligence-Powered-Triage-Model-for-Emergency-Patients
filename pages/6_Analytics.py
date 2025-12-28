import streamlit as st
import pandas as pd
import database
import plotly.express as px
import time

if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

st.set_page_config(page_title="Hospital Analytics", layout="wide", page_icon="📊")
st.title("📊 Operational Analytics")

# 1. LOAD DATA
df = database.get_all_patients()
if df.empty:
    st.warning("No data available.")
    st.stop()

# Convert time to datetime objects
df['arrival_time'] = pd.to_datetime(df['arrival_time'])
df['hour'] = df['arrival_time'].dt.hour

# 2. KEY METRICS ROW
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Visits", len(df))
c2.metric("Critical Cases (Lvl 1-2)", len(df[df['triage_level'] <= 2]))
c3.metric("AI Agreement Rate", f"{len(df[df['triage_level'] == df['ai_level']]) / len(df) * 100:.1f}%")
c4.metric("Avg Pain Score", f"{df['nrs_pain'].mean():.1f}/10")

st.divider()

# 3. VISUALIZATIONS
col1, col2 = st.columns(2)

with col1:
    st.subheader("Distribution of Triage Levels")
    # Count per level
    level_counts = df['triage_level'].value_counts().reset_index()
    level_counts.columns = ['Level', 'Count']
    
    fig_pie = px.pie(level_counts, values='Count', names='Level', 
                     color='Level', 
                     color_discrete_map={1:'red', 2:'orange', 3:'gold', 4:'green', 5:'blue'})
    st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    st.subheader("Busy Hours (Heatmap)")
    hourly_counts = df['hour'].value_counts().sort_index().reset_index()
    hourly_counts.columns = ['Hour of Day', 'Patient Count']
    
    fig_bar = px.bar(hourly_counts, x='Hour of Day', y='Patient Count', color='Patient Count')
    st.plotly_chart(fig_bar, use_container_width=True)

# 4. STAFF PERFORMANCE
st.subheader("👨‍⚕️ Staff Workload")
if 'assigned_nurse' in df.columns:
    nurse_counts = df['assigned_nurse'].value_counts().reset_index()
    nurse_counts.columns = ['Nurse Name', 'Patients Seen']
    st.bar_chart(nurse_counts.set_index("Nurse Name"))