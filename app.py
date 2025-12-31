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
    /* Optional: Center the camera widget */
    div[data-testid="stCameraInput"] {
        text-align: center;
        margin: 0 auto;
    }
</style>
""", unsafe_allow_html=True)

# 2. INITIALIZE SESSION STATE
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'username' not in st.session_state:
    st.session_state.username = None

# 3. LOGIN LOGIC
if not st.session_state.logged_in:
    st.title("🏥 EHR System Login")
    
    # Header Image
    col_logo, col_text = st.columns([1, 4])
    with col_logo:
        st.image("https://cdn-icons-png.flaticon.com/512/3063/3063176.png", width=80)
    with col_text:
        st.markdown("### Secure Access Portal")
        st.caption("Please authenticate using your credentials or biometrics.")

    st.write("---")

    # --- TABS FOR LOGIN METHOD ---
    tab_pass, tab_face = st.tabs(["🔑 Password Login", "📸 Face ID"])

    # === TAB 1: TRADITIONAL PASSWORD ===
    with tab_pass:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            
            if st.form_submit_button("Login", type="primary", use_container_width=True):
                is_valid, role = database.verify_login(username, password)
                
                if is_valid:
                    st.session_state.logged_in = True
                    st.session_state.user_role = role
                    st.session_state.username = username
                    st.success(f"Welcome back, {username}!")
                    time.sleep(0.5)
                    st.switch_page("pages/1_Dashboard.py")
                else:
                    st.error("Invalid Username or Password")
            
            st.caption("Default: **nurse** / **admin**")

    # === TAB 2: FACIAL RECOGNITION (SNAPSHOT) ===
    with tab_face:
        st.markdown("##### 👤 Biometric Scan")
        st.caption("Look directly at the camera and click 'Take Photo'.")
        
        # Simple, Stable Camera Input
        img_buffer = st.camera_input("Scan Face", label_visibility="collapsed")
        
        if img_buffer is not None:
            with st.spinner("Verifying Biometrics..."):
                # Call the function in database.py
                # Returns: (Success_Bool, Role, Username/ErrorMsg)
                success, role, result_data = database.login_with_face(img_buffer)
                
                if success:
                    st.session_state.logged_in = True
                    st.session_state.user_role = role
                    st.session_state.username = result_data # result_data is username on success
                    
                    st.success(f"✅ Face Recognized! Welcome, {result_data}.")
                    time.sleep(1)
                    st.switch_page("pages/1_Dashboard.py")
                else:
                    # result_data is Error Message on failure
                    st.error(f"❌ Access Denied: {result_data}")
                    st.caption("Tip: Ensure good lighting and look straight ahead.")

# If already logged in, redirect immediately
else:
    st.switch_page("pages/1_Dashboard.py")