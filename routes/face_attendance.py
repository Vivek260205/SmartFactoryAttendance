"""
routes/face_attendance.py
=========================
Route handlers for face-based attendance (live camera + gallery fallback).

Workflow
--------
1. **Enrollment** — On the Employee Registration page, after the employee
   record is created, the operator is redirected to the face enrollment page.
   A live camera feed is shown; the operator captures a clear face photo.
   The face encoding is stored on the employee record. A gallery upload
   fallback is also available.

2. **Face Attendance (Check-In)** — The Face Attendance page opens a live
   camera. The operator captures a frame; the server detects the face,
   encodes it, and matches it against all enrolled employees. If a match is
   found, the employee's name and ID are displayed and check-in is recorded
   automatically with ``attendance_method = "face_recognition"``.

3. **Unknown Face Fallback** — If no match is found, "Face not recognized" is
   shown and a manual fallback lets the operator select an employee. Attendance
   is then recorded with ``attendance_method = "manual"``.

4. **Check-Out** — The same face-recognition workflow is used for check-out.
   A recognized employee automatically receives check-out. If recognition
   fails, the manual fallback is available.

Attendance is NEVER marked automatically on face detection alone for the
manual path. For the face path, check-in/check-out is recorded automatically
once a face is recognized (no manual employee ID entry required).
"""

import base64
import os
from datetime import date

from flask import Blueprint, current_app, jsonify, render_template, request

from models import db
from models.attendance import Attendance
from models.employee import Employee
from services.attendance_service import AttendanceService
from services.face_recognition_service import (
    FaceRecognitionError,
    FaceRecognitionService,
)
from utils.helpers import allowed_file, save_upload

# Blueprint mounted at /face-attendance
face_attendance_bp = Blueprint(
    "face_attendance", __name__, url_prefix="/face-attendance"
)

attendance_service = AttendanceService()


def _build_face_service():
    """Build a FaceRecognitionService from config (or raise on error)."""
    model_path = current_app.config.get("FACE_DETECTION_MODEL", "")
    threshold = current_app.config.get("FACE_MATCH_THRESHOLD", 18.0)
    return FaceRecognitionService(
        yunet_model_path=model_path or None,
        match_threshold=threshold,
    )


# ------------------------------------------------------------------- helpers
def _save_image(file):
    """Validate and save an uploaded image; return the saved path or None."""
    allowed_extensions = current_app.config.get("ALLOWED_EXTENSIONS", set())
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename, allowed_extensions):
        return None
    upload_folder = current_app.config.get("UPLOAD_FOLDER")
    return save_upload(file, upload_folder)


def _employee_to_info(employee):
    """Serialize an employee to the display payload used by the UI."""
    return {
        "employee_id": employee.employee_id,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "department": employee.department,
        "shift": employee.shift,
        "has_face_enrolled": employee.face_encoding is not None,
    }


def _decode_base64_image(data_url):
    """
    Decode a base64 data-URL (from the browser canvas) into a BGR numpy array.

    Args:
        data_url: A string like "data:image/png;base64,iVBOR...".

    Returns:
        BGR numpy array, or None if decoding fails.
    """
    import cv2
    import numpy as np

    if not data_url or "," not in data_url:
        return None
    header, b64 = data_url.split(",", 1)
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return None
    arr = np.frombuffer(raw, dtype=np.uint8)
    image_array = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return image_array


