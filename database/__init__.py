"""
database/__init__.py
====================
Initializes the database package.

Provides access to the database connection and initialization utilities.
"""

from database.db_setup import init_db, get_db, drop_db, seed_initial_data

__all__ = ["init_db", "get_db", "drop_db", "seed_initial_data"]