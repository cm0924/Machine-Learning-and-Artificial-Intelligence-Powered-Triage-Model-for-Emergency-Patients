import streamlit as st
import pandas as pd
import database
import plotly.graph_objects as go
import plotly.express as px
import time

if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

st.set_page_config(page_title="Nurse Detail Dashboard", layout="wide", page_icon="📈")

# 1. LOAD DATA
df = database.get_all_patients()

if df.empty:
    st.error("No data found. Please regenerate database.")
    st.stop()

# 2. SIDEBAR FILTER
st.sidebar.header("Dashboard Settings")
nurses = df['triage_nurse'].dropna().unique()
if len(nurses) == 0:
    st.warning("No nurse data recorded yet.")
    st.stop()
    
selected_nurse = st.sidebar.selectbox("Select Nurse", options=nurses, index=0)

# Filter Dataset
nurse_df = df[df['triage_nurse'] == selected_nurse].copy()

# 3. CALCULATE CONCORDANCE LOGIC
# Agree: Levels match
# Up-Triage: Nurse Level < AI Level (e.g. Nurse 2, AI 3) -> Nurse thinks it's MORE critical
# Down-Triage: Nurse Level > AI Level (e.g. Nurse 4, AI 3) -> Nurse thinks it's LESS critical
def get_concordance(row):
    if row['triage_level'] == row['ai_level']: return "AGREE"
    elif row['triage_level'] < row['ai_level']: return "UP-TRIAGE"
    else: return "DOWN-TRIAGE"

nurse_df['concordance'] = nurse_df.apply(get_concordance, axis=1)

# 4. HEADER
st.title("NURSE-DETAIL DASHBOARD")
st.markdown(f"### NURSE: **{selected_nurse}**")
st.markdown("---")

# =========================================================
# UPPER SECTION: CHARTS & SUMMARY
# =========================================================
c1, c2, c3 = st.columns([2, 1.5, 1.5])

# --- CHART 1: BAR CHART (Distribution) ---
with c1:
    st.caption("Acuity Distribution Comparison")
    
    # Calculate counts 1-5
    dist_data = []
    for i in range(1, 6):
        dist_data.append({"Level": str(i), "Count": len(nurse_df[nurse_df['triage_level'] == i]), "Type": "Nurse Assignment"})
        dist_data.append({"Level": str(i), "Count": len(nurse_df[nurse_df['ai_level'] == i]), "Type": "AI Model"})
    
    dist_df = pd.DataFrame(dist_data)
    
    # Custom Colors to match image (Dark Blue vs Light Blue)
    fig_bar = px.bar(dist_df, x="Level", y="Count", color="Type", barmode="group",
                     color_discrete_map={"Nurse Assignment": "#0b2559", "AI Model": "#4a90e2"})
    fig_bar.update_layout(margin=dict(t=0, l=0, r=0, b=0), height=250, legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig_bar, use_container_width=True)

# --- CHART 2: DONUT CHART (Concordance) ---
with c2:
    st.caption("Concordance Rate")
    counts = nurse_df['concordance'].value_counts()
    
    agree_val = counts.get("AGREE", 0)
    up_val = counts.get("UP-TRIAGE", 0)
    down_val = counts.get("DOWN-TRIAGE", 0)
    total = len(nurse_df)
    
    # Colors: Orange (Agree), Brown/Yellow (Up/Down) to match image
    colors = ['#e67e22', '#f39c12', '#d35400'] # Orange shades
    
    fig_donut = go.Figure(data=[go.Pie(
        labels=['Agree', 'Up-Triage', 'Down-Triage'],
        values=[agree_val, up_val, down_val],
        hole=.6,
        marker=dict(colors=colors),
        textinfo='percent',
        sort=False
    )])
    
    # Add Text in Center
    agree_pct = int((agree_val/total)*100) if total > 0 else 0
    fig_donut.update_layout(
        annotations=[dict(text=f"{agree_pct}%", x=0.5, y=0.5, font_size=24, showarrow=False)],
        margin=dict(t=0, l=0, r=0, b=0), 
        height=250,
        showlegend=False
    )
    st.plotly_chart(fig_donut, use_container_width=True)
    
    # Legend below graph
    cols = st.columns(3)
    cols[0].markdown(f"🟧 **Agree**")
    cols[1].markdown(f"🟨 **Up**")
    cols[2].markdown(f"🟫 **Down**")

