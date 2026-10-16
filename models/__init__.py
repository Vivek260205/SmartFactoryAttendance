"""
models/__init__.py
==================
Initializes the models package and exposes the shared SQLAlchemy db instance.

All ORM models import `db` from this package so that the application factory
can initialize the database connection in one place.
"""

from flask_sqlalchemy import SQLAlchemy

# Shared SQLAlchemy instance used across all models
db = SQLAlchemy()