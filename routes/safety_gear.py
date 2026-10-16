"""
routes/safety_gear.py
=====================
Route handlers for safety gear (PPE) detection and compliance checks.

The safety check page is served at "/safety-check/" and the API endpoints for
running checks, retrieving results, and compliance reports share the prefix.

Detection is performed by the configured PPEDetector (see
``services/ppe_detector.py``). When no trained PPE model is configured, the
check endpoint returns a clear 503 response instead of fabricating detection
results.
"""

from datetime import datetime
import os

from flask import Blueprint, current_app, request, jsonify, render_template

from models.employee import Employee

from models.safety_check import SafetyCheck
from services.ppe_detector import (
    IGNORED_CLASSES,
    PPEDetectionError,
    get_ppe_detector,
    RECOMMENDED_MODEL,
)
from services.safety_gear_service import SafetyGearService
from utils.helpers import allowed_file, save_upload
from utils.validators import validate_date_range

# Create the safety gear blueprint (mounted at /safety-check)
safety_gear_bp = Blueprint("safety_gear", __name__, url_prefix="/safety-check")


def _build_service():
    """Build a SafetyGearService bound to the configured PPE model path."""
    model_path = current_app.config.get("PPE_MODEL_PATH", "")
    confidence_threshold = current_app.config.get(
        "PPE_CONFIDENCE_THRESHOLD", 0.35
    )
    detector = get_ppe_detector(model_path, confidence_threshold)
    return SafetyGearService(detector=detector)


@safety_gear_bp.route("/")
def safety_gear_view():
    """Render the safety gear check page."""
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.employee_id).all()
    return render_template("safety_check.html", employees=employees)



@safety_gear_bp.route("/status", methods=["GET"])
def ppe_detector_status():
    """
    Report whether a real PPE detection model is configured.

    Returns:
        JSON with model_available, model_path (if configured), and the
        recommended model specification when no model is available.
    """
    model_path = current_app.config.get("PPE_MODEL_PATH", "")
    available = bool(model_path)
    return jsonify(
        {
            "status": "ok",
            "model_available": available,
            "model_path": model_path or None,
            "recommended_model": None if available else RECOMMENDED_MODEL,
            "ppe_classes": ["helmet", "vest", "boots"],
            "ignored_classes": sorted(IGNORED_CLASSES),
        }
    )


@safety_gear_bp.route("/check", methods=["POST"])
def run_safety_check():
    """
    Run a safety gear compliance check on an uploaded image/video.

    Validates the upload, saves the file, runs real PPE detection (when a
    trained model is configured), evaluates compliance, and persists the
    result to the database. When no model is available, no detection is
    performed and no result is persisted.
    """
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded."}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"status": "error", "message": "No file selected."}), 400

    # Validate file extension against the configured allowed set.
    allowed_extensions = current_app.config.get("ALLOWED_EXTENSIONS", set())
    if not allowed_file(file.filename, allowed_extensions):
        return jsonify(
            {
                "status": "error",
                "message": "File type not allowed. Use PNG, JPG, JPEG, or MP4.",
            }
        ), 400

    employee_id = request.form.get("employee_id")
    if not employee_id:
        return jsonify({"status": "error", "message": "Employee ID is required."}), 400

    # Persist the uploaded file to the uploads folder
    upload_folder = current_app.config.get("UPLOAD_FOLDER")
    saved_path = save_upload(file, upload_folder)

    if not saved_path:
        return jsonify({"status": "error", "message": "Failed to save upload."}), 500

    service = _build_service()

    # Run detection using the configured PPE model. When no real model is
    # configured (or it cannot run), report honestly instead of fabricating
    # detection results.
    try:
        detection_results = service.run_detection(saved_path)
    except PPEDetectionError as exc:
        return jsonify(
            {
                "status": "error",
                "code": "PPE_MODEL_UNAVAILABLE",
                "message": str(exc),
                "recommended_model": RECOMMENDED_MODEL,
            }
        ), 503

    # Evaluate compliance and persist the real detection result
    compliance = service.evaluate_compliance(detection_results)
    saved = service.save_check_result(
        employee_id,
        detection_results,
        compliance.get("is_compliant", False),
    )

    if saved.get("status") != "ok":
        return jsonify(saved), 404

    base_orig = os.path.basename(saved_path)
    annotated_path = detection_results.get("annotated_image_path")
    annotated_url = f"/static/uploads/{os.path.basename(annotated_path)}" if annotated_path else None
    image_url = f"/static/uploads/{base_orig}"

    return jsonify(
        {
            "status": "ok",
            "message": "Safety check completed.",
            "employee_id": employee_id,
            "check_id": saved.get("check_id"),
            "compliant": compliance.get("is_compliant", False),
            "detected_gear": compliance.get("detected_gear", []),
            "missing_gear": compliance.get("missing_gear", []),
            "confidence_score": detection_results.get("confidence_score", 0.0),
            "detections": detection_results.get("detections", []),
            "image_path": saved_path,
            "image_url": image_url,
            "annotated_image_url": annotated_url,
        }
    )



@safety_gear_bp.route("/results/<int:check_id>", methods=["GET"])
def get_check_result(check_id):
    """
    Retrieve the result of a specific safety gear check.

    Args:
        check_id: Database ID of the safety check record.
    """
    record = SafetyCheck.query.get(check_id)
    if not record:
        return jsonify({"status": "error", "message": "Safety check not found."}), 404

    return jsonify({"status": "ok", "check": record.to_dict()})


@safety_gear_bp.route("/compliance-report", methods=["GET"])
def compliance_report():
    """
    Generate a compliance report over a date range.

    Query parameters:
        start_date: Report start date (YYYY-MM-DD).
        end_date:   Report end date (YYYY-MM-DD).
    """
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if not start_date or not end_date:
        return jsonify(
            {"status": "error", "message": "Both start_date and end_date are required."}
        ), 400

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return jsonify(
            {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD."}
        ), 400

    if not validate_date_range(start, end):
        return jsonify(
            {
                "status": "error",
                "message": "start_date must be before or equal to end_date.",
            }
        ), 400

    report = _build_service().get_compliance_report(start, end)
    return jsonify({"status": "ok", "report": report})


@safety_gear_bp.route("/history", methods=["GET"])
def safety_check_history():
    """
    Retrieve real safety check records with worker names and image previews.

    Optional query parameters:
        employee_id: Filter by employee ID string.
        limit: Max records to return (default 25).
    """
    employee_id_str = request.args.get("employee_id")
    limit = request.args.get("limit", 25, type=int)

    query = SafetyCheck.query
    if employee_id_str:
        emp = Employee.query.filter_by(employee_id=employee_id_str).first()
        if emp:
            query = query.filter_by(employee_id=emp.id)
        else:
            return jsonify({"status": "ok", "history": []})

    records = query.order_by(SafetyCheck.check_time.desc()).limit(limit).all()
    history = []
    for r in records:
        emp = Employee.query.get(r.employee_id)
        d = r.to_dict()
        d["employee_id_str"] = emp.employee_id if emp else f"ID-{r.employee_id}"
        d["employee_name"] = f"{emp.first_name} {emp.last_name}" if emp else "Unknown Worker"
        d["department"] = emp.department if emp else "-"
        if r.image_path:
            d["image_url"] = f"/static/uploads/{os.path.basename(r.image_path)}"
        history.append(d)

    return jsonify({"status": "ok", "history": history})

