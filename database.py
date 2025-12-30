# database.py
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import random
import ollama  # Ensure ollama is installed and configured 

DB_NAME = "hospital.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
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

        # B. MOCK PATIENTS
        print("Generating mock patients...")
        nurse_usernames = ["nurse", "nora", "sarah"]
        
        for i in range(50):
            nurse = random.choice(nurse_usernames)
            ai_lvl = random.choices([1, 2, 3, 4, 5], weights=[5, 15, 40, 30, 10])[0]
            
            # Logic: 80% Agreement
            if random.random() < 0.80: final_lvl = ai_lvl
            else: final_lvl = max(1, min(5, ai_lvl + random.choice([-1, 1])))
            
            disp = 'Discharge' if final_lvl > 3 else 'Admit'
            
            # Generate Random DOB based on Age
            age = random.randint(18, 90)
            birth_year = datetime.now().year - age
            dob_mock = f"{birth_year}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"

            c.execute('''
                INSERT INTO patients (name, dob, age, gender, complaint, triage_level, ai_level, 
                confidence, triage_nurse, final_disposition, arrival_time, status, 
                arrival_mode, injury, mental, pain, nrs_pain)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"Patient {i+100}", dob_mock, age, "Male", "Mock Complaint", 
                final_lvl, ai_lvl, 88.5, nurse, disp, 
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Discharged",
                2, 1, 1, 0, 0 # Default safe values for mock data
            ))

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

# --- LOGIN & USER MANAGEMENT ---

def verify_login(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE username = ? AND password = ?", (username, password))
    result = c.fetchone()
    conn.close()
    if result: return True, result[0]
    return False, None

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

# Update the function signature and SQL
def update_full_patient_record(patient_id, name, age, gender, complaint, 
                               arrival_mode, injury, mental, pain, nrs_pain,
                               sbp, dbp, hr, rr, bt, sat, 
                               triage_level, md, nppa, nurse, notes, 
                               summary=None): # <-- NEW ARGUMENT
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # We use COALESCE to keep the old summary if the new one is None
    c.execute('''
        UPDATE patients 
        SET name=?, age=?, gender=?, complaint=?, 
            arrival_mode=?, injury=?, mental=?, pain=?, nrs_pain=?, 
            sbp=?, dbp=?, hr=?, rr=?, bt=?, saturation=?, 
            triage_level=?, assigned_md=?, assigned_nppa=?, assigned_nurse=?, nurse_notes=?,
            clinical_summary = COALESCE(?, clinical_summary)  -- <-- NEW UPDATE LOGIC
        WHERE id=?
    ''', (
        name, age, gender, complaint, 
        arrival_mode, injury, mental, pain, nrs_pain,
        sbp, dbp, hr, rr, bt, sat, 
        triage_level, md, nppa, nurse, notes, 
        summary, # <-- Pass the summary here
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

def start_treatment_detailed(patient_id, md, nppa, nurse, bed_id, notes):
    """Transitions patient to 'In-Treatment' with full team assignment."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        # --- FIX: FORCE CAST TO PYTHON INTEGER ---
        # Pandas often sends numpy.int64 which SQLite dislikes
        pid = int(patient_id)
        
        # Prepare the note text
        new_note = f"\n\n[Treatment Started]: {notes}"
        
        # 1. ATOMIC UPDATE
        c.execute('''
            UPDATE patients 
            SET status='In-Treatment', 
                assigned_md=?, 
                assigned_nppa=?, 
                assigned_nurse=?, 
                nurse_notes = COALESCE(nurse_notes, '') || ?
            WHERE id=?
        ''', (md, nppa, nurse, new_note, pid))
        
        # Check if any row was actually updated
        if c.rowcount == 0:
            print(f"⚠️ Warning: Update failed for ID {pid}.")
            
            # --- DEBUGGING: SHOW WHAT IDS ACTUALLY EXIST ---
            c.execute("SELECT id FROM patients ORDER BY id DESC LIMIT 5")
            recent_ids = [row[0] for row in c.fetchall()]
            print(f"ℹ️ Debug: The most recent IDs in the DB are: {recent_ids}")
            return False

        # 2. Assign Bed (If selected)
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
    
    Logic: Total Staff - Staff assigned to Active Patients = Available Staff
    """
    conn = sqlite3.connect(DB_NAME)
    
    # 1. Get ALL staff for this role
    # We use 'set' for faster mathematical subtraction
    df_all = pd.read_sql("SELECT full_name FROM users WHERE role = ?", conn, params=(role,))
    all_staff = set(df_all['full_name'].dropna().tolist())
    
    # 2. Get BUSY staff
    # We look at patients who are NOT discharged.
    column_map = {
        "doctor": "assigned_md",
        "nurse": "assigned_nurse",
        "nppa":   "assigned_nppa"
    }
    
    target_col = column_map.get(role)
    busy_staff = set()

    if target_col:
        # Query: Find names in the assigned column where status is NOT Discharged
        query = f"""
            SELECT DISTINCT {target_col} 
            FROM patients 
            WHERE status != 'Discharged' 
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

# ---------------------------------------------------------
# ADD THESE FUNCTIONS TO database.py
# ---------------------------------------------------------

def transfer_patient(patient_id, new_bed_id):
    """
    Moves a patient from their current bed to a new bed.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        # FIX: Force Integer Cast
        pid = int(patient_id)
        
        # 1. Find the Old Bed (if exists) and mark it Dirty
        c.execute("SELECT id FROM beds WHERE current_patient_id = ?", (pid,))
        row = c.fetchone()
        
        if row:
            old_bed_id = row[0]
            c.execute("UPDATE beds SET status='Cleaning', current_patient_id=NULL WHERE id=?", (old_bed_id,))
        
        # 2. Occupy the New Bed
        c.execute("UPDATE beds SET status='Occupied', current_patient_id=? WHERE id=?", (pid, new_bed_id))
        
        # 3. Ensure Patient Status is correct
        c.execute("UPDATE patients SET status='In-Treatment' WHERE id=?", (pid,))

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

def discharge_patient_and_free_bed(patient_id):
    """
    Discharges patient, frees bed, and auto-generates AI History Summary.
    """
    conn = sqlite3.connect(DB_NAME)
    # FIX 1: Use Row Factory so we can access columns by name (['name'] instead of [1])
    conn.row_factory = sqlite3.Row 
    c = conn.cursor()
    
    try:
        # FIX 2: Force Integer Cast to prevent "Not Found" error
        pid = int(patient_id)
        
        # 1. Fetch the full patient record BEFORE discharging
        c.execute("SELECT * FROM patients WHERE id = ?", (pid,))
        patient_data = c.fetchone()
        
        if not patient_data:
            print(f"Error: Patient ID {pid} not found for discharge.")
            return False

        # Convert Row to Dict for the AI Helper
        p_dict = dict(patient_data)
        
        # 2. Generate the Clinical Summary
        notes = p_dict.get('nurse_notes', '')
        summary_text = generate_illness_script_internal(p_dict, notes)
        
        # 3. Update Patient (Set Discharged + Save Summary)
        c.execute("""
            UPDATE patients 
            SET status='Discharged', final_disposition='Home', clinical_summary = ? 
            WHERE id=?
        """, (summary_text, pid))
        
        # 4. Find Bed & Mark Dirty
        c.execute("SELECT id FROM beds WHERE current_patient_id=?", (pid,))
        row = c.fetchone()
        
        if row:
            bed_id = row[0]
            c.execute("UPDATE beds SET status='Cleaning', current_patient_id=NULL WHERE id=?", (bed_id,))
        
        conn.commit()
        return True

    except Exception as e:
        print(f"Error during discharge: {e}")
        return False
    finally:
        conn.close()    

# Initialize on run
init_db()