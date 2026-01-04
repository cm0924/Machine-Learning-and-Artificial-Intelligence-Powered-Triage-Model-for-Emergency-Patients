import streamlit as st

# --- PAGE DEFINITIONS ---
# Define all your pages here using st.Page
login_page = st.Page("login.py", title="Log In", icon="🔒")

# Core Pages (Everyone sees these)
dashboard = st.Page("pages/1_Dashboard.py", title="Dashboard", icon="📊")
staff_dir = st.Page("pages/3_Staff_Command_Center.py", title="Staff Directory", icon="📇")
patient_ehr = st.Page("pages/5_Patient_History.py", title="Patient History", icon="📂")
bed_mgr = st.Page("pages/8_Bed_Manager.py", title="Bed Manager", icon="🛏️")

# Nurse Specific
triage_page = st.Page("pages/2_Triage.py", title="AI Triage", icon="🚑") # Assuming this exists
nurse_audit = st.Page("pages/6_Quality_Assurance.py", title="Performance", icon="📈")

# Admin Specific
admin_panel = st.Page("pages/7_System_Administration.py", title="Admin Panel", icon="🛡️")

# --- ROUTING LOGIC ---
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    # If not logged in, ONLY show the login page
    pg = st.navigation([login_page])
else:
    role = st.session_state.get("user_role", "guest").lower()
    
    # 1. DEFINE PAGE LISTS
    common_pages = [dashboard, staff_dir, patient_ehr, bed_mgr]
    
    # 2. BUILD NAVIGATION BASED ON ROLE
    if role == "admin":
        # Admin sees everything
        pg = st.navigation({
            "Management": [dashboard, admin_panel, nurse_audit],
            "Clinical Operations": [staff_dir, bed_mgr, patient_ehr],
            "Triage": [triage_page] # Admins usually can access triage for testing
        })
        
    elif role == "nurse":
        # Nurse sees Common + Triage + Audit
        pg = st.navigation({
            "Dashboard": [dashboard],
            "Workflows": [triage_page, patient_ehr, bed_mgr],
            "Resources": [staff_dir, nurse_audit]
        })
        
    elif role in ["doctor", "nppa", "provider"]:
        # Doctors see Common ONLY (Hidden: Triage, Admin, Audit)
        pg = st.navigation({
            "Dashboard": [dashboard],
            "Clinical Work": [patient_ehr, bed_mgr],
            "Resources": [staff_dir]
        })
        
    else:
        # Fallback for errors
        pg = st.navigation([login_page])

# --- RUN THE APP ---
st.set_page_config(page_title="Hospital AI System", layout="wide")
pg.run()