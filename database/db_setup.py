"""
database/db_setup.py
====================
Database initialization and connection management.

Handles creating the database connection, running migrations, and
seeding initial data.
"""

import os

from models import db


def init_db(app):
    """
    Initialize the database with the given Flask app context.

    Binds the shared SQLAlchemy instance to the app and creates all
    tables defined by the ORM models.

    Args:
        app: Flask application instance to bind the database to.

    Returns:
        None
    """
    # Ensure the instance folder exists for the SQLite file
    instance_path = os.path.join(app.root_path, "instance")
    os.makedirs(instance_path, exist_ok=True)

    db.init_app(app)
    with app.app_context():
        # Import models so SQLAlchemy registers them before create_all()
        from models.employee import Employee  # noqa: F401
        from models.attendance import Attendance  # noqa: F401
        from models.safety_check import SafetyCheck  # noqa: F401

        db.create_all()


def get_db():
    """Return the current SQLAlchemy database instance."""
    return db


def drop_db(app):
    """
    Drop all database tables (useful for testing/reset).

    Args:
        app: Flask application instance.

    Returns:
        None
    """
    with app.app_context():
        db.drop_all()


def seed_initial_data(app):
    """
    Populate the database with seed data (e.g., default admin, departments).

    Args:
        app: Flask application instance.

    Returns:
        None
    """
    from models.employee import Employee

    with app.app_context():
        if Employee.query.first() is None:
            sample = Employee(
                employee_id="PRD-0001",
                first_name="John",
                last_name="Doe",
                department="Production",
                shift="Morning",
                is_active=True,
            )
            db.session.add(sample)
            db.session.commit()