"""
app.py
======
Main entry point for the Smart Factory Attendance with Safety Gear Check application.

This module initializes the Flask application, registers blueprints,
and configures the database.
"""

import os

from flask import Flask

from config import Config
from database.db_setup import init_db


def create_app(config_class=Config):
    """
    Application factory pattern.
    Creates and configures the Flask application instance.

    Args:
        config_class: Configuration class to use for app settings.

    Returns:
        Flask: Configured Flask application instance.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
    app.config["MAX_FORM_MEMORY_SIZE"] = 10 * 1024 * 1024
    # Ensure Werkzeug allows form payloads up to 10 MB (e.g. for base64 camera frames)
    if hasattr(app.request_class, "max_form_memory_size"):
        app.request_class.max_form_memory_size = 10 * 1024 * 1024

    # Ensure the upload folder exists
    upload_folder = app.config.get("UPLOAD_FOLDER")
    if upload_folder:
        os.makedirs(upload_folder, exist_ok=True)

# Initialize the SQLite database connection and create tables
    init_db(app)

    # Register all blueprints (routes)
    from routes import (
        main_bp,
        attendance_bp,
        safety_gear_bp,
        dashboard_bp,
        face_attendance_bp,
    )

    app.register_blueprint(main_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(safety_gear_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(face_attendance_bp)

    return app


# Entry point for running the application directly
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)