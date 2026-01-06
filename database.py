# database.py
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import random
import ollama  # Ensure ollama is installed and configured 
import face_recognition
import numpy as np
import pickle # To save the array as bytes
from PIL import Image


DB_NAME = "hospital.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Check if column exists, if not add it (Migration logic)
    c.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in c.fetchall()]
    if 'face_encoding' not in columns:
        print("Migrating DB: Adding face_encoding column...")
        c.execute("ALTER TABLE users ADD COLUMN face_encoding BLOB")

    # 1. PATIENTS TABLE (Updated with DOB and Clinical Fields)
    c.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            dob TEXT,               -- NEW: Date of Birth for identification
            age INTEGER,
            gender TEXT,
            
            -- Clinical Triage Data
            arrival_mode INTEGER,   -- 1:Ambulance, 2:Walk-in, 3:Transfer
            injury INTEGER,         -- 1:No, 2:Yes
            complaint TEXT,
            mental INTEGER,         -- 1:Alert, 2:Verbal, 3:Pain, 4:Unresponsive
            pain INTEGER,           -- 0:No, 1:Yes
            nrs_pain INTEGER,       -- 0-10 Scale
            
            -- Vitals
            sbp INTEGER,
            dbp INTEGER,
            hr INTEGER,
            rr INTEGER,
            bt REAL,
            saturation INTEGER,
            
            -- AI & Status
            triage_level INTEGER,   
            ai_level INTEGER,       
            confidence REAL,
            ai_explanation TEXT,
            nurse_notes TEXT,
            clinical_summary TEXT,  -- NEW: Dedicated column for the AI Paragraph  
            final_disposition TEXT,
            
            -- Staffing
            triage_nurse TEXT,
            assigned_md TEXT,
            assigned_nppa TEXT,
            assigned_nurse TEXT,
            
            arrival_time TIMESTAMP,
            status TEXT
        )
    ''')
    
    # 2. UNIFIED USERS TABLE
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            username TEXT UNIQUE,
            password TEXT, 
            role TEXT
        )
    ''')

    # 3. BEDS TABLE
    c.execute('''
        CREATE TABLE IF NOT EXISTS beds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bed_label TEXT UNIQUE,   -- e.g., "EME-01", "ICU-03"
            department TEXT,         -- "Emergency", "ICU", "Ward"
            status TEXT,             -- "Available", "Occupied", "Cleaning", "Maintenance"
            current_patient_id INTEGER, -- Links to patients table
            FOREIGN KEY(current_patient_id) REFERENCES patients(id)
        )
    ''')
    
    # --- MOCK DATA GENERATION ---
    
    # A. USERS
    c.execute("SELECT * FROM users")
    if not c.fetchone():
        print("Generating mock users...")
        staff_members = [
            ("System Admin", "admin", "admin123", "admin"),
            ("Nurse Joy", "nurse", "nurse123", "nurse"),
            ("Nora Roosevelt", "nora", "pass123", "nurse"),
            ("Sarah Connor", "sarah", "pass123", "nurse"),
            ("Dr. Gregory House", "dr_house", "vicodin", "doctor"),
            ("Dr. Meredith Grey", "dr_grey", "derrick", "doctor"),
            ("Dr. Stephen Strange", "dr_strange", "time", "doctor"),
            ("Peter Parker, PA-C", "peter", "web123", "nppa"), 
            ("Carol Danvers, NP", "carol", "hero123", "nppa")
        ]
        for name, user, pwd, role in staff_members:
            c.execute("INSERT INTO users (full_name, username, password, role) VALUES (?, ?, ?, ?)", 
                      (name, user, pwd, role))

        # # B. MOCK PATIENTS
        # print("Generating mock patients...")
        # nurse_usernames = ["nurse", "nora", "sarah"]
        
        # for i in range(50):
        #     nurse = random.choice(nurse_usernames)
        #     ai_lvl = random.choices([1, 2, 3, 4, 5], weights=[5, 15, 40, 30, 10])[0]
            
        #     # Logic: 80% Agreement
        #     if random.random() < 0.80: final_lvl = ai_lvl
        #     else: final_lvl = max(1, min(5, ai_lvl + random.choice([-1, 1])))
            
        #     disp = 'Discharge' if final_lvl > 3 else 'Admit'
            
        #     # Generate Random DOB based on Age
        #     age = random.randint(18, 90)
        #     birth_year = datetime.now().year - age
        #     dob_mock = f"{birth_year}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"

        #     c.execute('''
        #         INSERT INTO patients (name, dob, age, gender, complaint, triage_level, ai_level, 
        #         confidence, triage_nurse, final_disposition, arrival_time, status, 
        #         arrival_mode, injury, mental, pain, nrs_pain)
        #         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        #     ''', (
        #         f"Patient {i+100}", dob_mock, age, "Male", "Mock Complaint", 
        #         final_lvl, ai_lvl, 88.5, nurse, disp, 
        #         datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Discharged",
        #         2, 1, 1, 0, 0 # Default safe values for mock data
        #     ))

    # C. BEDS (100 BEDS LOGIC)
    c.execute("SELECT count(*) FROM beds")
    if c.fetchone()[0] == 0:
        print("Generating 100 mock beds...")
        departments = [
            ("Emergency", 20), 
            ("ICU", 30),       
            ("Ward", 50)       
        ]
        
        for dept, count in departments:
            for i in range(1, count + 1):
                label = f"{dept[:3].upper()}-{i:02d}" 
                c.execute("INSERT INTO beds (bed_label, department, status) VALUES (?, ?, ?)", 
                          (label, dept, "Available"))

    conn.commit()
    conn.close()