# ---------------------------------------------------------------- enrollment
@face_attendance_bp.route("/enroll", methods=["GET", "POST"])
def enroll():
    """
    Enroll (store) an employee's face encoding.

    GET  — render the enrollment page (optionally pre-filled with an
           ``employee_id`` query parameter from the registration redirect).
    POST — enroll from an uploaded gallery photo (fallback path).
    """
    if request.method == "POST":
        employee_id = (request.form.get("employee_id") or "").strip()
        file = request.files.get("file")

        if not employee_id:
            return jsonify(
                {"status": "error", "message": "Employee ID is required."}
            ), 400

        employee = Employee.query.filter_by(employee_id=employee_id).first()
        if not employee:
            return jsonify(
                {"status": "error", "message": "Employee not found."}
            ), 404

        saved_path = _save_image(file)
        if not saved_path:
            return jsonify(
                {
                    "status": "error",
                    "message": "Please upload a valid image (PNG/JPG/JPEG).",
                }
            ), 400

        try:
            service = _build_face_service()
            result = service.enroll(employee, saved_path)
        except FaceRecognitionError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

        if result.get("status") != "ok":
            return jsonify(result), 400

        db.session.commit()
        return jsonify(
            {
                "status": "ok",
                "message": result.get("message"),
                "employee": _employee_to_info(employee),
            }
        )

    # GET — pre-fill employee_id from query string if provided
    employee_id = request.args.get("employee_id", "")
    return render_template("face_enroll.html", employee_id=employee_id)


@face_attendance_bp.route("/enroll-capture", methods=["POST"])
def enroll_capture():
    """
    Enroll a face from a live-camera captured frame (base64 data-URL).

    The browser captures a frame from the video stream, draws it to a canvas,
    and sends it as a base64 data-URL. The server decodes it, detects the
    face, encodes it, and stores the encoding on the employee record.
    """
    employee_id = (request.form.get("employee_id") or "").strip()
    image_data = request.form.get("image_data") or (
        (request.get_json(silent=True) or {}).get("image_data", "")
    )

    if not employee_id:
        return jsonify(
            {"status": "error", "message": "Employee ID is required."}
        ), 400

    employee = Employee.query.filter_by(employee_id=employee_id).first()
    if not employee:
        return jsonify(
            {"status": "error", "message": "Employee not found."}
        ), 404

    image_array = _decode_base64_image(image_data)
    if image_array is None:
        return jsonify(
            {
                "status": "error",
                "message": "Could not decode the captured image.",
            }
        ), 400

    try:
        service = _build_face_service()
        result = service.enroll_from_array(employee, image_array)
    except FaceRecognitionError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    if result.get("status") != "ok":
        return jsonify(result), 400

    db.session.commit()
    return jsonify(
        {
            "status": "ok",
            "message": result.get("message"),
            "employee": _employee_to_info(employee),
        }
    )


# ---------------------------------------------------------------- recognition
@face_attendance_bp.route("/")
def face_attendance_view():
    """Render the face attendance page."""
    return render_template("face_attendance.html")


@face_attendance_bp.route("/capture", methods=["POST"])
def capture_and_recognize():
    """
    Process a live-camera captured frame and attempt face recognition.

    The browser sends a base64 data-URL of the current video frame. The server
    detects the face, encodes it, and matches against all enrolled employees.

    Returns the recognized employee info (if matched) or an "unknown" state
    with ``manual: true`` so the UI can fall back to manual selection.

    Attendance is NOT marked here; it is only marked via /mark after
    identification (or automatically if the caller requests auto-mark).
    """
    image_data = request.form.get("image_data") or (
        request.get_json(silent=True) or {}
    ).get("image_data", "")

    image_array = _decode_base64_image(image_data)
    if image_array is None:
        return jsonify(
            {
                "status": "error",
                "message": "Could not decode the captured image.",
            }
        ), 400

    try:
        service = _build_face_service()
        result = service.recognize(image_array)
    except FaceRecognitionError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    if result["recognized"] and result["employee"]:
        return jsonify(
            {
                "status": "ok",
                "recognized": True,
                "employee": _employee_to_info(result["employee"]),
                "distance": result["distance"],
                "manual": False,
            }
        )

    return jsonify(
        {
            "status": "ok",
            "recognized": False,
            "message": result["message"],
            "manual": True,
        }
    )


