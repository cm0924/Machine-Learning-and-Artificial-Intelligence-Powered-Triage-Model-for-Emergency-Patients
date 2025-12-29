# database.py
import sqlite3
import pandas as pd
from datetime import datetime
import random 

DB_NAME = "hospital.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 1. PATIENTS TABLE (Same as before)
    c.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            age INTEGER,
            gender TEXT,
            arrival_mode INTEGER,
            injury INTEGER,
            complaint TEXT,
            mental INTEGER,
            pain INTEGER,
            nrs_pain INTEGER,
            sbp INTEGER,
            dbp INTEGER,
            hr INTEGER,
            rr INTEGER,
            bt REAL,
            saturation INTEGER,
            triage_level INTEGER,   
            ai_level INTEGER,       
            confidence REAL,
            ai_explanation TEXT,
            nurse_notes TEXT,
            final_disposition TEXT,
            triage_nurse TEXT,
            assigned_md TEXT,
            assigned_nppa TEXT,
            assigned_nurse TEXT,
            arrival_time TIMESTAMP,
            status TEXT
        )
    ''')
    
    # 2. UNIFIED USERS TABLE (Merges Staff + Credentials)
    # We removed hashlib to allow you to "View" passwords in the admin panel
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            username TEXT UNIQUE,
            password TEXT, 
            role TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS beds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bed_label TEXT UNIQUE,   -- e.g., "ER-01", "ICU-03"
            department TEXT,         -- "Emergency", "ICU", "Ward"
            status TEXT,             -- "Available", "Occupied", "Cleaning", "Maintenance"
            current_patient_id INTEGER, -- Links to patients table
            FOREIGN KEY(current_patient_id) REFERENCES patients(id)
        )
    ''')
    
    # 3. MOCK DATA GENERATOR
    c.execute("SELECT * FROM users")
    if not c.fetchone():
        print("Generating mock data...")
        
        # Create Staff with Credentials
        # Format: (Real Name, Username, Password, Role)
        staff_members = [
            ("System Admin", "admin", "admin123", "admin"),
            ("Nurse Joy", "nurse", "nurse123", "nurse"),
            ("Nora Roosevelt", "nora", "pass123", "nurse"),
            ("Sarah Connor", "sarah", "pass123", "nurse"),
            ("Dr. Gregory House", "dr_house", "vicodin", "doctor"),
            ("Dr. Meredith Grey", "dr_grey", "derrick", "doctor"),
            ("Dr. Stephen Strange", "dr_strange", "time", "doctor"),
            # --- NEW NP/PA STAFF ---
            ("Peter Parker, PA-C", "peter", "web123", "nppa"), 
            ("Carol Danvers, NP", "carol", "hero123", "nppa")
        ]
        
        for name, user, pwd, role in staff_members:
            c.execute("INSERT INTO users (full_name, username, password, role) VALUES (?, ?, ?, ?)", 
                      (name, user, pwd, role))

        # Create Mock Patients (Using the new user list for triage_nurse)
        nurse_usernames = ["nurse", "nora", "sarah"]
        
        for i in range(50):
            nurse = random.choice(nurse_usernames)
            ai_lvl = random.choices([1, 2, 3, 4, 5], weights=[5, 15, 40, 30, 10])[0]
            
            # Logic: 80% Agreement
            if random.random() < 0.80:
                final_lvl = ai_lvl
            else:
                final_lvl = max(1, min(5, ai_lvl + random.choice([-1, 1])))
            
            disp = 'Discharge' if final_lvl > 3 else 'Admit'

            c.execute('''
                INSERT INTO patients (name, age, gender, complaint, triage_level, ai_level, 
                confidence, triage_nurse, final_disposition, arrival_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"Patient {i+100}", random.randint(18, 90), "Male", "Mock Complaint", 
                final_lvl, ai_lvl, 88.5, nurse, disp, 
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Discharged"
            ))

     # B. BEDS (UPDATED LOGIC HERE)
    c.execute("SELECT count(*) FROM beds")
    if c.fetchone()[0] == 0:
        print("Generating 100 mock beds...")
        
        # DEFINITION: (Department Name, Count)
        departments = [
            ("Emergency", 20), # 20 ER Beds
            ("ICU", 30),       # 30 ICU Beds
            ("Ward", 50)       # 50 Ward Beds
        ]
        
        for dept, count in departments:
            for i in range(1, count + 1):
                # Generates labels like EME-01, ICU-05, WAR-49
                label = f"{dept[:3].upper()}-{i:02d}" 
                c.execute("INSERT INTO beds (bed_label, department, status) VALUES (?, ?, ?)", 
                          (label, dept, "Available"))

    conn.commit()
    conn.close()

# --- LOGIN & USER MANAGEMENT FUNCTIONS ---

def verify_login(username, password):
    """Verifies login using plain text comparison."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # No hashing here, so we can view passwords in Admin Panel
    c.execute("SELECT role FROM users WHERE username = ? AND password = ?", (username, password))
    result = c.fetchone()
    conn.close()
    if result: return True, result[0]
    return False, None

def get_all_users():
    """Fetches all user credentials including ID for the Admin Panel."""
    conn = sqlite3.connect(DB_NAME)
    # ADDED 'id' to the list of columns below:
    df = pd.read_sql("SELECT id, full_name, username, password, role FROM users", conn)
    conn.close()
    return df

def get_staff_by_role(role):
    """Used for dropdowns (e.g., assigning a Doctor)"""
    conn = sqlite3.connect(DB_NAME)
    # We fetch 'full_name' for the dropdown list
    df = pd.read_sql("SELECT full_name FROM users WHERE role = ?", conn, params=(role,))
    conn.close()
    return df['full_name'].tolist()

# --- PATIENT FUNCTIONS (UNCHANGED) ---

def add_patient(name, age, gender, arrival_mode, injury, complaint, 
                mental, pain, nrs_pain, sbp, dbp, hr, rr, bt, saturation,
                final_level, ai_level, conf, explanation, notes, triage_nurse, status="Waiting"):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO patients (
            name, age, gender, arrival_mode, injury, complaint,
            mental, pain, nrs_pain, sbp, dbp, hr, rr, bt, saturation,
            triage_level, ai_level, confidence, ai_explanation, nurse_notes, triage_nurse, arrival_time, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        name, age, gender, arrival_mode, injury, complaint,
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

def update_full_patient_record(patient_id, name, age, gender, complaint, sbp, dbp, hr, rr, bt, sat, triage_level, md, nppa, nurse, notes):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        UPDATE patients 
        SET name=?, age=?, gender=?, complaint=?, sbp=?, dbp=?, hr=?, rr=?, bt=?, saturation=?, triage_level=?, assigned_md=?, assigned_nppa=?, assigned_nurse=?, nurse_notes=?
        WHERE id=?
    ''', (name, age, gender, complaint, sbp, dbp, hr, rr, bt, sat, triage_level, md, nppa, nurse, notes, patient_id))
    conn.commit()
    conn.close()