# --- TABLE 3: SUMMARY METRICS ---
with c3:
    st.caption("Performance Metrics")
    
    # Calculate Percentages
    p_agree = (agree_val / total * 100) if total else 0
    p_up = (up_val / total * 100) if total else 0
    p_down = (down_val / total * 100) if total else 0
    
    # Create HTML Table for cleaner look
    st.markdown(f"""
    <table style="width:100%; text-align: center; border-collapse: collapse;">
      <tr style="background-color: #0b2559; color: white;">
        <th style="padding: 8px; text-align:left;">METRIC</th>
        <th style="padding: 8px;">VALUE</th>
        <th style="padding: 8px;">TARGET</th>
      </tr>
      <tr>
        <td style="text-align:left; font-weight:bold;">AGREE</td>
        <td>{p_agree:.1f}%</td>
        <td style="color:green;">&gt; 75%</td>
      </tr>
      <tr>
        <td style="text-align:left; font-weight:bold;">UP-TRIAGE</td>
        <td>{p_up:.1f}%</td>
        <td style="color:gray;">&lt; 15%</td>
      </tr>
      <tr>
        <td style="text-align:left; font-weight:bold;">DOWN-TRIAGE</td>
        <td>{p_down:.1f}%</td>
        <td style="color:gray;">&lt; 15%</td>
      </tr>
    </table>
    """, unsafe_allow_html=True)
    
    # Logic for Distinction
    st.write("")
    if p_down > 15:
        st.error("⚠️ Down-Triage Rate exceeds safety target.")
    elif p_agree < 75:
        st.warning("⚠️ Agreement Rate low.")
    else:
        st.success("✅ Performance meets standards.")

# =========================================================
# LOWER SECTION: OUTCOME ANALYSIS (The "Deep Dive")
# =========================================================
st.write("")
st.subheader("Outcome Rates by Concordance")
st.caption("Do patients triaged differently have different admission outcomes?")

# Helper to calculate stats per bucket
def get_stats(data_subset):
    if len(data_subset) == 0: return 0, 0, 0, 0
    count = len(data_subset)
    # Define Critical: ICU or Surgery
    crit = len(data_subset[data_subset['final_disposition'].isin(['ICU'])])
    surg = len(data_subset[data_subset['final_disposition'].isin(['Surgery'])])
    admit = len(data_subset[data_subset['final_disposition'].isin(['Admit', 'ICU', 'Surgery'])])
    return count, (crit/count)*100, (surg/count)*100, (admit/count)*100

# Create specific buckets as per image (High Acuity, Mid Acuity, Low Acuity)
rows = []

# 1. HIGH ACUITY (Level 1-2)
high_subset = nurse_df[nurse_df['triage_level'].isin([1, 2])]
for c_type in ["AGREE", "UP-TRIAGE", "DOWN-TRIAGE"]: # Note: You can't usually down-triage INTO high acuity, but logic holds
    sub = high_subset[high_subset['concordance'] == c_type]
    if len(sub) > 0:
        c, cr, sr, ar = get_stats(sub)
        rows.append(["HIGH ACUITY (1-2)", c_type, c, cr, sr, ar])

# 2. MID ACUITY (Level 3)
mid_subset = nurse_df[nurse_df['triage_level'] == 3]
for c_type in ["AGREE", "UP-TRIAGE", "DOWN-TRIAGE"]:
    sub = mid_subset[mid_subset['concordance'] == c_type]
    if len(sub) > 0:
        c, cr, sr, ar = get_stats(sub)
        rows.append(["MID ACUITY (3)", c_type, c, cr, sr, ar])

# 3. LOW ACUITY (Level 4-5)
low_subset = nurse_df[nurse_df['triage_level'].isin([4, 5])]
for c_type in ["AGREE", "UP-TRIAGE", "DOWN-TRIAGE"]:
    sub = low_subset[low_subset['concordance'] == c_type]
    if len(sub) > 0:
        c, cr, sr, ar = get_stats(sub)
        rows.append(["LOW ACUITY (4-5)", c_type, c, cr, sr, ar])

# Display DataFrame
outcome_df = pd.DataFrame(rows, columns=["Assigned Acuity", "Concordance", "Visits", "Critical Rate", "Surgery Rate", "Admit Rate"])

# Format formatting
st.dataframe(
    outcome_df,
    column_config={
        "Critical Rate": st.column_config.NumberColumn(format="%.1f%%"),
        "Surgery Rate": st.column_config.NumberColumn(format="%.1f%%"),
        "Admit Rate": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
    },
    use_container_width=True,
    hide_index=True
)

st.info("💡 **Analysis:** High admission rates in 'DOWN-TRIAGED' rows indicate dangerous undertriage (Nurse categorized as mild, but patient required admission).")