# --- DELETION FUNCTIONS ---

def delete_patient(patient_id):
    """
    Deletes a single patient and ensures any bed they occupy is freed.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        pid = int(patient_id)
        
        # 1. Free the bed if they are currently occupying one
        c.execute("UPDATE beds SET status='Available', current_patient_id=NULL WHERE current_patient_id=?", (pid,))
        
        # 2. Delete the patient record
        c.execute("DELETE FROM patients WHERE id=?", (pid,))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting patient: {e}")
        return False
    finally:
        conn.close()

def delete_all_patients():
    """
    DANGER: Wipes the entire patient database and resets all beds.
    Used for 'Hard Reset'.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        # 1. Reset ALL Beds to Available
        c.execute("UPDATE beds SET status='Available', current_patient_id=NULL")
        
        # 2. Delete ALL Patients
        c.execute("DELETE FROM patients")
        
        # 3. Optional: Reset the Auto-Increment ID counter to 1
        c.execute("DELETE FROM sqlite_sequence WHERE name='patients'")
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting all patients: {e}")
        return False
    finally:
        conn.close()    

# --- LOGIN & USER MANAGEMENT ---
# 2. FUNCTION TO REGISTER FACE
def register_face(user_id, image_buffer):
    try:
        # 1. Load with Pillow
        img = Image.open(image_buffer)
        
        # 2. Convert to RGB
        img = img.convert('RGB')
        
        # 3. Create Numpy Array (uint8)
        img_array = np.array(img, dtype=np.uint8)
        
        # 4. CRITICAL: Make memory contiguous (Fixes some Dlib reading errors)
        img_array = np.ascontiguousarray(img_array)
        
        # Debug info
        print(f"DEBUG: Processing Image. Shape: {img_array.shape}, Dtype: {img_array.dtype}")
        
        # 5. Encode
        encodings = face_recognition.face_encodings(img_array)
        
        if len(encodings) > 0:
            face_data = encodings[0]
            face_blob = pickle.dumps(face_data)
            
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("UPDATE users SET face_encoding = ? WHERE id = ?", (face_blob, user_id))
            conn.commit()
            conn.close()
            return True, "✅ Face ID enrolled successfully!"
        else:
            return False, "⚠️ No face detected. Adjust lighting and try again."
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False, f"System Error: {str(e)}"

# In database.py