def discharge_patient(patient_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE patients SET status = 'Discharged' WHERE id = ?", (patient_id,))
    conn.commit()
    conn.close()

# --- APPEND THIS TO database.py ---

def add_user(full_name, username, password, role):
    """Creates a new user. Returns True if successful, False if username exists."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (full_name, username, password, role) VALUES (?, ?, ?, ?)", 
                  (full_name, username, password, role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False # Username already exists
    finally:
        conn.close()

def update_user(user_id, full_name, username, password, role):
    """Updates an existing user's details."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        UPDATE users 
        SET full_name=?, username=?, password=?, role=?
        WHERE id=?
    ''', (full_name, username, password, role, user_id))
    conn.commit()
    conn.close()

def delete_user(user_id):
    """Deletes a user by ID."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

# --- BED FUNCTIONS ---

def get_all_beds():
    conn = sqlite3.connect(DB_NAME)
    # Join with patients to get the name of the person in the bed
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
    """Get patients who have been triaged but not assigned a bed."""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT id, name, triage_level, complaint FROM patients WHERE status = 'Waiting'", conn)
    conn.close()
    return df

def assign_patient_to_bed(bed_id, patient_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        # 1. Update Bed
        c.execute("UPDATE beds SET status='Occupied', current_patient_id=? WHERE id=?", (patient_id, bed_id))
        # 2. Update Patient Status
        c.execute("UPDATE patients SET status='Admitted' WHERE id=?", (patient_id,))
        conn.commit()
        return True
    except Exception as e:
        print(e)
        return False
    finally:
        conn.close()

def clear_bed(bed_id, patient_id):
    """Discharges patient from bed, sets bed to Cleaning."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # 1. Free the bed
    c.execute("UPDATE beds SET status='Cleaning', current_patient_id=NULL WHERE id=?", (bed_id,))
    # 2. Update patient (keep them as Admitted in history, or mark Discharged)
    # Usually we don't change patient status here, they just leave the bed.
    conn.commit()
    conn.close()

def set_bed_status(bed_id, status):
    """For marking bed as Available after cleaning, or Maintenance."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE beds SET status=? WHERE id=?", (status, bed_id))
    conn.commit()
    conn.close()

def get_patient_history(name):
    """Fetches all past visits for a patient by matching their name."""
    conn = sqlite3.connect(DB_NAME)
    try:
        df = pd.read_sql("SELECT * FROM patients WHERE name = ? ORDER BY arrival_time DESC", conn, params=(name,))
    except Exception as e:
        print(f"Error fetching history: {e}")
        df = pd.DataFrame() # Return empty if error
    finally:
        conn.close()
    return df

def start_treatment_detailed(patient_id, md, nppa, nurse, bed_id, notes):
    """
    Updates patient status to In-Treatment, assigns the care team, 
    and handles bed assignment if a bed is selected.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    try:
        # 1. Update Patient Record (Team + Status)
        c.execute('''
            UPDATE patients 
            SET status='In-Treatment', 
                assigned_md=?, 
                assigned_nppa=?, 
                assigned_nurse=?, 
                nurse_notes = nurse_notes || ?
            WHERE id=?
        ''', (md, nppa, nurse, f"\n[Treatment Started]: {notes}", patient_id))
        
        # 2. Handle Bed Assignment (If a bed was selected)
        if bed_id:
            # First, check if patient already has a DIFFERENT bed, if so, free it? 
            # (Skipping complex swap logic for simplicity, assuming they move to empty bed)
            
            # Mark Bed as Occupied
            c.execute("UPDATE beds SET status='Occupied', current_patient_id=? WHERE id=?", (patient_id, bed_id))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error starting treatment: {e}")
        return False
    finally:
        conn.close()

def get_available_beds_list():
    """Returns a list of beds that are Available (for the dropdown)."""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT id, bed_label, department FROM beds WHERE status='Available'", conn)
    conn.close()
    return df

def get_patient_bed(patient_id):
    """Returns the bed label (e.g., 'ER-01') if patient is assigned to one."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT bed_label FROM beds WHERE current_patient_id=?", (patient_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "Waiting Room"            

# Initialize on run
init_db()