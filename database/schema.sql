-- ============================================================
-- schema.sql
-- ==========
-- SQL schema definitions for the Smart Factory Attendance database.
-- Defines tables for employees, attendance records, and safety checks.
-- Business logic is intentionally left unimplemented.
-- ============================================================

-- Employees table: stores factory worker details
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id VARCHAR(20) UNIQUE NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    department VARCHAR(50) NOT NULL,
    shift VARCHAR(20) NOT NULL,
    face_encoding BLOB,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Attendance records table: tracks check-in / check-out events
CREATE TABLE IF NOT EXISTS attendance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    check_in_time DATETIME NOT NULL,
    check_out_time DATETIME,
    date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,  -- present, absent, late
    attendance_method VARCHAR(30) NOT NULL DEFAULT 'manual',  -- face_recognition, manual
    safety_check_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees (id),
    FOREIGN KEY (safety_check_id) REFERENCES safety_checks (id)
);

-- Safety checks table: records PPE compliance check results
CREATE TABLE IF NOT EXISTS safety_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    check_time DATETIME NOT NULL,
    helmet_detected BOOLEAN DEFAULT 0,
    vest_detected BOOLEAN DEFAULT 0,
    gloves_detected BOOLEAN DEFAULT 0,
    boots_detected BOOLEAN DEFAULT 0,
    is_compliant BOOLEAN DEFAULT 0,
    image_path VARCHAR(255),
    confidence_score REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees (id)
);

-- Indexes for frequently queried columns
CREATE INDEX IF NOT EXISTS idx_attendance_employee ON attendance_records(employee_id);
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance_records(date);
CREATE INDEX IF NOT EXISTS idx_safety_check_employee ON safety_checks(employee_id);
CREATE INDEX IF NOT EXISTS idx_safety_check_time ON safety_checks(check_time);
CREATE INDEX IF NOT EXISTS idx_employee_department ON employees(department);
