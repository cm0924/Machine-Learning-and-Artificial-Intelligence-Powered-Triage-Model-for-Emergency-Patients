# pages/9_Bed_Manager.py
import streamlit as st
import database
import pandas as pd
import time

st.set_page_config(page_title="Bed Manager", page_icon="🛏️", layout="wide")

if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.switch_page("app.py")

st.title("🛏️ Bed Management Dashboard")

# 1. METRICS
beds = database.get_all_beds()
total = len(beds)
occupied = len(beds[beds['status'] == 'Occupied'])
available = len(beds[beds['status'] == 'Available'])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Beds", total)
c2.metric("Occupied", occupied)
c3.metric("Available", available, delta_color="normal")
c4.metric("Occupancy Rate", f"{int((occupied/total)*100)}%")

st.divider()

# 2. BED ASSIGNMENT INTERFACE
col_left, col_right = st.columns([1, 2])

# --- LEFT COLUMN: WAITING ROOM ---
with col_left:
    st.subheader("⏳ Waiting Room")
    waiting_df = database.get_waiting_patients()
    
    if not waiting_df.empty:
        st.info(f"{len(waiting_df)} patients waiting for a bed.")
        
        # Display each waiting patient as a small card
        for idx, row in waiting_df.iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['name']}** (Level {row['triage_level']})")
                st.caption(f"{row['complaint']}")
                
                # Assign Button
                # We need to pick a free bed
                free_beds = beds[beds['status'] == 'Available']
                if not free_beds.empty:
                    bed_choice = st.selectbox(
                        "Assign to:", 
                        free_beds['bed_label'].tolist(), 
                        key=f"sel_{row['id']}"
                    )
                    
                    if st.button("Assign", key=f"btn_{row['id']}", type="primary"):
                        # Get bed ID
                        bed_id = free_beds[free_beds['bed_label'] == bed_choice].iloc[0]['id']
                        database.assign_patient_to_bed(bed_id, row['id'])
                        st.success(f"Assigned to {bed_choice}")
                        time.sleep(0.5)
                        st.rerun()
                else:
                    st.error("No beds available!")
    else:
        st.success("Waiting room is empty.")

# --- RIGHT COLUMN: BED GRID ---
with col_right:
    st.subheader("🏥 Bed Status Map")
    
    # Filter by Department
    depts = beds['department'].unique()
    selected_dept = st.pills("Filter Department", depts, selection_mode="single")
    
    display_beds = beds if not selected_dept else beds[beds['department'] == selected_dept]
    
    # Create a Grid Layout
    cols = st.columns(3) # 3 Beds per row
    
    for index, row in display_beds.iterrows():
        col = cols[index % 3]
        
        with col:
            # Color logic
            if row['status'] == 'Available':
                border_color = "green"
                icon = "🟢"
            elif row['status'] == 'Occupied':
                border_color = "red"
                icon = "🔴"
            else: # Cleaning/Maintenance
                border_color = "orange"
                icon = "🧹"
            
            with st.container(border=True):
                st.markdown(f"### {icon} {row['bed_label']}")
                st.caption(row['department'])
                
                if row['status'] == 'Occupied':
                    st.markdown(f"**Patient:** {row['patient_name']}")
                    st.markdown(f"**Issue:** {row['complaint']}")
                    if st.button("Discharge/Transfer", key=f"dis_{row['id']}"):
                        database.clear_bed(row['id'], row['current_patient_id'])
                        st.rerun()
                
                elif row['status'] == 'Available':
                    st.markdown("*Empty*")
                    if st.button("Set Maintenance", key=f"maint_{row['id']}"):
                        database.set_bed_status(row['id'], "Maintenance")
                        st.rerun()
                        
                else: # Cleaning/Maintenance
                    st.warning(f"Status: {row['status']}")
                    if st.button("Mark Ready", key=f"cln_{row['id']}"):
                        database.set_bed_status(row['id'], "Available")
                        st.rerun()