def login_with_face(image_buffer):
    """
    Returns: success (bool), role (str), username (str), message_or_name (str)
    """
    try:
        img = Image.open(image_buffer)
        img = img.convert('RGB')
        unknown_image = np.array(img)
        
        unknown_encodings = face_recognition.face_encodings(unknown_image)
        
        # ERROR 1: No Face Found
        if len(unknown_encodings) == 0:
            # Return 4 values, putting the error message in the last slot
            return False, None, None, "⚠️ No face detected. Ensure your face is visible."
            
        unknown_encoding = unknown_encodings[0]

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT id, role, full_name, username, face_encoding FROM users WHERE face_encoding IS NOT NULL")
        users = c.fetchall()
        conn.close()

        for u_id, role, name, username, face_blob in users:
            try:
                known_encoding = pickle.loads(face_blob)
                results = face_recognition.compare_faces([known_encoding], unknown_encoding, tolerance=0.5)
                
                if results[0]:
                    # SUCCESS: Return Name in the last slot
                    return True, role, username, name 
            except:
                continue
        
        # ERROR 2: Face Found, but not in DB
        return False, None, None, "❌ Face not recognized. Access Denied."
        
    except Exception as e:
        # ERROR 3: System Crash
        return False, None, None, f"System Error: {str(e)}"
    
