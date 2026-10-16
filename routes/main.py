"""
routes/main.py
==============
Route handlers for the home (landing) page and employee registration.

These routes are mounted at the application root (no url_prefix) so that
the home page is served at "/" and registration at "/register".
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from models import db
from models.employee import Employee
from utils.helpers import generate_employee_id
from utils.validators import validate_employee_id, validate_name

# Blueprint for the home page and employee registration (root-level routes)
main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Render the application landing / home page."""
    return render_template("index.html")


@main_bp.route("/auto-attendance")
def auto_attendance():
    """Render the automatic (kiosk) face attendance page.

    This is the root-level alias for the kiosk mode. The camera auto-starts,
    frames are continuously captured and sent to the server for face detection
    + recognition, and attendance is recorded automatically — no manual button
    clicks required for the normal workflow.
    """
    return render_template("auto_attendance.html")


@main_bp.route("/employees", methods=["GET"])
def list_employees():
    """
    List all registered employees (read-only).

    Optional query parameters:
        department: Filter employees by department (case-insensitive substring).
        active:     Filter by active status ("true" / "false").

    Returns:
        JSON object with an "employees" list of serialized employee records.
    """
    department = request.args.get("department")
    active = request.args.get("active")

    query = Employee.query
    if department:
        query = query.filter(Employee.department.ilike(f"%{department}%"))
    if active is not None:
        active_bool = active.lower() in ("true", "1", "yes")
        query = query.filter(Employee.is_active.is_(active_bool))

    employees = query.order_by(Employee.created_at.desc()).all()
    return jsonify({"status": "ok", "employees": [e.to_dict() for e in employees]})


@main_bp.route("/register", methods=["GET", "POST"])
def register():
    """
    Render the employee registration page and handle registration submissions.

    On GET  -> display the registration form.
    On POST -> validate input, create an Employee record, and redirect home.
    """
    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        department = (request.form.get("department") or "").strip()
        shift = (request.form.get("shift") or "").strip()
        employee_id = (request.form.get("employee_id") or "").strip()

        # Basic validation
        errors = []
        if not validate_name(first_name):
            errors.append("First name is required and must be alphabetic.")
        if not validate_name(last_name):
            errors.append("Last name is required and must be alphabetic.")
        if not department:
            errors.append("Department is required.")
        if not shift:
            errors.append("Shift is required.")

        # Auto-generate an employee ID if one was not provided
        if not employee_id:
            department_code = "".join([c for c in department.upper() if c.isalpha()])[:3] or "GEN"
            employee_id = generate_employee_id(department_code)

        if not validate_employee_id(employee_id):
            errors.append("Employee ID format is invalid.")

        # Ensure uniqueness
        if employee_id and Employee.query.filter_by(employee_id=employee_id).first():
            errors.append("Employee ID already exists. Please use a different ID.")

        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template(
                "register.html",
                first_name=first_name,
                last_name=last_name,
                department=department,
                shift=shift,
                employee_id=employee_id,
            )

        # Persist the new employee
        employee = Employee(
            employee_id=employee_id,
            first_name=first_name,
            last_name=last_name,
            department=department,
            shift=shift,
            is_active=True,
        )
        db.session.add(employee)
        db.session.commit()

        flash(f"Employee {first_name} {last_name} registered successfully!", "success")
        # Redirect to the live face enrollment page so the operator can
        # immediately capture a face photo from the camera for this employee.
        return redirect(
            url_for("face_attendance.enroll") + f"?employee_id={employee_id}"
        )

    employees = Employee.query.order_by(Employee.created_at.desc()).all()
    return render_template("register.html", employees=employees)


@main_bp.route("/employee/<int:emp_id>/toggle-status", methods=["POST"])
def toggle_employee_status(emp_id):
    """Toggle an employee's active status."""
    employee = Employee.query.get(emp_id)
    if not employee:
        return jsonify({"status": "error", "message": "Employee not found."}), 404

    employee.is_active = not employee.is_active
    db.session.commit()
    status_str = "activated" if employee.is_active else "deactivated"
    return jsonify({
        "status": "ok",
        "message": f"Employee {employee.employee_id} {status_str}.",
        "is_active": employee.is_active,
    })


@main_bp.route("/api/system-status", methods=["GET"])
def system_status():
    """
    Check the actual availability of core system services:
    - Flask application runtime
    - SQLite database connection
    - Face detection model (YuNet / Haar Cascade)
    - Face recognition service
    - PPE detection model (YOLO weights)
    """
    import os
    from flask import current_app
    from sqlalchemy import text
    from services.face_recognition_service import DEFAULT_YUNET_MODEL, HAAR_CASCADE_PATH

    # Check Database connection
    db_ok = False
    try:
        db.session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    # Check Face Detection Model
    face_model_path = current_app.config.get("FACE_DETECTION_MODEL") or DEFAULT_YUNET_MODEL
    yunet_present = bool(face_model_path and os.path.exists(face_model_path))
    cascade_present = bool(HAAR_CASCADE_PATH and os.path.exists(HAAR_CASCADE_PATH))
    face_model_ok = yunet_present or cascade_present

    # Check Face Recognition Service
    face_service_ok = False
    try:
        from services.face_recognition_service import FaceRecognitionService
        FaceRecognitionService(yunet_model_path=face_model_path if yunet_present else None)
        face_service_ok = True
    except Exception:
        face_service_ok = False

    # Check PPE Model
    ppe_model_path = current_app.config.get("PPE_MODEL_PATH", "")
    ppe_model_ok = bool(ppe_model_path and os.path.exists(ppe_model_path))

    return jsonify({
        "status": "ok",
        "flask_healthy": True,
        "database_healthy": db_ok,
        "face_model_available": face_model_ok,
        "face_model_type": "YuNet ONNX" if yunet_present else ("Haar Cascade" if cascade_present else "None"),
        "face_model_path": face_model_path if yunet_present else (HAAR_CASCADE_PATH if cascade_present else None),
        "face_service_ready": face_service_ok,
        "ppe_model_available": ppe_model_ok,
        "ppe_model_path": ppe_model_path if ppe_model_ok else None,
        "ppe_model_classes": ["helmet", "vest", "boots", "gloves", "human"] if ppe_model_ok else [],
    })