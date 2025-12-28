# app.py
import streamlit as st
import time
import database

# 1. SETUP PAGE & HIDE SIDEBAR INITIALLY
st.set_page_config(page_title="Hospital System", page_icon="🏥", layout="centered")

# --- CSS TO HIDE SIDEBAR ON LOGIN PAGE ---
st.markdown("""
<style>
    [data-testid="stSidebar"] {
        display: none;
    }
    [data-testid="collapsedControl"] {
        display: none;
    }
</style>
""", unsafe_allow_html=True)

# 2. INITIALIZE SESSION STATE
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None

# 3. LOGIN LOGIC
if not st.session_state.logged_in:
    st.title("🏥 Triage System Login")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image("https://cdn-icons-png.flaticon.com/512/3063/3063176.png", width=150)
    
    with col2:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if st.button("Login", type="primary"):
            is_valid, role = database.verify_login(username, password)
            
            if is_valid:
                st.session_state.logged_in = True
                st.session_state.user_role = role
                st.success(f"Welcome back, {username}!")
                time.sleep(0.5)
                # Redirect to Dashboard
                st.switch_page("pages/1_Dashboard.py")
            else:
                st.error("Invalid Username or Password")
        
        st.info("Default Login: **nurse** / **admin**")

# If already logged in, redirect immediately
else:
    st.switch_page("pages/1_Dashboard.py")