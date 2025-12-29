# pages/3_Staff_Directory.py
import streamlit as st
import database
import pandas as pd

st.set_page_config(page_title="Staff Directory", page_icon="📋")

# 1. AUTH CHECK
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ You must log in to access this page.")
    st.stop()

st.title("📋 Hospital Staff Directory")

# 2. FETCH DATA (Read Only)
# We use get_all_users() but we will hide the passwords
users_df = database.get_all_users()

if not users_df.empty:
    # Filter out the password column for general viewing
    public_view = users_df[['full_name', 'role', 'username']]
    
    # Rename columns for display
    public_view.columns = ["Name", "Role", "System Username"]

    # Tabs for organization
    tab1, tab2, tab3 = st.tabs(["Doctors", "Nurses", "Admins"])
    
    with tab1:
        st.dataframe(public_view[public_view['Role'] == "doctor"], hide_index=True, use_container_width=True)
    
    with tab2:
        st.dataframe(public_view[public_view['Role'] == "nurse"], hide_index=True, use_container_width=True)
        
    with tab3:
        st.dataframe(public_view[public_view['Role'] == "admin"], hide_index=True, use_container_width=True)

else:
    st.info("No staff found in database.")