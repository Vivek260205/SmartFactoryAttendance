"""
models/employee.py
==================
SQLAlchemy model for the Employee entity.

Represents a factory worker with personal details and shift information.
"""

from datetime import datetime

from models import db


class Employee(db.Model):
    """Database model for a factory employee."""

    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(20), unique=True, nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    department = db.Column(db.String(50), nullable=False, index=True)
    shift = db.Column(db.String(20), nullable=False)
    face_encoding = db.Column(db.LargeBinary, nullable=True)  # For face recognition
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        """String representation of the employee."""
        return f"<Employee {self.employee_id} {self.first_name} {self.last_name}>"

    def to_dict(self):
        """Serialize the employee record to a dictionary."""
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "department": self.department,
            "shift": self.shift,
            "is_active": self.is_active,
            "has_face_enrolled": self.face_encoding is not None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }