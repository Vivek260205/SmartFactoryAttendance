"""
services/attendance_service.py
==============================
Business logic for employee attendance operations.

Handles check-in, check-out, record retrieval, and attendance status computation.
Face recognition and safety gear integration are intentionally deferred.
"""

from datetime import datetime, date, timedelta

from models import db
from models.attendance import Attendance
from models.employee import Employee


class AttendanceService:
    """Service class for attendance-related business logic."""

    def check_in(self, employee_id, image_data=None, attendance_method="manual"):
        """
        Process an employee check-in.

        Args:
            employee_id: Unique identifier (employee_id string) for the employee.
            image_data: Optional image/snapshot for face verification (not used yet).
            attendance_method: How the check-in was performed. Either
                "face_recognition" or "manual" (default "manual").

        Returns:
            dict: Result of the check-in operation.
        """
        employee = Employee.query.filter_by(employee_id=employee_id).first()
        if not employee:
            return {"status": "error", "message": "Employee not found."}

        today = date.today()
        existing = Attendance.query.filter_by(
            employee_id=employee.id, date=today
        ).first()
        if existing and existing.check_out_time is None:
            return {
                "status": "error",
                "message": "Employee already checked in today.",
            }

        record = Attendance(
            employee_id=employee.id,
            check_in_time=datetime.utcnow(),
            date=today,
            status="present",
            attendance_method=attendance_method,
        )
        db.session.add(record)
        db.session.commit()

        return {
            "status": "ok",
            "message": "Check-in recorded.",
            "record_id": record.id,
            "attendance_method": attendance_method,
            "check_in_time": record.check_in_time.isoformat() if record.check_in_time else None,
        }

    def check_out(self, employee_id):
        """
        Process an employee check-out.

        Args:
            employee_id: Unique identifier (employee_id string) for the employee.

        Returns:
            dict: Result of the check-out operation.
        """
        employee = Employee.query.filter_by(employee_id=employee_id).first()
        if not employee:
            return {"status": "error", "message": "Employee not found."}

        today = date.today()
        record = Attendance.query.filter_by(
            employee_id=employee.id, date=today
        ).first()
        if not record:
            return {"status": "error", "message": "No check-in record found for today."}
        if record.check_out_time is not None:
            return {"status": "error", "message": "Employee already checked out today."}

        record.check_out_time = datetime.utcnow()
        db.session.commit()

        return {
            "status": "ok",
            "message": "Check-out recorded.",
            "record_id": record.id,
            "check_out_time": record.check_out_time.isoformat() if record.check_out_time else None,
        }

    def get_records(self, employee_id=None, date=None):
        """
        Retrieve attendance records with optional filters.

        Args:
            employee_id: Filter by employee (optional).
            date: Filter by specific date (optional).

        Returns:
            list: Matching attendance records (serialized).
        """
        query = Attendance.query
        if employee_id:
            employee = Employee.query.filter_by(employee_id=employee_id).first()
            if employee:
                query = query.filter_by(employee_id=employee.id)
            else:
                return []
        if date:
            query = query.filter_by(date=date)

        records = query.order_by(Attendance.check_in_time.desc()).all()
        return [r.to_dict() for r in records]

    def compute_status(self, check_in_time, shift_start_time):
        """
        Determine attendance status (present, late, absent).

        Args:
            check_in_time: Actual check-in datetime.
            shift_start_time: Scheduled shift start datetime.

        Returns:
            str: Attendance status ("present", "late", or "absent").
        """
        if not check_in_time:
            return "absent"

        # Grace period of 15 minutes
        if check_in_time <= shift_start_time + timedelta(minutes=15):
            return "present"
        return "late"