@face_attendance_bp.route("/recognize", methods=["POST"])
def recognize():
    """
    Detect a face in an uploaded photo and identify the employee.

    Returns recognized employee info or an "unknown" state. Attendance is NOT
    marked here; it is only marked via /mark after identification.
    """
    file = request.files.get("file")
    saved_path = _save_image(file)
    if not saved_path:
        return jsonify(
            {
                "status": "error",
                "message": "Please upload a valid image (PNG/JPG/JPEG).",
            }
        ), 400

    try:
        service = _build_face_service()
        import cv2

        image_array = cv2.imread(saved_path)
        if image_array is None:
            return jsonify(
                {"status": "error", "message": "Could not read the uploaded image."}
            ), 400

        result = service.recognize(image_array)
    except FaceRecognitionError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    if result["recognized"] and result["employee"]:
        return jsonify(
            {
                "status": "ok",
                "recognized": True,
                "employee": _employee_to_info(result["employee"]),
                "distance": result["distance"],
                "manual": False,
            }
        )

    return jsonify(
        {
            "status": "ok",
            "recognized": False,
            "message": result["message"],
            "manual": True,
        }
    )


@face_attendance_bp.route("/mark", methods=["POST"])
def mark_attendance():
    """
    Mark attendance (check-in or check-out) for an identified employee.

    Accepts:
        employee_id: The employee's ID string.
        via_face:    "true" if identified via face recognition, "false" for
                     manual fallback.
        action:      "check-in" (default) or "check-out".

    For the face path, check-in is recorded automatically with
    ``attendance_method = "face_recognition"``. For the manual fallback,
    ``attendance_method = "manual"``.
    """
    employee_id = (request.form.get("employee_id") or "").strip()
    via_face = request.form.get("via_face", "false").lower() in (
        "true",
        "1",
        "yes",
    )
    action = (request.form.get("action") or "check-in").strip().lower()

    if not employee_id:
        return jsonify(
            {"status": "error", "message": "Employee ID is required."}
        ), 400

    attendance_method = "face_recognition" if via_face else "manual"

    if action == "check-out":
        result = attendance_service.check_out(employee_id)
        if result.get("status") != "ok":
            return jsonify(result), 400
        return jsonify(
            {
                "status": "ok",
                "message": "Check-out recorded.",
                "via_face": via_face,
                "attendance_method": attendance_method,
                "record_id": result.get("record_id"),
                "action": "check-out",
            }
        )

    # Default: check-in
    result = attendance_service.check_in(
        employee_id, attendance_method=attendance_method
    )
    if result.get("status") != "ok":
        return jsonify(result), 400

    return jsonify(
        {
            "status": "ok",
            "message": "Attendance marked.",
            "via_face": via_face,
            "attendance_method": result.get("attendance_method"),
            "record_id": result.get("record_id"),
            "action": "check-in",
        }
    )


@face_attendance_bp.route("/mark-checkout", methods=["POST"])
def mark_check_out():
    """
    Mark check-out for a recognized (or manually selected) employee.

    Accepts:
        employee_id: The employee's ID string.
        via_face:    "true" if identified via face recognition.
    """
    employee_id = (request.form.get("employee_id") or "").strip()
    via_face = request.form.get("via_face", "false").lower() in (
        "true",
        "1",
        "yes",
    )

    if not employee_id:
        return jsonify(
            {"status": "error", "message": "Employee ID is required."}
        ), 400

    result = attendance_service.check_out(employee_id)
    if result.get("status") != "ok":
        return jsonify(result), 400

    attendance_method = "face_recognition" if via_face else "manual"
    return jsonify(
        {
            "status": "ok",
            "message": "Check-out recorded.",
            "via_face": via_face,
            "attendance_method": attendance_method,
            "record_id": result.get("record_id"),
        }
    )


