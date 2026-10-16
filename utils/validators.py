"""
utils/validators.py
===================
Input validation functions for forms, API requests, and file uploads.
"""

import re
from datetime import datetime

# Employee ID pattern: LETTERS-ALPHANUMERIC (e.g., PRD-20260805-104530 or PRD-0001)
EMPLOYEE_ID_PATTERN = re.compile(r"^[A-Z]{2,5}-[A-Za-z0-9\-]+$")

# Name pattern: letters, spaces, hyphens, apostrophes (1-50 chars)
NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z\-\']{0,49}$")

# Allowed image extensions
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}

# Max upload size: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024


def validate_employee_id(employee_id):
    """
    Validate the format of an employee ID.

    Args:
        employee_id: Employee ID string to validate.

    Returns:
        bool: True if valid, False otherwise.
    """
    if not employee_id:
        return False
    return bool(EMPLOYEE_ID_PATTERN.match(employee_id.strip()))


def validate_name(name):
    """
    Validate a person's name (first or last).

    Args:
        name: Name string to validate.

    Returns:
        bool: True if valid, False otherwise.
    """
    if not name:
        return False
    return bool(NAME_PATTERN.match(name.strip()))


def validate_image_file(file):
    """
    Validate an uploaded image file (extension and size).

    Args:
        file: File object from a request (werkzeug FileStorage).

    Returns:
        bool: True if valid, False otherwise.
    """
    if not file or not file.filename:
        return False

    filename = file.filename
    if "." not in filename:
        return False

    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return False

    # Check file size by seeking to the end
    try:
        file.stream.seek(0, 2)  # Seek to end
        size = file.stream.tell()
        file.stream.seek(0)  # Reset pointer
    except Exception:
        return False

    return size <= MAX_FILE_SIZE


def validate_date_range(start_date, end_date):
    """
    Validate that a date range is well-formed (start <= end).

    Args:
        start_date: Start date string (YYYY-MM-DD) or datetime object.
        end_date: End date string (YYYY-MM-DD) or datetime object.

    Returns:
        bool: True if valid range, False otherwise.
    """
    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
        return start_date <= end_date
    except (ValueError, TypeError):
        return False


def sanitize_input(text):
    """
    Sanitize user input by stripping leading/trailing whitespace and
    removing angle brackets to mitigate basic HTML injection.

    Args:
        text: Raw user input string.

    Returns:
        str: Sanitized string.
    """
    if text is None:
        return ""
    text = str(text).strip()
    text = text.replace("<", "").replace(">", "")
    return text