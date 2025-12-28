# pages/3_Staff_Manager.py
import streamlit as st
import database
import pandas as pd
import time

if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

st.set_page_config(page_title="Staff Management", page_icon="🪪")

st.title("🪪 Staff Registry")
st.markdown("Register new healthcare providers here.")

# 1. ADD NEW STAFF FORM
with st.form("new_staff_form"):
    col1, col2 = st.columns(2)
    new_name = col1.text_input("Staff Name", placeholder="e.g. Dr. House")
    new_role = col2.selectbox("Role", ["ED MD", "ED NP/PA", "Nurse"])
    
    submitted = st.form_submit_button("Register Staff")
    
    if submitted and new_name:
        database.add_staff(new_name, new_role)
        st.success(f"✅ Added {new_role}: {new_name}")
        st.rerun()

st.divider()

# 2. VIEW STAFF LIST
st.subheader("Current Staff List")
staff_df = database.get_all_staff()

if not staff_df.empty:
    # Group by Role for cleaner view
    tab1, tab2, tab3 = st.tabs(["Doctors (MD)", "Mid-Levels (NP/PA)", "Nurses"])
    
    with tab1:
        st.dataframe(staff_df[staff_df['role'] == "ED MD"], hide_index=True, use_container_width=True)
    with tab2:
        st.dataframe(staff_df[staff_df['role'] == "ED NP/PA"], hide_index=True, use_container_width=True)
    with tab3:
        st.dataframe(staff_df[staff_df['role'] == "Nurse"], hide_index=True, use_container_width=True)
else:
    st.info("No staff registered yet.")