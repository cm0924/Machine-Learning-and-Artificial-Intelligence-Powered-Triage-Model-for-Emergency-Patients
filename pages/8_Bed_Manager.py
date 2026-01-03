import streamlit as st
import database
import pandas as pd
import time
import datetime

st.set_page_config(page_title="Bed Manager", page_icon="🛏️", layout="wide")

# --- CUSTOM STYLING (Simple & Clean) ---
st.markdown("""
<style>
    /* Card Style */
    .bed-card {
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        color: #000;
    }
    .bed-title { font-size: 18px; font-weight: bold; margin-bottom: 5px; }
    .bed-status { font-size: 12px; opacity: 0.8; }
    
    /* Status Colors */
    .status-free    { background-color: #d4edda; border: 2px solid #28a745; } /* Green */
    .status-busy    { background-color: #f8d7da; border: 2px solid #dc3545; } /* Red */
    .status-dirty   { background-color: #fff3cd; border: 2px solid #ffc107; } /* Yellow */
    .status-fix     { background-color: #e2e3e5; border: 2px solid #6c757d; } /* Grey */
    
    div[data-testid="stMetricValue"] { font-size: 26px; }
</style>
""", unsafe_allow_html=True)

if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.switch_page("app.py")

# ---------------------------------------------------------
# AI HELPER: SUGGEST BED TYPE
# ---------------------------------------------------------
def get_bed_suggestion(triage_level, complaint):
    complaint = complaint.lower()
    # Critical patients go to ICU
    if triage_level <= 2:
        return "ICU"
    # Trauma/Breathing issues go to Emergency Beds
    elif any(x in complaint for x in ["trauma", "bleeding", "accident", "fall", "breath"]):
        return "Emergency"
    # Everyone else goes to General Ward
    else:
        return "Ward"

# ---------------------------------------------------------
# PAGE HEADER
# ---------------------------------------------------------
st.title("🛏️ Bed Manager")
st.caption("Manage Hospital Capacity and Cleanliness")

# 1. SIMPLE METRICS
beds = database.get_all_beds()
total = len(beds)
occupied = len(beds[beds['status'] == 'Occupied'])
available = len(beds[beds['status'] == 'Available'])
dirty = len(beds[beds['status'] == 'Cleaning'])

# Progress Bar
percent_full = int((occupied/total)*100) if total > 0 else 0
st.progress(percent_full / 100, text=f"**Hospital is {percent_full}% Full**")

with st.container(border=True):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Beds", total)
    c2.metric("Occupied", occupied, delta_color="inverse")
    c3.metric("Available", available, delta="Ready", delta_color="normal")
    c4.metric("Needs Cleaning", dirty, delta="Dirty", delta_color="off")

st.write("") # Spacer

# 2. MAIN LAYOUT
col_left, col_right = st.columns([1, 2.8])

# --- LEFT: WAITING LIST ---
with col_left:
    st.subheader("⏳ Waiting for Bed")
    waiting_df = database.get_waiting_patients()
    
    if not waiting_df.empty:
        st.write(f"**{len(waiting_df)}** patients waiting.")
        
        # Sort so sickest patients appear first
        waiting_df = waiting_df.sort_values(by='triage_level', ascending=True)
        
        for idx, row in waiting_df.iterrows():
            # Get Suggestion
            suggestion = get_bed_suggestion(row['triage_level'], row['complaint'])
            
            # Simple Card for Patient
            with st.container(border=True):
                st.markdown(f"**{row['name']}** (Level {row['triage_level']})")
                st.caption(f"Issue: {row['complaint']}")
                
                # AI Suggestion
                st.info(f"🤖 Suggested: **{suggestion}**")
                
                # Find available beds in that department
                free_beds = beds[beds['status'] == 'Available'].copy()
                
                if not free_beds.empty:
                    # Put suggested beds at the top
                    free_beds['is_match'] = free_beds['department'] == suggestion
                    free_beds = free_beds.sort_values(by=['is_match', 'bed_label'], ascending=[False, True])
                    
                    # Create simple labels for dropdown
                    options = free_beds.apply(lambda x: f"{'⭐ ' if x['is_match'] else ''}{x['bed_label']} ({x['department']})", axis=1).tolist()
                    
                    choice = st.selectbox("Assign to:", options, key=f"sel_{row['id']}", label_visibility="collapsed")
                    
                    # Clean the label string to get the name (Remove "⭐ " and "(Dept)")
                    bed_name = choice.replace("⭐ ", "").split(" (")[0]
                    
                    if st.button("✅ Confirm Assignment", key=f"btn_{row['id']}", type="primary", use_container_width=True):
                        # Find the ID of the bed
                        bed_id = beds[beds['bed_label'] == bed_name].iloc[0]['id']
                        # Update Database
                        database.assign_patient_to_bed(bed_id, row['id'])
                        st.toast(f"Assigned {row['name']} to {bed_name}")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.error("No Available Beds")
    else:
        st.success("No patients waiting.")

# --- RIGHT: BED STATUS VIEW ---
with col_right:
    c_h, c_f = st.columns([3, 1])
    c_h.subheader("🏥 Bed Status View")
    
    # Simple Filter
    depts = ["All Departments"] + list(beds['department'].unique())
    filter_choice = c_f.selectbox("Filter", depts, label_visibility="collapsed")
    
    # Apply Filter
    if filter_choice == "All Departments":
        display_beds = beds
    else:
        display_beds = beds[beds['department'] == filter_choice]
    
    # Grid Layout (4 Columns)
    cols = st.columns(4)
    
    for index, row in display_beds.iterrows():
        col = cols[index % 4]
        
        with col:
            status = row['status']
            
            # --- CARD DISPLAY LOGIC ---
            
            # 1. AVAILABLE (Green)
            if status == 'Available':
                st.markdown(f"""
                <div class="bed-card status-free">
                    <div class="bed-title">{row['bed_label']}</div>
                    <div class="bed-status">🟢 Available</div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button("Lock", key=f"lock_{row['id']}", use_container_width=True):
                    database.set_bed_status(row['id'], "Maintenance")
                    st.rerun()

            # 2. OCCUPIED (Red)
            elif status == 'Occupied':
                # Shorten long names/complaints
                short_complaint = (row['complaint'][:15] + '..') if len(str(row['complaint'])) > 15 else row['complaint']
                
                st.markdown(f"""
                <div class="bed-card status-busy">
                    <div class="bed-title">{row['bed_label']}</div>
                    <div style="font-weight:bold;">{row['patient_name']}</div>
                    <div class="bed-status">{short_complaint}</div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button("📂 Open Chart", key=f"open_{row['id']}", type="primary", use_container_width=True):
                    st.session_state['selected_patient_id'] = int(row['current_patient_id'])
                    st.switch_page("pages/4_Patient_Details.py")

            # 3. CLEANING (Yellow)
            elif status == 'Cleaning':
                st.markdown(f"""
                <div class="bed-card status-dirty">
                    <div class="bed-title">{row['bed_label']}</div>
                    <div style="font-weight:bold;">Dirty</div>
                    <div class="bed-status">Needs Cleaning</div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button("✅ Mark Clean", key=f"clean_{row['id']}", use_container_width=True):
                    database.set_bed_status(row['id'], "Available")
                    st.rerun()

            # 4. MAINTENANCE (Grey)
            else: 
                st.markdown(f"""
                <div class="bed-card status-fix">
                    <div class="bed-title">{row['bed_label']}</div>
                    <div class="bed-status">🔧 Maintenance</div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button("Unlock", key=f"unlock_{row['id']}", use_container_width=True):
                    database.set_bed_status(row['id'], "Available")
                    st.rerun()