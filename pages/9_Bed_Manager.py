import streamlit as st
import database
import pandas as pd
import time
import datetime

st.set_page_config(page_title="Bed Manager", page_icon="🛏️", layout="wide")

if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.switch_page("app.py")

# ---------------------------------------------------------
# AI HELPER: BED LOGIC
# ---------------------------------------------------------
def get_recommended_bed_type(triage_level, complaint):
    """
    Simple Rule-Based AI to suggest bed location based on acuity.
    In a full ML project, this could be a classifier model.
    """
    complaint = complaint.lower()
    if triage_level <= 2:
        return "ICU"
    elif "trauma" in complaint or "bleeding" in complaint:
        return "Emergency"
    else:
        return "Ward"

# ---------------------------------------------------------
# PAGE HEADER
# ---------------------------------------------------------
st.title("🛏️ Bed Management Command Center")
st.caption("AI-Assisted Patient Flow & Capacity Management")

# 1. METRICS
beds = database.get_all_beds()
total = len(beds)
occupied = len(beds[beds['status'] == 'Occupied'])
available = len(beds[beds['status'] == 'Available'])
dirty = len(beds[beds['status'] == 'Cleaning'])

# Occupancy Progress Bar (Visualizing Saturation)
occupancy_rate = int((occupied/total)*100)
st.progress(occupancy_rate / 100, text=f"Hospital Capacity: {occupancy_rate}% Full")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Beds", total)
c2.metric("Occupied", occupied, delta_color="inverse")
c3.metric("Available", available, delta="Ready for Admit", delta_color="normal")
c4.metric("Dirty / Cleaning", dirty, delta="Needs EVS", delta_color="off")

st.divider()

# 2. MAIN INTERFACE
col_left, col_right = st.columns([1, 2.5])

# --- LEFT COLUMN: INTELLIGENT WAITING LIST ---
with col_left:
    st.subheader("⏳ Waiting Room")
    waiting_df = database.get_waiting_patients()
    
    if not waiting_df.empty:
        st.info(f"{len(waiting_df)} patients waiting.")
        
        # Sort by Acuity (Sickest First - Real World Triage Logic)
        waiting_df = waiting_df.sort_values(by='triage_level', ascending=True)
        
        for idx, row in waiting_df.iterrows():
            # AI RECOMMENDATION LOGIC
            rec_dept = get_recommended_bed_type(row['triage_level'], row['complaint'])
            
            # Acuity Color
            acuity_color = {1: "#d32f2f", 2: "#f57c00", 3: "#fbc02d", 4: "#388e3c", 5: "#1976d2"}.get(row['triage_level'], "grey")
            
            with st.container(border=True):
                # Header with Color Strip
                st.markdown(f"<div style='border-left: 5px solid {acuity_color}; padding-left: 10px;'><b>{row['name']}</b> (KTAS {row['triage_level']})</div>", unsafe_allow_html=True)
                st.caption(f"Complaint: {row['complaint']}")
                
                # AI Suggestion Badge
                st.markdown(f"🤖 **AI Suggestion:** `{rec_dept}`")
                
                # Filter beds based on recommendation
                # We show recommended beds FIRST, then others
                free_beds = beds[beds['status'] == 'Available'].copy()
                
                if not free_beds.empty:
                    # Sort logic: Put recommended department at top of list
                    free_beds['is_rec'] = free_beds['department'] == rec_dept
                    free_beds = free_beds.sort_values(by=['is_rec', 'bed_label'], ascending=[False, True])
                    
                    # Create labels
                    bed_opts = free_beds.apply(lambda x: f"{'⭐ ' if x['is_rec'] else ''}{x['bed_label']} ({x['department']})", axis=1).tolist()
                    
                    bed_choice_label = st.selectbox("Assign Bed:", bed_opts, key=f"sel_{row['id']}", label_visibility="collapsed")
                    
                    # Parse selection to get ID
                    # Extract the bed label part "⭐ ICU-01 (ICU)" -> "ICU-01"
                    clean_label = bed_choice_label.replace("⭐ ", "").split(" (")[0]
                    
                    if st.button("Assign", key=f"btn_{row['id']}", type="primary", use_container_width=True):
                        bed_id = beds[beds['bed_label'] == clean_label].iloc[0]['id']
                        database.assign_patient_to_bed(bed_id, row['id'])
                        st.toast(f"Assigned {row['name']} to {clean_label}")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.error("No Available Beds!")
    else:
        st.success("Waiting room empty.")

