"""
models/safety_check.py
======================
SQLAlchemy model for the SafetyCheck entity.

Records the result of a PPE (safety gear) compliance check for an employee.
"""

from datetime import datetime

from models import db


class SafetyCheck(db.Model):
    """Database model for a safety gear compliance check."""

    __tablename__ = "safety_checks"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(
        db.Integer, db.ForeignKey("employees.id"), nullable=False, index=True
    )
    check_time = db.Column(db.DateTime, nullable=False, index=True)
    helmet_detected = db.Column(db.Boolean, default=False)
    vest_detected = db.Column(db.Boolean, default=False)
    gloves_detected = db.Column(db.Boolean, default=False)
    boots_detected = db.Column(db.Boolean, default=False)
    is_compliant = db.Column(db.Boolean, default=False)
    image_path = db.Column(db.String(255), nullable=True)
    confidence_score = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        """String representation of the safety check record."""
        return f"<SafetyCheck {self.id} employee={self.employee_id} compliant={self.is_compliant}>"

    def to_dict(self):
        """Serialize the safety check record to a dictionary."""
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "check_time": self.check_time.isoformat() if self.check_time else None,
            "helmet_detected": self.helmet_detected,
            "vest_detected": self.vest_detected,
            "gloves_detected": self.gloves_detected,
            "boots_detected": self.boots_detected,
            "is_compliant": self.is_compliant,
            "image_path": self.image_path,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }