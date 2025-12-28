# database.py
import sqlite3
import pandas as pd
import hashlib
from datetime import datetime
import random # For generating mock data

DB_NAME = "hospital.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 1. PATIENTS TABLE (Updated with Nurse & Outcome tracking)
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
            
            -- Triage Data
            triage_level INTEGER,   
            ai_level INTEGER,       
            confidence REAL,
            ai_explanation TEXT,
            nurse_notes TEXT,
              
            -- Outcomes (NEW for Analytics)
            final_disposition TEXT, -- 'Discharge', 'Admit', 'ICU', 'Surgery'
            
            -- Staffing & Logistics
            triage_nurse TEXT,      -- NEW: Who performed the triage?
            assigned_md TEXT,
            assigned_nppa TEXT,
            assigned_nurse TEXT,    -- Bedside nurse (different from triage nurse)
            
            arrival_time TIMESTAMP,
            status TEXT
        )
    ''')
    
    # 2. STAFF TABLE
    c.execute('''
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            role TEXT
        )
    ''')

    # 3. USERS TABLE
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            role TEXT
        )
    ''')
    
    # 3. MOCK DATA GENERATOR (Crucial for your Charts)
    c.execute("SELECT * FROM users")
    if not c.fetchone():
        # Create Users
        users = [("nurse", "admin", "Nurse"), ("admin", "admin", "Admin"), 
                 ("nora", "password", "Nurse"), ("sarah", "password", "Nurse")]
        for u, p, r in users:
            pw_hash = hashlib.sha256(p.encode()).hexdigest()
            c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (u, pw_hash, r))
        
        # Create Staff
        staff = [("Dr. House", "ED MD"), ("Dr. Grey", "ED MD"), 
                 ("Nora Roosevelt", "Nurse"), ("Sarah Connor", "Nurse")]
        for n, r in staff:
            c.execute("INSERT INTO staff (name, role) VALUES (?, ?)", (n, r))

        # Create 100 Mock Patients for Analytics
        print("Generating mock data...")
        nurse_options = ["nora", "sarah", "nurse"]
        
        for i in range(100):
            nurse = random.choice(nurse_options)
            ai_lvl = random.choices([1, 2, 3, 4, 5], weights=[5, 15, 40, 30, 10])[0]
            
            # Logic: 80% Agreement, 10% Up, 10% Down
            r = random.random()
            if r < 0.80:
                final_lvl = ai_lvl # Agree
            elif r < 0.90:
                final_lvl = max(1, ai_lvl - 1) # Up-Triage (Level 2 is "Higher" than 3)
            else:
                final_lvl = min(5, ai_lvl + 1) # Down-Triage
            
            # Outcome Logic (Lower Level = Sicker)
            if final_lvl <= 2: 
                disp = random.choices(['ICU', 'Admit', 'Surgery'], weights=[30, 50, 20])[0]
            elif final_lvl == 3:
                disp = random.choices(['Admit', 'Discharge'], weights=[40, 60])[0]
            else:
                disp = 'Discharge'

            c.execute('''
                INSERT INTO patients (name, age, gender, complaint, triage_level, ai_level, 
                confidence, triage_nurse, final_disposition, arrival_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"Patient {i}", random.randint(18, 90), "Male", "Mock Complaint", 
                final_lvl, ai_lvl, 88.5, nurse, disp, 
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Discharged"
            ))

    conn.commit()
    conn.close()

# --- KEEP ALL OTHER EXISTING FUNCTIONS SAME AS BEFORE ---
# (verify_login, add_patient, get_all_patients, etc.)
# Just ensure 'add_patient' now accepts 'triage_nurse' argument

def verify_login(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    hashed_input = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT role FROM users WHERE username = ? AND password_hash = ?", (username, hashed_input))
    result = c.fetchone()
    conn.close()
    if result: return True, result[0]
    return False, None

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

# ... (Copy the rest of your previous database functions: get_all, get_by_id, updates, staff, etc.) ...
# Ensure you copy get_all_patients, discharge_patient, etc. from previous steps.
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

def get_patient_history(name):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT * FROM patients WHERE name = ? ORDER BY arrival_time DESC", conn, params=(name,))
    conn.close()
    return df

def update_patient_status(patient_id, status):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE patients SET status = ? WHERE id = ?", (status, patient_id))
    conn.commit()
    conn.close()

def discharge_patient(patient_id):
    update_patient_status(patient_id, "Discharged")

def assign_staff(patient_id, md, nppa, nurse):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE patients SET assigned_md=?, assigned_nppa=?, assigned_nurse=? WHERE id=?", (md, nppa, nurse, patient_id))
    conn.commit()
    conn.close()

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

def add_staff(name, role):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO staff (name, role) VALUES (?, ?)", (name, role))
    conn.commit()
    conn.close()

def get_staff_by_role(role):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT name FROM staff WHERE role = ?", conn, params=(role,))
    conn.close()
    return df['name'].tolist()

def get_all_staff():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql("SELECT * FROM staff", conn)
    conn.close()
    return df

init_db()