import streamlit as st
import pandas as pd
import database
import time

if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

st.set_page_config(page_title="Patient History", layout="wide", page_icon="📜")

st.title("📜 Master Patient Index (History)")
st.markdown("View and search all historical patient records.")

# ---------------------------------------------------------
# 1. LOAD DATA
# ---------------------------------------------------------
# This function gets EVERYONE (including discharged)
all_patients = database.get_all_patients()

if all_patients.empty:
    st.warning("No records found in the database.")
    st.stop()

# ---------------------------------------------------------
# 2. FILTERS (Sidebar)
# ---------------------------------------------------------
st.sidebar.header("🔍 Filter Records")

# Search by Name/ID
search_query = st.sidebar.text_input("Search Name or ID", placeholder="John Doe")

# Filter by Status
status_filter = st.sidebar.multiselect(
    "Filter by Status",
    options=all_patients['status'].unique(),
    default=all_patients['status'].unique()
)

# Filter by Triage Level
level_filter = st.sidebar.multiselect(
    "Filter by KTAS Level",
    options=[1, 2, 3, 4, 5],
    default=[1, 2, 3, 4, 5]
)

# --- APPLY FILTERS ---
filtered_df = all_patients.copy()

# 1. Name/ID Search
if search_query:
    filtered_df = filtered_df[
        filtered_df['name'].str.contains(search_query, case=False, na=False) | 
        filtered_df['id'].astype(str).str.contains(search_query)
    ]

# 2. Status & Level Filters
filtered_df = filtered_df[filtered_df['status'].isin(status_filter)]
filtered_df = filtered_df[filtered_df['triage_level'].isin(level_filter)]

# ---------------------------------------------------------
# 3. METRICS ROW
# ---------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Records", len(all_patients))
c2.metric("Showing", len(filtered_df))
c3.metric("Discharged", len(all_patients[all_patients['status'] == 'Discharged']))
c4.metric("Avg Confidence", f"{all_patients['confidence'].mean():.1f}%")

st.divider()

# ---------------------------------------------------------
# 4. MAIN DATA TABLE
# ---------------------------------------------------------
# Helper for color coding triage levels
def color_triage(val):
    colors = {1: '#ff4b4b', 2: '#ffa500', 3: '#fca311', 4: '#28a745', 5: '#007bff'}
    return f'color: {colors.get(val, "black")}; font-weight: bold'

# Configure columns for display
column_config = {
    "id": st.column_config.NumberColumn("ID", width="small"),
    "arrival_time": st.column_config.DatetimeColumn("Arrival Time", format="D MMM, h:mm a"),
    "name": st.column_config.TextColumn("Patient Name"),
    "triage_level": st.column_config.NumberColumn("Level", width="small"),
    "confidence": st.column_config.ProgressColumn("AI Conf.", format="%.1f%%", min_value=0, max_value=100),
    "status": st.column_config.SelectboxColumn("Status", width="medium", options=["Waiting", "In-Treatment", "Admitted", "Discharged"]),
    "nurse_notes": st.column_config.TextColumn("Notes", width="large")
}

# Display Table with Selection
st.subheader("🗃️ Patient Database")

event = st.dataframe(
    filtered_df[['id', 'arrival_time', 'name', 'gender', 'age', 'complaint', 'triage_level', 'confidence', 'status', 'nurse_notes']],
    column_config=column_config,
    use_container_width=True,
    hide_index=True,
    selection_mode="single-row",
    on_select="rerun",
    height=500
)

# ---------------------------------------------------------
# 5. ACTIONS (View Details & Export)
# ---------------------------------------------------------
st.markdown("---")
col_actions, col_export = st.columns([2, 1])

with col_actions:
    if len(event.selection.rows) > 0:
        selected_index = event.selection.rows[0]
        # Get ID from the FILTERED dataframe using iloc
        selected_id = filtered_df.iloc[selected_index]['id']
        patient_name = filtered_df.iloc[selected_index]['name']
        
        st.info(f"Selected: **{patient_name}** (ID: {selected_id})")
        
        if st.button("📂 Open Full Medical Record", type="primary"):
            st.session_state['selected_patient_id'] = int(selected_id)
            st.switch_page("pages/4_Patient_Details.py")
    else:
        st.caption("👆 Select a row to view details.")

with col_export:
    st.write("##") # Spacer
    # CSV Download Button (Crucial for "Records")
    csv = filtered_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Export Data as CSV",
        data=csv,
        file_name='hospital_records.csv',
        mime='text/csv',
        use_container_width=True
    )