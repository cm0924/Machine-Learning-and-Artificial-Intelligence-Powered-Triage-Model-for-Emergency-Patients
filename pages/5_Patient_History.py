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
    """
    Uses AI to find patients matching a vague concept (e.g., 'Heart problems').
    """
    if not query: return df
    
    # 1. Prepare a list of ID + Complaints
    records = df[['id', 'complaint', 'clinical_summary']].to_dict(orient='records')
    records_str = "\n".join([f"ID {r['id']}: {r['complaint']} | {str(r.get('clinical_summary',''))}" for r in records])
    
    prompt = f"""
    You are a Medical Search Engine.
    User Query: "{query}"
    
    Database Records:
    {records_str}
    
    Task: Return ONLY a JSON list of IDs that clinically match the user's query.
    Example: [101, 104, 110]
    If no matches, return [].
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        content = response['message']['content']
        # Extract list from string (simple parsing)
        import json
        start = content.find('[')
        end = content.find(']') + 1
        return json.loads(content[start:end])
    except:
        return []

# ---------------------------------------------------------
# 1. LOAD DATA & HEADER
# ---------------------------------------------------------
all_patients = database.get_all_patients()

st.title("🗄️ Master Patient Index (MPI)")
st.caption("Central Registry for Clinical Audit, Coding, and Research.")

if all_patients.empty:
    st.warning("No records found.")
    st.stop()

# ---------------------------------------------------------
# 2. TABS FOR DIFFERENT VIEWS
# ---------------------------------------------------------
tab_registry, tab_analytics, tab_ai_query = st.tabs(["📋 Patient Registry", "📊 Population Health", "🤖 Semantic Query"])

# === TAB 1: TRADITIONAL REGISTRY (Refined) ===
with tab_registry:
    # Sidebar Filters (Scoped to this tab primarily)
    c_search, c_status = st.columns([2, 1])
    search_query = c_search.text_input("🔍 Quick Search (Name/ID/Complaint)", placeholder="Type to filter...")
    status_filter = c_status.multiselect("Status Filter", all_patients['status'].unique(), default=all_patients['status'].unique())
    
    # Apply Filters
    filtered_df = all_patients.copy()
    filtered_df = filtered_df[filtered_df['status'].isin(status_filter)]
    
    if search_query:
        filtered_df = filtered_df[
            filtered_df['name'].str.contains(search_query, case=False, na=False) | 
            filtered_df['complaint'].str.contains(search_query, case=False, na=False) |
            filtered_df['id'].astype(str).str.contains(search_query)
        ]

    # DATA TABLE
    st.dataframe(
        filtered_df[['id', 'arrival_time', 'name', 'age', 'gender', 'complaint', 'triage_level', 'status', 'final_disposition']],
        column_config={
            "id": st.column_config.NumberColumn("MRN", width="small"),
            "arrival_time": st.column_config.DatetimeColumn("Date", format="MMM DD, YY"),
            "triage_level": st.column_config.NumberColumn("KTAS", width="small"),
            "final_disposition": st.column_config.TextColumn("Outcome"),
        },
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun"
    )

# === TAB 2: ANALYTICS (Real-World Dashboarding) ===
with tab_analytics:
    st.markdown("### 📈 ED Performance & Clinical Trends")
    
    row1_1, row1_2 = st.columns(2)
    
    with row1_1:
        # Chart 1: Triage Acuity Distribution
        fig_acuity = px.bar(
            all_patients['triage_level'].value_counts().sort_index(), 
            title="Patient Volume by Triage Acuity (KTAS)",
            labels={'value': 'Count', 'index': 'KTAS Level'},
            color_discrete_sequence=['#1E88E5']
        )
        st.plotly_chart(fig_acuity, use_container_width=True)
        
    with row1_2:
        # Chart 2: Disposition / Outcomes
        # Handle missing disposition
        clean_disp = all_patients['final_disposition'].fillna('Unknown')
        fig_disp = px.pie(
            names=clean_disp.unique(), 
            values=clean_disp.value_counts(),
            title="Final Disposition Outcomes",
            hole=0.4
        )
        st.plotly_chart(fig_disp, use_container_width=True)

    # Chart 3: Age Distribution (Histogram)
    fig_age = px.histogram(
        all_patients, x="age", nbins=20, 
        title="Patient Demographics: Age Distribution",
        color_discrete_sequence=['#00C853']
    )
    st.plotly_chart(fig_age, use_container_width=True)

# === TAB 3: AI SEMANTIC QUERY (The FYP Feature) ===
with tab_ai_query:
    st.markdown("### 🤖 AI Cohort Builder")
    st.info("Use natural language to find patient groups based on clinical concepts, not just keywords.")
    
    col_ai_input, col_ai_btn = st.columns([4, 1])
    user_prompt = col_ai_input.text_input("Describe the cohort", placeholder="e.g. 'Patients with respiratory issues' or 'Trauma cases involving elderly'")
    
    if col_ai_btn.button("🔍 AI Search", type="primary"):
        with st.spinner("AI is analyzing clinical context..."):
            matched_ids = get_semantic_matches(all_patients, user_prompt)
            
            if matched_ids:
                st.success(f"✅ AI Identified {len(matched_ids)} patients matching criteria.")
                
                # Filter DataFrame to these IDs
                ai_results = all_patients[all_patients['id'].isin(matched_ids)]
                
                st.dataframe(
                    ai_results[['id', 'name', 'age', 'complaint', 'clinical_summary']],
                    column_config={
                        "clinical_summary": st.column_config.TextColumn("Clinical Context", width="large")
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("No clinically relevant matches found.")

# ---------------------------------------------------------
# FOOTER / EXPORT
# ---------------------------------------------------------
st.markdown("---")
c_open, c_export = st.columns([1, 4])

# Logic to open details from ANY tab selection (Streamlit State handling)
# Note: Streamlit dataframes selection states are widget-specific. 
# This is a generic handler if you select in Tab 1.
# (For a robust solution, you'd check selection state of the specific dataframe widget)

with c_export:
    csv = all_patients.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Export Registry to CSV", csv, "hospital_registry.csv", "text/csv")