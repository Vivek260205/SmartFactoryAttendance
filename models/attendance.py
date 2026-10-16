"""
models/attendance.py
====================
SQLAlchemy model for the Attendance record entity.

Tracks employee check-in and check-out events with timestamps.
"""

from datetime import datetime

from models import db


class Attendance(db.Model):
    """Database model for an attendance record (check-in / check-out)."""

    __tablename__ = "attendance_records"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(
        db.Integer, db.ForeignKey("employees.id"), nullable=False, index=True
    )
    check_in_time = db.Column(db.DateTime, nullable=False)
    check_out_time = db.Column(db.DateTime, nullable=True)
    date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False)  # present, absent, late
    # How the check-in was performed: "face_recognition" or "manual".
    attendance_method = db.Column(db.String(30), nullable=False, default="manual")
    safety_check_id = db.Column(
        db.Integer, db.ForeignKey("safety_checks.id"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        """String representation of the attendance record."""
        return f"<Attendance {self.id} employee={self.employee_id} status={self.status}>"

    def to_dict(self):
        """Serialize the attendance record to a dictionary."""
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "check_in_time": self.check_in_time.isoformat() if self.check_in_time else None,
            "check_out_time": self.check_out_time.isoformat() if self.check_out_time else None,
            "date": self.date.isoformat() if self.date else None,
            "status": self.status,
            "attendance_method": self.attendance_method,
            "safety_check_id": self.safety_check_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
