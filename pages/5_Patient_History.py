import streamlit as st
import pandas as pd
import database
import time
import plotly.express as px
import ollama

# ---------------------------------------------------------
# SECURITY CHECK
# ---------------------------------------------------------
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

st.set_page_config(page_title="Master Patient Index", layout="wide", page_icon="🗄️")

# ---------------------------------------------------------
# AI HELPER: SEMANTIC SEARCH
# ---------------------------------------------------------
def get_semantic_matches(df, query):
    if not query: return df
    records = df[['id', 'complaint', 'clinical_summary']].to_dict(orient='records')
    records_str = "\n".join([f"ID {r['id']}: {r['complaint']} | {str(r.get('clinical_summary',''))}" for r in records])
    
    prompt = f"""
    You are a Medical Search Engine.
    User Query: "{query}"
    Database Records: {records_str}
    Task: Return ONLY a JSON list of IDs that clinically match the user's query.
    Example: [101, 104, 110]
    If no matches, return [].
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        content = response['message']['content']
        import json
        start = content.find('[')
        end = content.find(']') + 1
        return json.loads(content[start:end])
    except:
        return []

# ---------------------------------------------------------
# 1. LOAD DATA
# ---------------------------------------------------------
all_patients = database.get_all_patients()

st.title("🗄️ Master Patient Index (MPI)")
st.caption("Central Registry for Clinical Audit, Coding, and Research.")

if all_patients.empty:
    st.warning("No records found.")
    st.stop()

# Variable to track selection across tabs
selected_patient_data = None

# ---------------------------------------------------------
# 2. TABS
# ---------------------------------------------------------
tab_registry, tab_analytics, tab_ai_query = st.tabs(["📋 Patient Registry", "📊 Population Health", "🤖 Semantic Query"])

# === TAB 1: REGISTRY (Standard Search) ===
with tab_registry:
    c_search, c_status = st.columns([2, 1])
    search_query = c_search.text_input("🔍 Quick Search (Name/ID)", placeholder="Type to filter...")
    status_filter = c_status.multiselect("Status", all_patients['status'].unique(), default=all_patients['status'].unique())
    
    filtered_df = all_patients.copy()
    filtered_df = filtered_df[filtered_df['status'].isin(status_filter)]
    
    if search_query:
        filtered_df = filtered_df[
            filtered_df['name'].str.contains(search_query, case=False, na=False) | 
            filtered_df['id'].astype(str).str.contains(search_query)
        ]

    # DATAFRAME WITH SELECTION
    event_reg = st.dataframe(
        filtered_df[['id', 'arrival_time', 'name', 'age', 'gender', 'triage_level', 'status', 'final_disposition']],
        column_config={
            "id": st.column_config.NumberColumn("MRN", width="small"),
            "arrival_time": st.column_config.DatetimeColumn("Date", format="MMM DD, YY"),
            "triage_level": st.column_config.NumberColumn("KTAS", width="small"),
        },
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key="registry_grid" # Unique Key is required
    )
    
    # Capture Selection Tab 1
    if len(event_reg.selection.rows) > 0:
        idx = event_reg.selection.rows[0]
        selected_patient_data = filtered_df.iloc[idx]

# === TAB 2: ANALYTICS ===
with tab_analytics:
    st.markdown("### 📈 ED Performance & Clinical Trends")
    row1_1, row1_2 = st.columns(2)
    with row1_1:
        fig_acuity = px.bar(all_patients['triage_level'].value_counts().sort_index(), title="Acuity Distribution", color_discrete_sequence=['#1E88E5'])
        st.plotly_chart(fig_acuity, use_container_width=True)
    with row1_2:
        clean_disp = all_patients['final_disposition'].fillna('Unknown')
        fig_disp = px.pie(names=clean_disp.unique(), values=clean_disp.value_counts(), title="Outcomes", hole=0.4)
        st.plotly_chart(fig_disp, use_container_width=True)

# === TAB 3: AI QUERY ===
with tab_ai_query:
    st.markdown("### 🤖 AI Cohort Builder")
    col_ai_input, col_ai_btn = st.columns([4, 1])
    user_prompt = col_ai_input.text_input("Describe cohort", placeholder="e.g. 'Respiratory issues' or 'Trauma'")
    
    # Session state to keep results after rerun (caused by clicking the grid)
    if 'ai_results_ids' not in st.session_state: st.session_state.ai_results_ids = []
    
    if col_ai_btn.button("🔍 Search", type="primary"):
        with st.spinner("AI Analyzing..."):
            st.session_state.ai_results_ids = get_semantic_matches(all_patients, user_prompt)
    
    # Render results if they exist
    if st.session_state.ai_results_ids:
        ai_df = all_patients[all_patients['id'].isin(st.session_state.ai_results_ids)]
        st.caption(f"Found {len(ai_df)} matches.")
        
        event_ai = st.dataframe(
            ai_df[['id', 'name', 'complaint', 'clinical_summary']],
            column_config={"clinical_summary": st.column_config.TextColumn("Context", width="large")},
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="ai_grid" # Unique Key
        )
        
        # Capture Selection Tab 3
        if len(event_ai.selection.rows) > 0:
            idx = event_ai.selection.rows[0]
            selected_patient_data = ai_df.iloc[idx]
    else:
        st.info("Enter a query to find patients.")

# ---------------------------------------------------------
# 3. ACTION BAR (THE MISSING PIECE)
# ---------------------------------------------------------
st.markdown("---")

if selected_patient_data is not None:
    # We found a selection from EITHER Tab 1 or Tab 3
    pid = int(selected_patient_data['id'])
    pname = selected_patient_data['name']
    
    # Highlight the selection
    st.success(f"Selected Patient: **{pname}** (MRN: {pid})")
    
    col_act1, col_act2, col_act3 = st.columns([1, 1, 3])
    
    with col_act1:
        # THE OPEN CHART BUTTON
        if st.button("📂 Open Chart", type="primary", use_container_width=True):
            st.session_state['selected_patient_id'] = pid
            st.switch_page("pages/4_Patient_Details.py")
            
    with col_act2:
        # Quick CSV Export for single patient
        st.download_button(
            "📥 Download Record", 
            selected_patient_data.to_frame().to_csv(), 
            f"{pname}_record.csv", 
            "text/csv", 
            use_container_width=True
        )
else:
    st.caption("👆 **Select a patient** from the Registry or AI Search to view details.")

# Bulk Export (Always visible)
with st.expander("Admin: Bulk Data Export"):
    st.download_button("📥 Export Entire Database (CSV)", all_patients.to_csv(index=False), "hospital_db_full.csv", "text/csv")