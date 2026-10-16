"""
routes/attendance.py
====================
Route handlers for employee attendance (check-in / check-out).

The attendance page is served at "/attendance/" and the API endpoints for
check-in, check-out, and records retrieval are exposed under the same prefix.
"""

from datetime import datetime, date

import csv
import io
from flask import Blueprint, request, jsonify, render_template, Response

from models.attendance import Attendance
from models.employee import Employee
from services.attendance_service import AttendanceService

# Create the attendance blueprint
attendance_bp = Blueprint("attendance", __name__, url_prefix="/attendance")

# Shared service instance
attendance_service = AttendanceService()


def _serialize_record(record):
    """
    Attach employee display information to a serialized attendance record.

    The ORM model stores the numeric employee foreign key; consumers of the
    API expect the human-readable employee ID string and full name.

    Args:
        record: Serialized attendance record dict from the ORM model.

    Returns:
        dict: The same record enriched with employee_id (string), employee_name,
              department, and shift.
    """
    employee = Employee.query.get(record.get("employee_id"))
    if employee:
        record["employee_id"] = employee.employee_id
        record["employee_name"] = f"{employee.first_name} {employee.last_name}"
        record["department"] = employee.department
        record["shift"] = employee.shift
    else:
        record["employee_name"] = "Unknown"
        record["department"] = "-"
        record["shift"] = "-"
    return record


@attendance_bp.route("/")
def attendance_view():
    """Render the attendance management page."""
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.employee_id).all()
    return render_template("attendance.html", employees=employees)


@attendance_bp.route("/check-out", methods=["GET"])
def check_out_view():
    """Render the dedicated check-out page."""
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.employee_id).all()
    return render_template("check_out.html", employees=employees)



@attendance_bp.route("/employee-info", methods=["GET"])
def employee_info():
    """
    Look up an employee by ID string and return their details plus
    today's check-in / check-out status.

    Query parameters:
        employee_id: The employee's ID string.

    Returns:
        JSON with employee details and ``checked_in`` / ``checked_out``
        booleans for today.
    """
    employee_id = (request.args.get("employee_id") or "").strip()
    if not employee_id:
        return jsonify(
            {"status": "error", "message": "Employee ID is required."}
        ), 400

    employee = Employee.query.filter_by(employee_id=employee_id).first()
    if not employee:
        return jsonify(
            {"status": "error", "message": "Employee not found."}
        ), 404

    today = date.today()
    record = Attendance.query.filter_by(
        employee_id=employee.id, date=today
    ).first()

    checked_in = record is not None
    checked_out = record is not None and record.check_out_time is not None

    return jsonify(
        {
            "status": "ok",
            "employee": {
                "employee_id": employee.employee_id,
                "first_name": employee.first_name,
                "last_name": employee.last_name,
                "department": employee.department,
                "shift": employee.shift,
                "is_active": employee.is_active,
            },
            "checked_in": checked_in,
            "checked_out": checked_out,
            "check_in_time": record.check_in_time.isoformat() if record and record.check_in_time else None,
            "check_out_time": record.check_out_time.isoformat() if record and record.check_out_time else None,
            "record_id": record.id if record else None,
        }
    )


@attendance_bp.route("/check-in", methods=["POST"])
def check_in():
    """
    Handle employee check-in.

    Accepts either form-encoded or JSON payloads containing the employee ID.
    Delegates to AttendanceService to create the attendance record.
    """
    employee_id = request.form.get("employee_id") or (
        request.get_json(silent=True) or {}
    ).get("employee_id")
    if not employee_id:
        return jsonify({"status": "error", "message": "Employee ID is required."}), 400

    image_data = request.files.get("file")
    result = attendance_service.check_in(employee_id, image_data=image_data)
    status_code = 200 if result.get("status") == "ok" else 400
    return jsonify(result), status_code


@attendance_bp.route("/check-out", methods=["POST"])
def check_out():
    """
    Handle employee check-out.

    Accepts either form-encoded or JSON payloads containing the employee ID.
    Delegates to AttendanceService to update the attendance record.
    """
    employee_id = request.form.get("employee_id") or (
        request.get_json(silent=True) or {}
    ).get("employee_id")
    if not employee_id:
        return jsonify({"status": "error", "message": "Employee ID is required."}), 400

    result = attendance_service.check_out(employee_id)
    status_code = 200 if result.get("status") == "ok" else 400
    return jsonify(result), status_code


@attendance_bp.route("/records", methods=["GET"])
@attendance_bp.route("/history", methods=["GET"])
def get_records():
    """
    Retrieve attendance records.

    Optional query parameters:
        employee_id: Filter by employee's ID string.
        date:        Filter by date (YYYY-MM-DD).
    """
    employee_id = request.args.get("employee_id")
    date_str = request.args.get("date")

    filter_date = None
    if date_str:
        try:
            filter_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify(
                {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD."}
            ), 400

    records = attendance_service.get_records(employee_id=employee_id, date=filter_date)
    records = [_serialize_record(r) for r in records]

    return jsonify({"status": "ok", "records": records})


@attendance_bp.route("/export-csv", methods=["GET"])
def export_csv():
    """
    Export real attendance records from SQLite database to a downloadable CSV.

    Optional query parameters:
        employee_id: Filter by employee ID string.
        date: Filter by date (YYYY-MM-DD).
    """
    employee_id = request.args.get("employee_id")
    date_str = request.args.get("date")

    filter_date = None
    if date_str:
        try:
            filter_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    records = attendance_service.get_records(employee_id=employee_id, date=filter_date)
    records = [_serialize_record(r) for r in records]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Record ID",
        "Employee ID",
        "Employee Name",
        "Department",
        "Date",
        "Check-In Time",
        "Check-Out Time",
        "Attendance Method",
        "Status",
    ])

    for r in records:
        writer.writerow([
            r.get("id"),
            r.get("employee_id"),
            r.get("employee_name"),
            r.get("department", "-"),
            r.get("date"),
            r.get("check_in_time") or "-",
            r.get("check_out_time") or "-",
            r.get("attendance_method"),
            r.get("status"),
        ])

    csv_data = output.getvalue()
    filename = f"factory_attendance_{date.today().strftime('%Y%m%d')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )