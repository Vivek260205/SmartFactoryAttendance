"""
utils/helpers.py
================
General-purpose helper functions used across the application.

Includes date/time formatting, ID generation, and file utilities.
"""

import os
import uuid
from datetime import datetime


def format_datetime(dt, fmt="%Y-%m-%d %H:%M:%S"):
    """
    Format a datetime object into a human-readable string.

    Args:
        dt: Datetime object to format.
        fmt: Output format string (default: YYYY-MM-DD HH:MM:SS).

    Returns:
        str: Formatted datetime string, or None if dt is falsy.
    """
    return dt.strftime(fmt) if dt else None


def generate_employee_id(department_code):
    """
    Generate a unique employee ID based on department code and a timestamp.

    Args:
        department_code: Short code for the department (e.g., "PRD").

    Returns:
        str: Generated employee ID (e.g., "PRD-20260805-1045").
    """
    code = (department_code or "GEN").upper()
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{code}-{stamp}"


def allowed_file(filename, allowed_extensions):
    """
    Check if an uploaded file has an allowed extension.

    Args:
        filename: Name of the uploaded file.
        allowed_extensions: Set of allowed file extensions.

    Returns:
        bool: True if extension is allowed, False otherwise.
    """
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in allowed_extensions


def save_upload(file, upload_folder):
    """
    Save an uploaded file to the specified folder with a unique name.

    Args:
        file: File object from request (werkzeug FileStorage).
        upload_folder: Destination folder path.

    Returns:
        str: Path to the saved file, or None if the file is empty.
    """
    if not file or not file.filename:
        return None

    os.makedirs(upload_folder, exist_ok=True)

    ext = ""
    if "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[1].lower()

    unique_name = f"{uuid.uuid4().hex}{ext}"
    destination = os.path.join(upload_folder, unique_name)
    file.save(destination)
    return destination