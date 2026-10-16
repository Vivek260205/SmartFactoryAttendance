"""
services/__init__.py
====================
Initializes the services package.

Services contain the business logic layer, separate from routes and models.
"""

from services.attendance_service import AttendanceService
from services.safety_gear_service import SafetyGearService
from services.notification_service import NotificationService

# Shared service instances
attendance_service = AttendanceService()
safety_gear_service = SafetyGearService()
notification_service = NotificationService()

__all__ = [
    "AttendanceService",
    "SafetyGearService",
    "NotificationService",
    "attendance_service",
    "safety_gear_service",
    "notification_service",
]