@face_attendance_bp.route("/check-status", methods=["GET"])
def check_status():
    """
    Check whether an employee has already checked in / out today.

    Query parameters:
        employee_id: The employee's ID string.

    Returns:
        JSON with ``checked_in`` and ``checked_out`` booleans.
    """
    from datetime import date

    employee_id = (request.args.get("employee_id") or "").strip()
    if not employee_id:
        return jsonify(
            {"status": "error", "message": "Employee ID is required."}
        ), 400

    employee = Employee.query.filter_by(employee_id=employee_id).first()
    if not employee:
        return jsonify(
            {"status": "error", "message": "Employee not found."}
        ), 404

    today = date.today()
    record = Attendance.query.filter_by(
        employee_id=employee.id, date=today
    ).first()

    checked_in = record is not None
    checked_out = record is not None and record.check_out_time is not None

    return jsonify(
        {
            "status": "ok",
            "employee": _employee_to_info(employee),
            "checked_in": checked_in,
            "checked_out": checked_out,
            "record_id": record.id if record else None,
        }
    )


@face_attendance_bp.route("/employees", methods=["GET"])
def list_enrollable_employees():
    """List employees for the manual fallback dropdown."""
    employees = Employee.query.order_by(Employee.employee_id).all()
    return jsonify(
        {
            "status": "ok",
            "employees": [_employee_to_info(e) for e in employees],
        }
    )


# ------------------------------------------------------- automatic kiosk mode
@face_attendance_bp.route("/auto-attendance", methods=["GET"])
def auto_attendance_view():
    """Render the automatic (kiosk) attendance page.

    This page auto-starts the webcam, continuously captures frames, detects
    faces, recognizes enrolled employees, and automatically records
    check-in or check-out — no manual button clicks required for the normal
    workflow. A manual Employee-ID fallback is available when recognition
    fails.
    """
    return render_template("auto_attendance.html")


@face_attendance_bp.route("/detect-face", methods=["POST"])
def detect_face():
    """Detect whether a face is present in a camera frame.

    Used by the automatic enrollment page to detect a face before capturing.
    Returns the number of faces detected so the UI can prompt the user to
    ensure only one person is visible.

    Accepts:
        image_data: base64 data-URL of the current video frame.

    Returns:
        JSON with ``face_detected`` (bool), ``face_count`` (int), and
        ``faces`` (list of bounding boxes).
    """
    image_data = request.form.get("image_data") or (
        request.get_json(silent=True) or {}
    ).get("image_data", "")

    image_array = _decode_base64_image(image_data)
    if image_array is None:
        return jsonify(
            {
                "status": "error",
                "message": "Could not decode the captured image.",
            }
        ), 400

    try:
        service = _build_face_service()
        faces = service.detect_faces(image_array)
    except FaceRecognitionError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    return jsonify(
        {
            "status": "ok",
            "face_detected": len(faces) > 0,
            "face_count": len(faces),
            "faces": [{"x": f[0], "y": f[1], "w": f[2], "h": f[3]} for f in faces],
        }
    )


