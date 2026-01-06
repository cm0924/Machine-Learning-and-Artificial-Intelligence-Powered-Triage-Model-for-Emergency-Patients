import streamlit as st
import time
import database

# 1. SETUP PAGE
st.set_page_config(
    page_title="MediCore Login", 
    page_icon="🏥", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- PROFESSIONAL STYLING (CSS) ---
st.markdown("""
<style>
    /* 1. HIDE DEFAULT STREAMLIT ELEMENTS */
    [data-testid="stSidebar"] {display: none;}
    [data-testid="collapsedControl"] {display: none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* 2. BACKGROUND COLOR (Soft Medical Grey) */
    .stApp {
        background-color: #e8eaed;
    }

    /* 3. LOGIN CARD STYLING (Force White Background + Dark Text) */
    /* This targets the container with the border */
    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        background-color: #ffffff !important;
        border: 1px solid #d1d5db !important;
        border-radius: 12px !important;
        box-shadow: 0 10px 25px rgba(0,0,0,0.05) !important;
        padding: 2rem !important;
    }

    /* 4. FORCE TEXT VISIBILITY (Fix for Dark Mode Users) */
    h1, h2, h3, h4, h5, p, span, div, label {
        color: #1f2937 !important; /* Dark Grey Text */
    }
    
    /* 5. INPUT FIELDS (Clean Borders) */
    div[data-testid="stTextInput"] input {
        background-color: #f9fafb !important;
        border: 1px solid #d1d5db !important;
        color: #111827 !important; /* Dark Text inside inputs */
        border-radius: 6px;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: #2563eb !important; /* Blue focus */
    }

    /* 6. BUTTON STYLING */
    div[data-testid="stButton"] button {
        width: 100%;
        border-radius: 6px;
        font-weight: 600;
        height: 45px;
    }
    
    /* 7. TABS STYLING */
    div[data-testid="stTabs"] button {
        font-weight: bold;
        color: #4b5563 !important;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: #2563eb !important; /* Active Tab Blue */
        border-bottom-color: #2563eb !important;
    }
</style>
""", unsafe_allow_html=True)

# 2. INITIALIZE SESSION STATE
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'username' not in st.session_state: st.session_state.username = None

# 3. LOGIN FLOW
if not st.session_state.logged_in:
    
    # --- LAYOUT: CENTERED CARD ---
    col_l, col_main, col_r = st.columns([1, 8, 1])
    
    with col_main:
        # We use a container to wrap the login logic visually
        with st.container(border=True):
            
            # HEADER
            c_logo, c_title = st.columns([1.5, 5], vertical_alignment="center")
            with c_logo:
                st.markdown("<div style='font-size: 40px; text-align:center;'>🏥</div>", unsafe_allow_html=True)
            with c_title:
                st.markdown("<h3 style='margin:0; padding:0;'>MediCore</h3>", unsafe_allow_html=True)
                st.markdown("<p style='font-size:14px; margin:0; color:#6b7280 !important;'>Secure Clinical Access Portal</p>", unsafe_allow_html=True)
            
            st.markdown("<hr style='margin: 15px 0; border-top: 1px solid #e5e7eb;'>", unsafe_allow_html=True)

            # --- TABS ---
            tab_pass, tab_face = st.tabs(["🔑 Password Access", "👤 Face ID"])

            # === TAB 1: PASSWORD LOGIN ===
            with tab_pass:
                with st.form("login_form", clear_on_submit=True):
                    st.write("") # Spacer
                    username = st.text_input("Username", placeholder="Enter System ID")
                    password = st.text_input("Password", type="password", placeholder="••••••••")
                    
                    st.write("") # Spacer
                    submitted = st.form_submit_button("🔒 Login", type="primary")
                    
                    # In login.py (Tab 1: Password Login)

                    if submitted:
                        with st.spinner("Verifying Credentials..."):
                            time.sleep(0.8)
                            
                            # Now unpacking 3 values!
                            is_valid, role, full_name = database.verify_login(username, password)
                            
                            if is_valid:
                                st.session_state.logged_in = True
                                st.session_state.user_role = role
                                st.session_state.username = username
                                st.session_state.full_name = full_name # <--- Store it here!
                                
                                st.success(f"Welcome, {full_name}!") # Nice touch
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error("❌ Authentication Failed: Invalid ID or Password.")

            # === TAB 2: BIOMETRIC LOGIN ===
            with tab_face:
                st.markdown(
                    """
                    <div style="text-align: center; color: #4b5563 !important; font-size: 14px; margin-bottom: 15px;">
                        Position your face within the frame.<br>Ensure proper lighting for accurate scanning.
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
                # Camera Input
                img_buffer = st.camera_input("Biometric Scanner", label_visibility="collapsed")
                
                # In login.py (Tab 2: Face ID Section)

                if img_buffer is not None:
                    with st.spinner("Processing Biometric Data..."):
                        
                        # Unpack the 4 values
                        # result_msg will be the Name (if success) OR the Error Message (if fail)
                        success, role, username, result_msg = database.login_with_face(img_buffer)
                        
                        if success:
                            st.session_state.logged_in = True
                            st.session_state.user_role = role
                            st.session_state.username = username
                            st.session_state.full_name = result_msg # result_msg is the Name here
                            
                            st.success(f"✅ Identity Verified: {result_msg}")
                            time.sleep(1)
                            st.rerun()
                        else:
                            # If failed, result_msg contains "No face detected" or "Access Denied"
                            st.error(result_msg) 
                            # Optional: Add a button to retry or just let them take another picture

    # --- FOOTER ---
    st.markdown("""
        <div style="text-align: center; margin-top: 40px; color: #6b7280 !important; font-size: 11px;">
            Authorized Use Only • MediCore Systems 🔒<br>
            Unauthorized access is a violation of hospital policy and applicable laws.
        </div>
    """, unsafe_allow_html=True)

# If already logged in, redirect immediately
else:
    st.switch_page("pages/1_Dashboard.py")