# pages/2_Admin_Panel.py
import streamlit as st
import database
import pandas as pd

st.set_page_config(page_title="Admin Panel", page_icon="🔐", layout="wide")

# --- SECURITY CHECK ---
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.warning("Please log in first.")
    st.stop()

if st.session_state.user_role != "admin":
    st.error("⛔ ACCESS DENIED: Only Admins can view this page.")
    st.stop()

st.title("🔐 Staff Management")

# Fetch latest data
users_df = database.get_all_users()

# --- TABS FOR CRUD OPERATIONS ---
tab1, tab2, tab3 = st.tabs(["📝 View & Edit", "➕ Add New Staff", "❌ Delete Staff"])

# =========================================================
# TAB 1: VIEW & UPDATE (The Editable Table)
# =========================================================
with tab1:
    st.markdown("### Staff Directory")
    st.info("💡 **Tip:** Double-click on any cell below to edit it. Changes save immediately.")

    # We use data_editor for inline editing
    # We hide the index, but we need the 'id' to map changes back to the DB
    edited_df = st.data_editor(
        users_df,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "full_name": "Full Name",
            "username": "Username",
            "password": "Password", 
            "role": st.column_config.SelectboxColumn("Role", options=["admin", "doctor", "nurse"])
        },
        disabled=["id"], # ID cannot be changed
        hide_index=True,
        use_container_width=True,
        key="editor"
    )

    # CHECK FOR CHANGES
    # Streamlit doesn't automatically sync data_editor back to SQL. 
    # We have to compare the old DF vs new DF or use a button to save.
    # Here is a "Save Changes" button approach for safety.
    
    if st.button("💾 Save Changes to Database", type="primary"):
        # Iterate through the edited dataframe rows
        try:
            for index, row in edited_df.iterrows():
                # We update every row (or you could optimize to only update changed ones)
                database.update_user(
                    user_id=row['id'],
                    full_name=row['full_name'],
                    username=row['username'],
                    password=row['password'],
                    role=row['role']
                )
            st.success("✅ Database updated successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Error updating database: {e}")

# =========================================================
# TAB 2: CREATE (Add New User)
# =========================================================
with tab2:
    st.markdown("### Register New Staff")
    
    with st.form("add_user_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input("Full Name")
            new_role = st.selectbox("Role", ["doctor", "nurse", "admin"])
        with col2:
            new_user = st.text_input("Username")
            new_pass = st.text_input("Password", type="password")
            
        submitted = st.form_submit_button("➕ Create User")
        
        if submitted:
            if new_name and new_user and new_pass:
                success = database.add_user(new_name, new_user, new_pass, new_role)
                if success:
                    st.success(f"✅ User {new_user} created!")
                    st.rerun()
                else:
                    st.error("❌ Username already exists. Please choose another.")
            else:
                st.warning("⚠️ Please fill in all fields.")

# =========================================================
# TAB 3: DELETE
# =========================================================
with tab3:
    st.markdown("### Remove Staff")
    st.warning("⚠️ This action cannot be undone.")
    
    # Create a list of "ID: Name (Role)" for the dropdown
    user_options = {f"{row['id']}: {row['full_name']} ({row['role']})": row['id'] for index, row in users_df.iterrows()}
    
    selected_option = st.selectbox("Select User to Remove", options=list(user_options.keys()))
    
    if st.button("🗑️ Delete User", type="primary"):
        user_id_to_delete = user_options[selected_option]
        
        # Prevent deleting yourself (optional safety)
        # Note: In a real app, you'd check session_state username against the DB
        
        database.delete_user(user_id_to_delete)
        st.success("User deleted.")
        st.rerun()

st.subheader("📸 Face ID Enrollment")

# Select User to Enroll
users = database.get_all_users()
user_map = {f"{row['full_name']} ({row['role']})": row['id'] for i, row in users.iterrows()}
target_user = st.selectbox("Select Staff Member", list(user_map.keys()))

# Camera Input
img_file = st.camera_input("Take a clear photo for enrollment")

if img_file is not None:
    if st.button("💾 Save Face ID"):
        user_id = user_map[target_user]
        success, msg = database.register_face(user_id, img_file)
        if success:
            st.success(msg)
        else:
            st.error(msg)        