@face_attendance_bp.route("/auto-process", methods=["POST"])
def auto_process():
    """Process a live camera frame for fully automatic attendance.

    This is the core endpoint for the kiosk mode. It:

    1. Detects faces in the frame.
    2. If **multiple** faces are detected, returns a ``multiple_faces`` state
       so the UI can ask the employee to step back / ensure only one person
       is visible.
    3. If **no** face is detected, returns a ``no_face`` state.
    4. If exactly **one** face is detected, runs recognition against all
       enrolled employees.
    5. If the face is **recognized**, checks today's attendance record and
       automatically records check-in (in check-in mode) or check-out (in
       check-out mode) using the existing ``AttendanceService``.
    6. If the face is **not recognized**, returns an ``unknown`` state with
       ``manual: true`` so the UI can offer the manual Employee-ID fallback.

    Duplicate check-ins are prevented both by the database (the
    ``AttendanceService.check_in`` method rejects same-day duplicates) and by
    the frontend cooldown.

    Accepts:
        image_data: base64 data-URL of the current video frame.
        mode:       "check-in" (default) or "check-out".

    Returns:
        JSON describing the recognition result and any attendance action taken.
    """
    image_data = request.form.get("image_data") or (
        request.get_json(silent=True) or {}
    ).get("image_data", "")
    mode = (request.form.get("mode") or "check-in").strip().lower()

    image_array = _decode_base64_image(image_data)
    if image_array is None:
        return jsonify(
            {
                "status": "error",
                "message": "Could not decode the captured image.",
            }
        ), 400

    try:
        service = _build_face_service()
        # Step 1: detect faces to enforce single-face policy.
        faces = service.detect_faces(image_array)
    except FaceRecognitionError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    # Step 2: multiple faces — do NOT pick one randomly.
    if len(faces) > 1:
        return jsonify(
            {
                "status": "ok",
                "recognized": False,
                "message": (
                    "Multiple faces detected. Please ensure only one "
                    "employee is in front of the camera."
                ),
                "multiple_faces": True,
            }
        )

    # Step 3: no face detected.
    if not faces:
        return jsonify(
            {
                "status": "ok",
                "recognized": False,
                "message": "No face detected. Please stand in front of the camera.",
                "no_face": True,
            }
        )

    # Step 4: exactly one face — run recognition.
    result = service.recognize(image_array)

    if not result["recognized"] or not result["employee"]:
        return jsonify(
            {
                "status": "ok",
                "recognized": False,
                "message": result["message"],
                "unknown": True,
                "manual": True,
            }
        )

    employee = result["employee"]
    employee_info = _employee_to_info(employee)
    employee_info["distance"] = result["distance"]

    # Step 5: check today's attendance status and auto-mark.
    today = date.today()
    record = Attendance.query.filter_by(
        employee_id=employee.id, date=today
    ).first()

    checked_in = record is not None
    checked_out = record is not None and record.check_out_time is not None

    if mode == "check-out":
        if not checked_in:
            return jsonify(
                {
                    "status": "ok",
                    "recognized": True,
                    "employee": employee_info,
                    "message": (
                        "No check-in record found for today. "
                        "Check-out is not possible without a prior check-in."
                    ),
                    "no_check_in": True,
                }
            )
        if checked_out:
            return jsonify(
                {
                    "status": "ok",
                    "recognized": True,
                    "employee": employee_info,
                    "already_checked_out": True,
                    "message": "Already checked out today.",
                    "check_out_time": (
                        record.check_out_time.isoformat()
                        if record.check_out_time
                        else None
                    ),
                }
            )
        # Auto check-out
        co_result = attendance_service.check_out(employee.employee_id)
        if co_result.get("status") != "ok":
            return jsonify(
                {
                    "status": "error",
                    "message": co_result.get("message", "Check-out failed."),
                }
            ), 400
        return jsonify(
            {
                "status": "ok",
                "recognized": True,
                "employee": employee_info,
                "action": "check-out",
                "message": "Check-out successful.",
                "check_out_time": co_result.get("check_out_time"),
                "record_id": co_result.get("record_id"),
                "attendance_method": "face_recognition",
            }
        )

    # Default: check-in mode
    if checked_in:
        return jsonify(
            {
                "status": "ok",
                "recognized": True,
                "employee": employee_info,
                "already_checked_in": True,
                "message": "Already checked in today.",
                "check_in_time": (
                    record.check_in_time.isoformat()
                    if record.check_in_time
                    else None
                ),
            }
        )

    # Auto check-in
    ci_result = attendance_service.check_in(
        employee.employee_id, attendance_method="face_recognition"
    )
    if ci_result.get("status") != "ok":
        return jsonify(
            {
                "status": "error",
                "message": ci_result.get("message", "Check-in failed."),
            }
        ), 400

    return jsonify(
        {
            "status": "ok",
            "recognized": True,
            "employee": employee_info,
            "action": "check-in",
            "message": "Check-in successful.",
            "check_in_time": ci_result.get("check_in_time"),
            "record_id": ci_result.get("record_id"),
            "attendance_method": "face_recognition",
        }
    )
