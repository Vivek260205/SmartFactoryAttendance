"""
tests/conftest.py
=================
Pytest fixtures for the Smart Factory Attendance test suite.
"""

import os
import tempfile

import pytest

from app import create_app
from config import TestingConfig
from models import db

# Shared temporary file-based SQLite database for all tests.
# A file (rather than :memory:) avoids cross-connection isolation issues
# that can occur with SQLAlchemy and in-memory SQLite.
_tmp_dir = tempfile.mkdtemp(prefix="smart_factory_tests_")
TEST_DB_PATH = os.path.join(_tmp_dir, "test.db")
TEST_UPLOAD_DIR = os.path.join(_tmp_dir, "uploads")


class TestConfig(TestingConfig):
    """Test configuration using a temporary file-based SQLite database."""

    SQLALCHEMY_DATABASE_URI = f"sqlite:///{TEST_DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = TEST_UPLOAD_DIR

    # Force the "no model" state for the general test suite so existing tests
    # that verify the app reports PPE_MODEL_UNAVAILABLE honestly continue to
    # pass. Real-model integration tests set PPE_MODEL_PATH explicitly.
    PPE_MODEL_PATH = ""


@pytest.fixture
def app():
    """Create a fresh Flask application with a clean database for each test."""
    app = create_app(TestConfig)

    with app.app_context():
        db.drop_all()
        db.create_all()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Provide a test client bound to the fixture app."""
    return app.test_client()


@pytest.fixture
def register_employee(client):
    """
    Register an employee via the /register route and return their employee ID.

    Usage:
        emp_id = register_employee()
        emp_id = register_employee(employee_id="PRD-0002", first_name="Jane")
    """

    def _register(
        employee_id="PRD-0001",
        first_name="John",
        last_name="Doe",
        department="Production",
        shift="Morning",
    ):
        resp = client.post(
            "/register",
            data={
                "employee_id": employee_id,
                "first_name": first_name,
                "last_name": last_name,
                "department": department,
                "shift": shift,
            },
        )
        assert resp.status_code == 302, f"Registration failed: {resp.status_code}"
        return employee_id

    return _register