# --- RIGHT COLUMN: INTERACTIVE BED TRACK BOARD ---
with col_right:
    c_head, c_filt = st.columns([2, 1])
    c_head.subheader("🏥 Live Track Board")
    
    # Filter by Department
    depts = ["All"] + list(beds['department'].unique())
    selected_dept = c_filt.selectbox("Filter Zone", depts)
    
    display_beds = beds if selected_dept == "All" else beds[beds['department'] == selected_dept]
    
    # GRID LAYOUT (4 Columns for higher density)
    cols = st.columns(4)
    
    for index, row in display_beds.iterrows():
        col = cols[index % 4]
        
        with col:
            status = row['status']
            
            # --- COLOR PALETTE (High Contrast) ---
            # We force color: #000 (Black) to ensure readability on the light backgrounds
            if status == 'Available':
                bg_color = "#d1e7dd"   # Mint Green
                border = "#0f5132"     # Dark Green
                title_col = "#0f5132"
                icon = "🟢"
                
                card_html = f"""
                <div style="background-color:{bg_color}; padding:10px; border-radius:8px; border:2px solid {border}; text-align:center; color:black;">
                    <h4 style="color:{title_col}; margin:0; padding:0;">{icon} {row['bed_label']}</h4>
                    <div style="font-size:12px; font-weight:bold;">{row['department']}</div>
                    <div style="margin-top:5px; font-style:italic;">Ready</div>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)
                
                if st.button("🛠️ Lock", key=f"maint_{row['id']}", help="Set to Maintenance"):
                    database.set_bed_status(row['id'], "Maintenance")
                    st.rerun()

            elif status == 'Occupied':
                bg_color = "#f8d7da"   # Pink/Red
                border = "#842029"     # Dark Red
                title_col = "#842029"
                icon = "🔴"
                
                # Truncate complaint for UI neatness
                comp_short = (row['complaint'][:15] + '..') if len(row['complaint']) > 15 else row['complaint']
                
                card_html = f"""
                <div style="background-color:{bg_color}; padding:10px; border-radius:8px; border:2px solid {border}; text-align:center; color:black;">
                    <h4 style="color:{title_col}; margin:0; padding:0;">{icon} {row['bed_label']}</h4>
                    <div style="font-weight:bold; font-size:13px; margin-top:5px;">{row['patient_name']}</div>
                    <div style="font-size:11px; color:#333;">{comp_short}</div>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)
                
                if st.button("📂 View", key=f"view_{row['id']}", type="secondary", use_container_width=True):
                    st.session_state['selected_patient_id'] = int(row['current_patient_id'])
                    st.switch_page("pages/4_Patient_Details.py")

            elif status == 'Cleaning':
                bg_color = "#fff3cd"   # Yellow/Orange
                border = "#664d03"     # Dark Brown
                title_col = "#664d03"
                icon = "🧹"
                
                card_html = f"""
                <div style="background-color:{bg_color}; padding:10px; border-radius:8px; border:2px solid {border}; text-align:center; color:black;">
                    <h4 style="color:{title_col}; margin:0; padding:0;">{icon} {row['bed_label']}</h4>
                    <div style="font-weight:bold; margin-top:5px;">Dirty</div>
                    <div style="font-size:11px;">Needs EVS</div>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)
                
                if st.button("✅ Clean", key=f"clean_{row['id']}", type="primary", use_container_width=True):
                    database.set_bed_status(row['id'], "Available")
                    st.rerun()

            else: # Maintenance
                bg_color = "#e2e3e5"   # Grey
                border = "#41464b"     # Dark Grey
                title_col = "#41464b"
                icon = "🔧"
                
                card_html = f"""
                <div style="background-color:{bg_color}; padding:10px; border-radius:8px; border:2px solid {border}; text-align:center; color:black;">
                    <h4 style="color:{title_col}; margin:0; padding:0;">{icon} {row['bed_label']}</h4>
                    <div style="font-size:12px;">Maintenance</div>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)
                
                if st.button("Activate", key=f"act_{row['id']}", use_container_width=True):
                    database.set_bed_status(row['id'], "Available")
                    st.rerun()