def verify_login(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Fetch full_name along with role
    c.execute("SELECT role, full_name FROM users WHERE username = ? AND password = ?", (username, password))
    result = c.fetchone()
    conn.close()
    
    if result:
        # result[0] is role, result[1] is full_name
        return True, result[0], result[1] 
    else:
        return False, None, None

def get_full_name_by_username(username):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT full_name FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    if result:
        return result[0]
    return "Unknown Staff"

def get_all_users():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT id, full_name, username, password, role FROM users", conn)
    conn.close()
    return df

def get_staff_by_role(role):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT full_name FROM users WHERE role = ?", conn, params=(role,))
    conn.close()
    return df['full_name'].tolist()

def add_user(full_name, username, password, role):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (full_name, username, password, role) VALUES (?, ?, ?, ?)", 
                  (full_name, username, password, role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_user(user_id, full_name, username, password, role):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET full_name=?, username=?, password=?, role=? WHERE id=?", 
              (full_name, username, password, role, user_id))
    conn.commit()
    conn.close()

def delete_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

# --- PATIENT FUNCTIONS ---

def add_patient(name, dob, age, gender, arrival_mode, injury, complaint, 
                mental, pain, nrs_pain, sbp, dbp, hr, rr, bt, saturation,
                final_level, ai_level, conf, explanation, notes, triage_nurse, status="Waiting"):
    """Updated to include DOB and detailed triage fields."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO patients (
            name, dob, age, gender, arrival_mode, injury, complaint,
            mental, pain, nrs_pain, sbp, dbp, hr, rr, bt, saturation,
            triage_level, ai_level, confidence, ai_explanation, nurse_notes, triage_nurse, arrival_time, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        name, dob, age, gender, arrival_mode, injury, complaint,
        mental, pain, nrs_pain, sbp, dbp, hr, rr, bt, saturation,
        int(final_level), int(ai_level), float(conf), explanation, notes, triage_nurse, now, status
    ))
    conn.commit()
    conn.close()

def get_all_patients():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT * FROM patients ORDER BY arrival_time DESC", conn)
    conn.close()
    return df

def get_patient_by_id(patient_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row 
    c = conn.cursor()
    c.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
    row = c.fetchone()
    conn.close()
    if row: return dict(row)
    return None

# Updated to include DOB in the arguments and SQL query
def update_full_patient_record(patient_id, name, dob, age, gender, complaint, 
                               arrival_mode, injury, mental, pain, nrs_pain,
                               sbp, dbp, hr, rr, bt, sat, 
                               triage_level, md, nppa, nurse, notes, 
                               summary=None): 
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Added dob=? to the SET clause
    c.execute('''
        UPDATE patients 
        SET name=?, dob=?, age=?, gender=?, complaint=?, 
            arrival_mode=?, injury=?, mental=?, pain=?, nrs_pain=?, 
            sbp=?, dbp=?, hr=?, rr=?, bt=?, saturation=?, 
            triage_level=?, assigned_md=?, assigned_nppa=?, assigned_nurse=?, nurse_notes=?,
            clinical_summary = COALESCE(?, clinical_summary)
        WHERE id=?
    ''', (
        name, dob, age, gender, complaint, 
        arrival_mode, injury, mental, pain, nrs_pain,
        sbp, dbp, hr, rr, bt, sat, 
        triage_level, md, nppa, nurse, notes, 
        summary, 
        patient_id
    ))
    conn.commit()
    conn.close()

def get_patient_history(name, dob=None):
    """
    Fetches past visits. 
    If DOB is provided, it uses strict NAME + DOB matching (Real World Safety).
    If DOB is None, it falls back to Name only (Legacy support).
    """
    conn = sqlite3.connect(DB_NAME)
    try:
        if dob:
            df = pd.read_sql("SELECT * FROM patients WHERE name = ? AND dob = ? ORDER BY arrival_time DESC", 
                             conn, params=(name, dob))
        else:
            df = pd.read_sql("SELECT * FROM patients WHERE name = ? ORDER BY arrival_time DESC", 
                             conn, params=(name,))
    except Exception as e:
        print(f"Error fetching history: {e}")
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

# --- BED & TREATMENT WORKFLOW FUNCTIONS ---

def get_all_beds():
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT b.id, b.bed_label, b.department, b.status, b.current_patient_id, p.name as patient_name, p.complaint
        FROM beds b
        LEFT JOIN patients p ON b.current_patient_id = p.id
        ORDER BY b.bed_label
    '''
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def get_waiting_patients():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT id, name, triage_level, complaint FROM patients WHERE status = 'Waiting'", conn)
    conn.close()
    return df

def assign_patient_to_bed(bed_id, patient_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("UPDATE beds SET status='Occupied', current_patient_id=? WHERE id=?", (patient_id, bed_id))
        c.execute("UPDATE patients SET status='Admitted' WHERE id=?", (patient_id,))
        conn.commit()
        return True
    except Exception as e:
        print(e)
        return False
    finally:
        conn.close()

def clear_bed(bed_id, patient_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE beds SET status='Cleaning', current_patient_id=NULL WHERE id=?", (bed_id,))
    conn.commit()
    conn.close()

def set_bed_status(bed_id, status):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE beds SET status=? WHERE id=?", (status, bed_id))
    conn.commit()
    conn.close()

def get_available_beds_list():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT id, bed_label, department FROM beds WHERE status='Available'", conn)
    conn.close()
    return df

def get_patient_bed(patient_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        # --- FIX: FORCE INT CASTING ---
        pid = int(patient_id) 
        
        c.execute("SELECT bed_label FROM beds WHERE current_patient_id=?", (pid,))
        row = c.fetchone()
        
        return row[0] if row else "Waiting Room"
    except Exception as e:
        print(f"Error fetching bed: {e}")
        return "Waiting Room"
    finally:
        conn.close()

def start_treatment_detailed(patient_id, md, nppa, nurse, bed_id, notes, author_username="System"):
    """
    Transitions patient to 'In-Treatment' and logs the Start Note with Author ID.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        pid = int(patient_id)
        
        # 1. Get Author's Real Name
        # We try to find the full name, otherwise fallback to the username
        c.execute("SELECT full_name, role FROM users WHERE username = ?", (author_username,))
        row = c.fetchone()
        if row:
            author_display = f"{row[0]} ({row[1].title()})"
        else:
            author_display = author_username

        # 2. Format the Log Entry
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # This creates the timeline block
        structured_note = f"\n\n{'='*30}\n[{timestamp}] 🚀 ENCOUNTER STARTED\n👤 Activated by: {author_display}\n📝 HPI/Note: {notes}\n{'='*30}"
        
        # 3. Update Patient Record
        c.execute('''
            UPDATE patients 
            SET status='In-Treatment', 
                assigned_md=?, 
                assigned_nppa=?, 
                assigned_nurse=?, 
                nurse_notes = COALESCE(nurse_notes, '') || ?
            WHERE id=?
        ''', (md, nppa, nurse, structured_note, pid))
        
        # 4. Assign Bed (If selected)
        if bed_id:
            c.execute("UPDATE beds SET status='Occupied', current_patient_id=? WHERE id=?", (pid, bed_id))
        
        conn.commit()
        return True

    except Exception as e:
        print(f"Error starting treatment: {e}")
        return False
    finally:
        conn.close()

def discharge_patient(patient_id):
    """Simple discharge (updates status only)."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE patients SET status = 'Discharged' WHERE id = ?", (patient_id,))
    conn.commit()
    conn.close()

def get_available_staff(role):
    """
    Returns a list of staff members who are NOT currently assigned 
    to any active patient.
    
    Logic: Staff is BUSY if patient is 'In-Treatment' or 'Waiting'.
    Staff is FREE if patient is 'Discharged' OR 'Admitted' (moved to Ward/ICU).
    """
    conn = sqlite3.connect(DB_NAME)
    
    # 1. Get ALL staff for this role
    df_all = pd.read_sql("SELECT full_name FROM users WHERE role = ?", conn, params=(role,))
    all_staff = set(df_all['full_name'].dropna().tolist())
    
    # 2. Get BUSY staff
    column_map = {
        "doctor": "assigned_md",
        "nurse": "assigned_nurse",
        "nppa":   "assigned_nppa"
    }
    
    target_col = column_map.get(role)
    busy_staff = set()

    if target_col:
        # UPDATED QUERY:
        # We check for patients who are NOT Discharged AND NOT Admitted.
        # If they are 'Admitted', they have left the ER, so the staff is free.
        query = f"""
            SELECT DISTINCT {target_col} 
            FROM patients 
            WHERE status NOT IN ('Discharged', 'Admitted') 
            AND {target_col} IS NOT NULL 
            AND {target_col} != ''
        """
        df_busy = pd.read_sql(query, conn)
        busy_staff = set(df_busy[target_col].dropna().tolist())
        
    conn.close()
    
    # 3. Subtract Busy from All
    available_staff = list(all_staff - busy_staff)
    available_staff.sort()
    
    return available_staff

def transfer_patient(patient_id, new_bed_id, reason="Clinical Update", author_username="System"):
    """
    Moves patient to new bed AND updates status based on Department (Smart Admission).
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        pid = int(patient_id)
        
        # 1. Get Author info
        c.execute("SELECT full_name, role FROM users WHERE username = ?", (author_username,))
        row_user = c.fetchone()
        author_display = f"{row_user[0]} ({row_user[1].title()})" if row_user else author_username

        # 2. Get Old Bed Info
        c.execute("SELECT bed_label, department FROM beds WHERE current_patient_id = ?", (pid,))
        row = c.fetchone()
        old_bed_label = row[0] if row else "Waiting Room"
        
        # 3. Get New Bed Info AND Department
        c.execute("SELECT bed_label, department FROM beds WHERE id = ?", (new_bed_id,))
        row_new = c.fetchone()
        if not row_new: return False
        
        new_bed_label = row_new[0]
        new_dept = row_new[1] # e.g., 'ICU', 'Ward', 'Emergency'

        # --- SMART STATUS LOGIC ---
        # If moving to ICU or Ward, they are technically "Admitted"
        if new_dept in ['ICU', 'Ward']:
            new_status = 'Admitted'
            # Also update final_disposition to reflect this
            disposition_note = f"Admitted to {new_dept}"
            c.execute("UPDATE patients SET final_disposition = ? WHERE id = ?", (disposition_note, pid))
        else:
            new_status = 'In-Treatment' # Stay active if in ER

        # 4. Swap Beds
        # Free old bed
        c.execute("UPDATE beds SET status='Cleaning', current_patient_id=NULL WHERE current_patient_id=?", (pid,))
        # Occupy new bed
        c.execute("UPDATE beds SET status='Occupied', current_patient_id=? WHERE id=?", (pid, new_bed_id))
        
        # 5. Update Patient Log & Status
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_entry = f"\n\n[{timestamp}] ⚠️ TRANSFER: {old_bed_label} -> {new_bed_label} ({new_dept})\n👤 Authorized by: {author_display}\nReason: {reason}\nStatus Update: {new_status}"
        
        c.execute("""
            UPDATE patients 
            SET status=?, 
                nurse_notes = COALESCE(nurse_notes, '') || ? 
            WHERE id=?
        """, (new_status, log_entry, pid))

        conn.commit()
        return True

    except Exception as e:
        print(f"Error transferring patient: {e}")
        return False
    finally:
        conn.close()

def generate_illness_script_internal(patient_dict, logs):
    """
    Internal helper for database.py to generate summary.
    """
    prompt = f"""
    Act as a Doctor. Write a 1-paragraph Clinical Synopsis for:
    Patient: {patient_dict['name']} ({patient_dict['age']} {patient_dict['gender']})
    Complaint: {patient_dict['complaint']}
    Notes: {logs}
    Task: Summarize diagnosis, treatment, and outcome in 3 sentences.
    """
    try:
        response = ollama.chat(model='gemini-3-flash-preview:cloud', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
    except Exception as e:
        return "Summary unavailable."

def discharge_patient_and_free_bed(patient_id, disposition="Home"):
    """
    Finalizes the ER visit.
    disposition: 'Home', 'Admit', 'ICU', 'Transfer', 'AMA'
    """
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row 
    c = conn.cursor()
    
    try:
        pid = int(patient_id)
        
        # 1. Fetch data for AI Summary
        c.execute("SELECT * FROM patients WHERE id = ?", (pid,))
        patient_data = c.fetchone()
        
        if not patient_data: return False

        p_dict = dict(patient_data)
        
        # 2. Generate Summary (Pass the disposition to AI so it knows context)
        notes = p_dict.get('nurse_notes', '')
        # (Optional: Append outcome to notes for AI context)
        context_notes = f"{notes}\n[Outcome: {disposition}]"
        summary_text = generate_illness_script_internal(p_dict, context_notes)
        
        # 3. UPDATE: Set Status to 'Discharged' (from ER perspective)
        # BUT set 'final_disposition' to the specific outcome (Admit/ICU/Home)
        c.execute("""
            UPDATE patients 
            SET status='Discharged', 
                final_disposition=?, 
                clinical_summary = ? 
            WHERE id=?
        """, (disposition, summary_text, pid))
        
        # 4. Free the Bed
        c.execute("SELECT id FROM beds WHERE current_patient_id=?", (pid,))
        row = c.fetchone()
        if row:
            bed_id = row[0]
            c.execute("UPDATE beds SET status='Cleaning', current_patient_id=NULL WHERE id=?", (bed_id,))
        
        conn.commit()
        return True

    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        conn.close()

def get_staff_status_report():
    """
    Returns staff status, location, AND total patient count (workload).
    """
    conn = sqlite3.connect(DB_NAME)
    
    # 1. Get All Staff
    staff_df = pd.read_sql("SELECT full_name, role, username FROM users", conn)
    
    # 2. Get All Patients (Active & Discharged) for Workload Stats
    p_df = pd.read_sql("SELECT assigned_md, assigned_nppa, assigned_nurse, status, name, id FROM patients", conn)
    
    # 3. Get Active Bed Mapping (For Location)
    b_df = pd.read_sql("SELECT current_patient_id, bed_label FROM beds WHERE current_patient_id IS NOT NULL", conn)
    
    conn.close()
    
    # --- PROCESSING LOGIC ---
    status_map = {}
    location_map = {}
    
    # A. Calculate Workload (Count total assignments regardless of status)
    all_assignments = pd.concat([p_df['assigned_md'], p_df['assigned_nppa'], p_df['assigned_nurse']])
    counts = all_assignments.value_counts().to_dict()
    
    # B. Calculate Active Status
    # UPDATED LOGIC: 
    # A patient is only "Active" (making staff busy) if they are NOT Discharged AND NOT Admitted.
    active_patients = p_df[~p_df['status'].isin(['Discharged', 'Admitted'])]
    
    # Create a map of Patient ID -> Bed Label
    bed_map = dict(zip(b_df['current_patient_id'], b_df['bed_label']))
    
    for idx, row in active_patients.iterrows():
        # Find Bed
        pid = row['id']
        loc_txt = bed_map.get(pid, "Waiting Room")
        status_txt = f"Busy ({row['name']})"
        
        # Assign to map
        for role_col in ['assigned_md', 'assigned_nppa', 'assigned_nurse']:
            staff_name = row[role_col]
            if staff_name:
                status_map[staff_name] = status_txt
                location_map[staff_name] = loc_txt

    # C. Apply to Main DataFrame
    def get_status(name): return status_map.get(name, "Available")
    def get_location(name): return location_map.get(name, "Staff Lounge")
    def get_workload(name): return counts.get(name, 0)

    staff_df['Status'] = staff_df['full_name'].apply(get_status)
    staff_df['Location'] = staff_df['full_name'].apply(get_location)
    staff_df['Patients Seen'] = staff_df['full_name'].apply(get_workload)
    
    return staff_df            

# Initialize on run
init_db()