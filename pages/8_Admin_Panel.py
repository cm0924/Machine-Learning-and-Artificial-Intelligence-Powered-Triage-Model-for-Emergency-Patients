# pages/2_Admin_Panel.py
import streamlit as st
import database
import pandas as pd
import time

st.set_page_config(page_title="Admin Panel", page_icon="🔐", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; padding-top: 10px; }
</style>
""", unsafe_allow_html=True)

# --- SECURITY CHECK ---
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("⚠️ Please log in first.")
    time.sleep(1)
    st.switch_page("app.py")
    st.stop()

if st.session_state.user_role != "admin":
    st.error("⛔ ACCESS DENIED: Only System Admins can view this page.")
    st.stop()

st.title("🔐 System Administration")
st.caption(f"Logged in as: {st.session_state.username}")

# Fetch latest data
users_df = database.get_all_users()

# --- TABS FOR CRUD OPERATIONS ---
t1, t2, t3, t4 = st.tabs(["📝 Directory & Edit", "➕ Register Staff", "📸 Face ID Setup", "❌ Remove Staff"])

# =========================================================
# TAB 1: VIEW & UPDATE (The Editable Table)
# =========================================================
with t1:
    st.subheader("Staff Directory")
    
    # --- FILTERS & SORTING ---
    with st.container(border=True):
        c_search, c_filter = st.columns([2, 1])
        
        with c_search:
            search_query = st.text_input("🔍 Search Staff", placeholder="Name or Username...")
            
        with c_filter:
            all_roles = list(users_df['role'].unique())
            role_filter = st.multiselect("Filter by Role", options=all_roles, default=all_roles, placeholder="Select roles...")

    # --- APPLY FILTERS ---
    filtered_df = users_df.copy()
    
    # 1. Role Filter
    if role_filter:
        filtered_df = filtered_df[filtered_df['role'].isin(role_filter)]
        
    # 2. Text Search
    if search_query:
        mask = (
            filtered_df['full_name'].str.contains(search_query, case=False) | 
            filtered_df['username'].str.contains(search_query, case=False)
        )
        filtered_df = filtered_df[mask]

    # 3. Default Sort (By Role then Name)
    filtered_df = filtered_df.sort_values(by=['role', 'full_name'])

    st.info(f"Showing **{len(filtered_df)}** records. Double-click any cell to edit.")

    # --- EDITOR ---
    # We use data_editor for inline editing
    edited_df = st.data_editor(
        filtered_df,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "full_name": "Full Name",
            "username": "Username",
            "password": "Password", 
            "role": st.column_config.SelectboxColumn("Role", options=["admin", "doctor", "nurse", "nppa"])
        },
        disabled=["id"], 
        hide_index=True,
        use_container_width=True,
        key="editor"
    )

    col_save, col_spacer = st.columns([1, 4])
    with col_save:
        if st.button("💾 Save Changes", type="primary", use_container_width=True):
            try:
                # We iterate through the EDITED dataframe (which contains the ID)
                # This works even if filtered, because the ID remains correct.
                for index, row in edited_df.iterrows():
                    database.update_user(
                        user_id=row['id'],
                        full_name=row['full_name'],
                        username=row['username'],
                        password=row['password'],
                        role=row['role']
                    )
                st.toast("✅ Database updated successfully!", icon="💾")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Error updating database: {e}")

# =========================================================
# TAB 2: CREATE (Add New User)
# =========================================================
with t2:
    st.subheader("Register New Staff Member")
    
    with st.container(border=True):
        with st.form("add_user_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                new_name = st.text_input("Full Name (e.g., Dr. Strange)")
                new_role = st.selectbox("Assign Role", ["doctor", "nurse", "nppa"])
            with c2:
                new_user = st.text_input("Username")
                new_pass = st.text_input("Default Password", type="password")
                
            st.markdown("---")
            submitted = st.form_submit_button("➕ Create User", type="primary", use_container_width=True)
            
            if submitted:
                if new_name and new_user and new_pass:
                    # Database Call
                    success = database.add_user(new_name, new_user, new_pass, new_role)
                    if success:
                        st.success(f"✅ User '{new_user}' created successfully!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Username already exists. Please choose another.")
                else:
                    st.warning("⚠️ Please fill in all fields.")

# =========================================================
# TAB 3: FACE ID (Clean Setup)
# =========================================================
with t3:
    st.subheader("📸 Biometric Enrollment")
    st.caption("Enroll staff faces for touchless login.")
    
    col_cam, col_sel = st.columns([1, 1])
    
    with col_sel:
        # Create a dropdown map of users sorted alphabetically
        # Using a sorted list for better UX
        sorted_users = users_df.sort_values(by="full_name")
        user_map = {f"{row['full_name']} ({row['role']})": row['id'] for i, row in sorted_users.iterrows()}
        
        target_user_label = st.selectbox("Select Staff Member to Enroll", list(user_map.keys()))
        target_user_id = user_map[target_user_label]
        
        st.info("1. Select the staff member above.\n2. Look at the camera.\n3. Click 'Take Photo'.\n4. Click 'Save Face ID'.")

    with col_cam:
        img_buffer = st.camera_input("Capture Face")

        if img_buffer is not None:
            if st.button("💾 Save Face ID to Database", type="primary", use_container_width=True):
                with st.spinner("Processing biometric data..."):
                    success, msg = database.register_face(target_user_id, img_buffer)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)

# =========================================================
# TAB 4: DELETE
# =========================================================
with t4:
    st.subheader("Remove Access")
    
    with st.container(border=True):
        st.warning("⚠️ DANGER ZONE: This action cannot be undone.")
        
        # Create list for dropdown sorted by name
        sorted_users = users_df.sort_values(by="full_name")
        user_options = {f"{row['id']}: {row['full_name']} ({row['role']})": row['id'] for index, row in sorted_users.iterrows()}
        
        selected_option = st.selectbox("Select User to Remove", options=list(user_options.keys()))
        
        if st.button("🗑️ Permanently Delete User", type="primary"):
            user_id_to_delete = user_options[selected_option]
            
            # Prevent Admin Suicide (Deleting the logged-in admin)
            current_admin_id = users_df[users_df['username'] == st.session_state.username]['id'].values[0]
            
            if user_id_to_delete == current_admin_id:
                st.error("⛔ You cannot delete your own Admin account.")
            else:
                database.delete_user(user_id_to_delete)
                st.toast("User deleted.", icon="🗑️")
                time.sleep(1)
                st.rerun()