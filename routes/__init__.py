"""
routes/__init__.py
==================
Initializes the routes package and exposes Flask Blueprints.
"""

from routes.main import main_bp
from routes.attendance import attendance_bp
from routes.safety_gear import safety_gear_bp
from routes.dashboard import dashboard_bp
from routes.face_attendance import face_attendance_bp

__all__ = [
    "main_bp",
    "attendance_bp",
    "safety_gear_bp",
    "dashboard_bp",
    "face_attendance_bp",
]
