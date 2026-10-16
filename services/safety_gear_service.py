"""
services/safety_gear_service.py
===============================
Business logic for safety gear (PPE) detection and compliance checks.

Integrates with a real computer vision PPE detector (see
``services/ppe_detector.py``). When a trained PPE model is configured, uploaded
images are actually analyzed and structured detections are returned. When no
model is configured, detection is NOT run and NO results are fabricated; the
service raises :class:`PPEDetectionError` so the caller can report that real
detection is unavailable.
"""

from datetime import datetime

from models import db
from models.safety_check import SafetyCheck
from models.employee import Employee
from services.ppe_detector import (
    PPEDetector,
    PPEDetectionError,
    get_ppe_detector,
)


# Required PPE items used for compliance evaluation. Gloves is intentionally
# removed from the required set: an employee is COMPLIANT when helmet + vest +
# boots are detected. Gloves is still detected/reported but does not affect the
# compliance verdict.
REQUIRED_GEAR = ["helmet", "vest", "boots"]


class SafetyGearService:
    """Service class for safety gear detection and compliance logic."""

    def __init__(self, detector=None):
        """
        Args:
            detector: A PPEDetector instance. Defaults to a detector built
                from the current configuration (see ``get_ppe_detector``).
        """
        self.detector = detector if detector is not None else get_ppe_detector()

    def run_detection(self, image_path):
        """
        Run PPE detection on an image using the configured PPEDetector.

        When a real trained model is available, the image is actually analyzed
        and the returned dict reflects only real detections. When no model is
        configured, a :class:`PPEDetectionError` is raised so the caller can
        clearly report that real detection is unavailable.

        Args:
            image_path: Path to the image file to analyze.

        Returns:
            dict: Detection results (detected gear, confidence scores).

        Raises:
            PPEDetectionError: If no real PPE model is configured or the model
                fails to load/run.
        """
        return self.detector.detect(image_path)

    def evaluate_compliance(self, detection_results):
        """
        Determine if the detected gear meets compliance requirements.

        Args:
            detection_results: Output from run_detection.

        Returns:
            dict: Compliance verdict with missing gear list.
        """
        detected = {
            "helmet": detection_results.get("helmet_detected", False),
            "vest": detection_results.get("vest_detected", False),
            "gloves": detection_results.get("gloves_detected", False),
            "boots": detection_results.get("boots_detected", False),
        }
        missing = [gear for gear in REQUIRED_GEAR if not detected[gear]]
        is_compliant = len(missing) == 0

        return {
            "is_compliant": is_compliant,
            "missing_gear": missing,
            # Report only the required gear that was detected. Gloves may be
            # detected but is NOT part of the required compliance set, so it is
            # excluded from the reported detected gear.
            "detected_gear": [
                gear for gear in REQUIRED_GEAR if detected.get(gear, False)
            ],
        }

    def save_check_result(self, employee_id, detection_results, is_compliant):
        """
        Persist a safety check result to the database.

        Args:
            employee_id: Employee identifier (employee_id string).
            detection_results: Detection output.
            is_compliant: Boolean compliance verdict.

        Returns:
            dict: Saved record reference.
        """
        employee = Employee.query.filter_by(employee_id=employee_id).first()
        if not employee:
            return {"status": "error", "message": "Employee not found."}

        record = SafetyCheck(
            employee_id=employee.id,
            check_time=datetime.utcnow(),
            helmet_detected=detection_results.get("helmet_detected", False),
            vest_detected=detection_results.get("vest_detected", False),
            gloves_detected=detection_results.get("gloves_detected", False),
            boots_detected=detection_results.get("boots_detected", False),
            is_compliant=is_compliant,
            image_path=detection_results.get("image_path"),
            confidence_score=detection_results.get("confidence_score"),
        )
        db.session.add(record)
        db.session.commit()

        return {
            "status": "ok",
            "message": "Safety check result saved.",
            "check_id": record.id,
        }

    def get_compliance_report(self, start_date, end_date):
        """
        Generate a compliance report over a date range.

        Args:
            start_date: Report start date.
            end_date: Report end date.

        Returns:
            dict: Aggregated compliance statistics.
        """
        query = SafetyCheck.query.filter(
            SafetyCheck.check_time >= start_date,
            SafetyCheck.check_time <= end_date,
        )
        total = query.count()
        compliant = query.filter(SafetyCheck.is_compliant.is_(True)).count()
        rate = (compliant / total * 100) if total else 0.0

        return {
            "total_checks": total,
            "compliant_checks": compliant,
            "non_compliant_checks": total - compliant,
            "compliance_rate": round(rate, 2),
        }
