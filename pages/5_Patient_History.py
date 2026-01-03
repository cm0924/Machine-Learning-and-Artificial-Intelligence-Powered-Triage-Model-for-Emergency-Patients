import streamlit as st
import pandas as pd
import database
import time
import plotly.express as px
import ollama
import re 
import json

# ---------------------------------------------------------
# SECURITY CHECK
# ---------------------------------------------------------
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

st.set_page_config(page_title="Master Patient Index", layout="wide", page_icon="🗄️")

# --- CUSTOM CSS FOR POLISH ---
st.markdown("""
<style>
    div[data-testid="stMetricValue"] {font-size: 24px;}
    .action-panel {
        background-color: var(--secondary-background-color);
        color: var(--text-color);
        padding: 20px;
        border-radius: 10px;
        border: 1px solid rgba(128, 128, 128, 0.2);
        margin-top: 20px;
    }
    /* Style for the selection checkbox column in dataframe */
    .stDataFrame > div > div > div > div[aria-colindex="1"] { 
        width: 50px !important; 
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# AI HELPER: SEMANTIC SEARCH
# ---------------------------------------------------------
def get_semantic_matches(df, query):
    if not query: return []
    records = df[['id', 'complaint', 'clinical_summary']].to_dict(orient='records')
    records_str = "\n".join([f"ID {r['id']}: {r['complaint']} | {str(r.get('clinical_summary',''))}" for r in records])
    
    prompt = f"""
    You are a Medical Search Engine.
    User Query: "{query}"
    Database Records: {records_str}
    Task: Return ONLY a JSON list of IDs that clinically match the user's query.
    Example: [101, 104, 110]
    Do not write any text outside the brackets.
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        content = response['message']['content']
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return []
    except Exception as e:
        print(f"AI Search Error: {e}")
        return []

# ---------------------------------------------------------
# HELPER: BULK DELETE DIALOG (CENTER SCREEN)
# ---------------------------------------------------------
@st.dialog("⚠️ Confirm Bulk Deletion")
def show_bulk_delete_dialog(ids_to_delete):
    count = len(ids_to_delete)
    st.warning(f"You are about to permanently delete **{count}** patient record(s).")
    st.write("This action cannot be undone.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚫 Cancel", use_container_width=True):
            st.rerun()
            
    with col2:
        if st.button("🗑️ Yes, Delete All", type="primary", use_container_width=True):
            success_count = 0
            fail_count = 0
            
            progress = st.progress(0)
            for i, pid in enumerate(ids_to_delete):
                if database.delete_patient(pid):
                    success_count += 1
                else:
                    fail_count += 1
                progress.progress((i + 1) / count)
                
            time.sleep(0.5)
            st.success(f"Deleted {success_count} records.")
            if fail_count > 0:
                st.error(f"Failed to delete {fail_count} records.")
            
            time.sleep(1)
            st.rerun()

# ---------------------------------------------------------
# 1. LOAD DATA
# ---------------------------------------------------------
all_patients = database.get_all_patients()

c_title, c_kpi = st.columns([3, 1], vertical_alignment="bottom")
with c_title:
    st.title("🗄️ Master Patient Index")
    st.caption("Central Registry for Clinical Audit, Coding, and Research.")

if all_patients.empty:
    st.warning("No records found in the database.")
    st.stop()

with c_kpi:
    st.metric("Total Records", len(all_patients), help="Total patient volume in DB")

# Variable to track selection across tabs
selected_patient_data = None

# ---------------------------------------------------------
# 2. TABS
# ---------------------------------------------------------
tab_registry, tab_analytics, tab_ai_query = st.tabs(["📋 Patient Registry", "📊 Population Health", "🤖 Semantic Query"])

# === TAB 1: REGISTRY (Standard Search) ===
with tab_registry:
    # Filter Row
    with st.container(border=True):
        # Adjusted columns to fit Acuity Filter: Search(2) | Acuity(1.5) | Status(1.5) | Delete(1)
        c_search, c_acuity, c_status, c_delete = st.columns([2, 1.5, 1.5, 1]) 
        
        # 1. Search Input
        search_query = c_search.text_input("🔍 Search", placeholder="Filter by Name, MRN, or Complaint...", label_visibility="collapsed")
        
        # 2. NEW: Acuity Filter
        # We default to all levels (1-5) selected
        acuity_options = [1, 2, 3, 4, 5]
        acuity_filter = c_acuity.multiselect(
            "Acuity", 
            acuity_options, 
            default=acuity_options, 
            format_func=lambda x: f"Level {x}", # Makes it look nice ("Level 1")
            label_visibility="collapsed", 
            placeholder="Filter Acuity"
        )

        # 3. Status Filter
        status_filter = c_status.multiselect("Status", all_patients['status'].unique(), default=all_patients['status'].unique(), label_visibility="collapsed", placeholder="Filter Status")
        
        # 4. Bulk Delete Button Placeholder
        delete_btn_placeholder = c_delete.empty()

    # --- FILTERING LOGIC ---
    filtered_df = all_patients.copy()
    
    # Apply Status Filter
    filtered_df = filtered_df[filtered_df['status'].isin(status_filter)]
    
    # Apply NEW Acuity Filter
    if acuity_filter:
        filtered_df = filtered_df[filtered_df['triage_level'].isin(acuity_filter)]
    
    # Apply Text Search
    if search_query:
        mask = (
            filtered_df['name'].str.contains(search_query, case=False, na=False) | 
            filtered_df['id'].astype(str).str.contains(search_query) |
            filtered_df['complaint'].str.contains(search_query, case=False, na=False)
        )
        filtered_df = filtered_df[mask]

    # Display Formatting (Visual Badges)
    def format_triage(val):
        if val == 1: return "🔴 Level 1"
        if val == 2: return "🟠 Level 2"
        if val == 3: return "🟡 Level 3"
        if val == 4: return "🟢 Level 4"
        return "🔵 Level 5"

    display_df = filtered_df.copy()
    display_df['triage_display'] = display_df['triage_level'].apply(format_triage)

    # DATAFRAME WITH MULTI-ROW SELECTION
    event_reg = st.dataframe(
        # Added 'complaint' to the list of columns
        display_df[['id', 'arrival_time', 'name', 'age', 'gender', 'complaint', 'triage_display', 'status', 'final_disposition']],
        column_config={
            "id": st.column_config.NumberColumn("MRN", width="small"),
            "arrival_time": st.column_config.DatetimeColumn("Date", format="MMM DD, YY - HH:mm"),
            # NEW CONFIGURATION FOR COMPLAINT
            "complaint": st.column_config.TextColumn("Chief Complaint", width="medium"), 
            "triage_display": st.column_config.TextColumn("Acuity", width="small"),
            "final_disposition": "Outcome"
        },
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key="registry_grid",
        height=500
    )
    
    # --- LOGIC TO MAP SELECTION TO IDs ---
    selected_indices = event_reg.selection.rows
    
    if selected_indices:
        ids_to_delete = display_df.iloc[selected_indices]['id'].tolist()
        
        # Render the Delete Button now that we have IDs
        if delete_btn_placeholder.button(f"🗑️ Delete ({len(ids_to_delete)})", type="secondary", use_container_width=True):
            show_bulk_delete_dialog(ids_to_delete)
        
        # If only 1 row selected, populate the "Selected Patient" variable for bottom panel
        if len(selected_indices) == 1:
            selected_patient_data = display_df.iloc[selected_indices[0]]
    else:
        # Disable button if nothing selected
        delete_btn_placeholder.button("🗑️ Delete Selected", type="secondary", disabled=True, use_container_width=True)

# === TAB 2: ANALYTICS ===
with tab_analytics:
    st.subheader("📈 Clinical Operations Overview")
    row1_1, row1_2 = st.columns(2)
    with row1_1:
        # 1. Prepare Data
        counts = all_patients['triage_level'].value_counts().reset_index()
        counts.columns = ['Level', 'Count']
        
        # CRITICAL FIX: Convert Level to String ('1', '2'...) 
        # This forces Plotly to use Discrete Mapping instead of a Continuous Gradient
        counts['Level_Str'] = counts['Level'].astype(str)

        # 2. Define Color Map (Keys must match the String values)
        triage_colors = {
            "1": "#d32f2f", # Red (Resuscitation)
            "2": "#f57c00", # Orange (Emergent)
            "3": "#fbc02d", # Yellow (Urgent)
            "4": "#388e3c", # Green (Less Urgent)
            "5": "#1976d2"  # Blue (Non Urgent)
        }
        
        # 3. Render Chart
        fig_acuity = px.bar(
            counts, 
            x='Level_Str', 
            y='Count', 
            title="Patient Volume by Acuity (KTAS)", 
            color='Level_Str',          # Use the String Column
            color_discrete_map=triage_colors, # Apply the colors
            text_auto=True,
            category_orders={"Level_Str": ["1", "2", "3", "4", "5"]} # Force order 1->5
        )
        
        # Clean up layout
        fig_acuity.update_layout(
            xaxis_title="KTAS Level", 
            yaxis_title="Encounters",
            showlegend=False # Hide legend as X-axis is self-explanatory
        )
        st.plotly_chart(fig_acuity, use_container_width=True)

    with row1_2:
        # 1. Create a Clean Summary Dataframe
        # This ensures the Label "LWBS" stays locked to the Count "1"
        clean_disp = all_patients['final_disposition'].fillna('Active/Unknown')
        disp_summary = clean_disp.value_counts().reset_index()
        disp_summary.columns = ['Disposition', 'Count']
        
        # 2. Render Chart using the DataFrame
        fig_disp = px.pie(
            disp_summary, 
            names='Disposition', 
            values='Count', 
            title="Clinical Outcomes / Disposition", 
            hole=0.4, 
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        
        # Optional: Show percentage and label text inside slices
        fig_disp.update_traces(textinfo='percent+label')
        
        st.plotly_chart(fig_disp, use_container_width=True)

# === TAB 3: AI QUERY ===
with tab_ai_query:
    c_desc, c_ex = st.columns([2, 1])
    c_desc.markdown("### 🤖 Semantic Cohort Search")
    c_desc.caption("Use natural language to find patients based on symptoms or history, even if keywords don't match exactly.")
    with st.container(border=True):
        col_ai_input, col_ai_btn = st.columns([5, 1], vertical_alignment="bottom")
        user_prompt = col_ai_input.text_input("Describe Cohort Criteria", placeholder="e.g. 'Elderly patients with respiratory issues'")
        if 'ai_results_ids' not in st.session_state: st.session_state.ai_results_ids = []
        if col_ai_btn.button("Run AI Query", type="primary", use_container_width=True):
            if not user_prompt: st.toast("⚠️ Please enter a query first.")
            else:
                with st.spinner("🧠 AI is analyzing clinical summaries..."):
                    st.session_state.ai_results_ids = get_semantic_matches(all_patients, user_prompt)
                    if not st.session_state.ai_results_ids: st.toast("No semantic matches found.", icon="ℹ️")
    if st.session_state.ai_results_ids:
        ai_df = all_patients[all_patients['id'].isin(st.session_state.ai_results_ids)].copy()
        st.info(f"✅ AI identified **{len(ai_df)} records** matching your criteria.")
        event_ai = st.dataframe(
            ai_df[['id', 'name', 'complaint', 'clinical_summary']],
            column_config={"id": st.column_config.NumberColumn("MRN", width="small"), "clinical_summary": st.column_config.TextColumn("AI Summary / Context", width="large")},
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="ai_grid",
            height=400
        )
        if len(event_ai.selection.rows) > 0:
            idx = event_ai.selection.rows[0]
            selected_patient_data = ai_df.iloc[idx]
    else:
        st.markdown("""
        <div style="background-color:#f8f9fa; padding:20px; border-radius:10px; text-align:center; color:#666;">
            👋 Enter a prompt above to build a patient cohort using Semantic Search.
        </div>
        """, unsafe_allow_html=True)

# ---------------------------------------------------------
# 3. CONTROL PANEL (Styled Action Bar)
# ---------------------------------------------------------
st.write("") # Spacer

if selected_patient_data is not None:
    pid = int(selected_patient_data['id'])
    pname = selected_patient_data['name']
    
    with st.container():
        st.markdown(f"""
        <div class="action-panel">
            <h4 style="margin:0; color:inherit;">🎯 Selected: {pname} <span style="opacity: 0.8; font-weight:normal; font-size:16px;">(MRN: {pid})</span></h4>
        </div>
        """, unsafe_allow_html=True)
        
        col_act1, col_act2, col_act3 = st.columns([1, 1, 3])
        
        with col_act1:
            if st.button("📂 Open Clinical Chart", type="primary", use_container_width=True):
                st.session_state['selected_patient_id'] = pid
                st.switch_page("pages/4_Patient_Details.py")
                
        with col_act2:
            st.download_button(
                "📥 Download Record CSV", 
                selected_patient_data.to_frame().to_csv(), 
                f"{pname}_record.csv", 
                "text/csv", 
                use_container_width=True
            )

# --- Always Visible Action/Admin Panel ---
st.markdown("---")
with st.expander("🛠️ Admin & Data Tools"):
    st.caption("Manage patient records, perform bulk actions, or export data.")
    
    st.download_button("📥 Export Full Database (CSV)", 
                       all_patients.to_csv(index=False), 
                       "hospital_db_full.csv", "text/csv", 
                       use_container_width=True)