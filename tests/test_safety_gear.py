"""
tests/test_safety_gear.py
========================
Safety gear blueprint tests: upload, detection, and compliance report.

No real trained PPE model ships with the repository, so the app must never
fabricate detection results. These tests verify the check endpoint reports
PPE_MODEL_UNAVAILABLE honestly when no model is configured, and that a real
detector (injected for testing) produces genuine compliance results.

Compliance is based on the required gear: helmet, vest, boots. Gloves is
detected/reported but is NOT required for compliance.
"""

import io

from services.ppe_detector import PPEDetector
from services.safety_gear_service import SafetyGearService


def _make_image_file(filename="worker.png", content=b"\x89PNG\r\n\x1a\nfake-image-data"):
    return (io.BytesIO(content), filename)


class FakePPEDetector(PPEDetector):
    """Deterministic fake detector for exercising the real pipeline."""

    def __init__(self, detections=None):
        self.detections = detections or {}

    def is_available(self):
        return True

    def detect(self, image_path):
        return {
            "detection_status": "completed",
            "helmet_detected": self.detections.get("helmet_detected", False),
            "vest_detected": self.detections.get("vest_detected", False),
            "gloves_detected": self.detections.get("gloves_detected", False),
            "boots_detected": self.detections.get("boots_detected", False),
            "confidence_score": self.detections.get("confidence_score", 75.5),
            "detections": self.detections.get("detections", []),
            "image_path": image_path,
            "message": "PPE detection completed.",
        }


def _inject(client, monkeypatch, detections):
    from routes.safety_gear import _build_service

    def fake_build():
        return SafetyGearService(detector=FakePPEDetector(detections))

    monkeypatch.setattr("routes.safety_gear._build_service", fake_build)


def test_safety_check_page_loads(client):
    resp = client.get("/safety-check/")
    assert resp.status_code == 200
    assert b"Safety Gear Check" in resp.data


def test_ppe_status_no_model(client):
    resp = client.get("/safety-check/status")
    assert resp.status_code == 200
    data = resp.json
    assert data["model_available"] is False
    assert data["ppe_classes"] == ["helmet", "vest", "boots"]
    assert "recommended_model" in data


def test_ppe_status_with_model(client):
    client.application.config["PPE_MODEL_PATH"] = "/models/best.pt"
    resp = client.get("/safety-check/status")
    assert resp.status_code == 200
    assert resp.json["model_available"] is True
    assert resp.json["model_path"] == "/models/best.pt"


def test_ppe_status_with_real_model_reports_mapped_classes(client):
    """With a real model path, status reports the mapped PPE classes and notes
    that 'human' is ignored for compliance."""
    from services.ppe_detector import IGNORED_CLASSES

    client.application.config["PPE_MODEL_PATH"] = "/models/best.pt"
    resp = client.get("/safety-check/status")
    assert resp.status_code == 200
    data = resp.json
    assert data["model_available"] is True
    assert data["ppe_classes"] == ["helmet", "vest", "boots"]
    assert data["ignored_classes"] == sorted(IGNORED_CLASSES)


def test_check_no_file(client):
    resp = client.post("/safety-check/check", data={"employee_id": "PRD-0001"})
    assert resp.status_code == 400
    assert "No file" in resp.json["message"]


def test_check_disallowed_extension(client, register_employee):
    employee_id = register_employee()
    resp = client.post(
        "/safety-check/check",
        data={"employee_id": employee_id, "file": _make_image_file("worker.exe", b"MZ\x90\x00")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "File type not allowed" in resp.json["message"]


def test_check_missing_employee_id(client):
    resp = client.post(
        "/safety-check/check",
        data={"file": _make_image_file()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "Employee ID is required" in resp.json["message"]


def test_check_unknown_employee(client, register_employee, monkeypatch):
    """An upload for a non-existent employee should return an error."""
    # Inject a working detector so the request reaches the employee lookup.
    _inject(client, monkeypatch, {})
    resp = client.post(
        "/safety-check/check",
        data={"employee_id": "NOPE-123", "file": _make_image_file()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 404
    assert resp.json["status"] == "error"


def test_check_no_model_returns_503(client, register_employee):
    """Without a configured model, the check must NOT fabricate results."""
    employee_id = register_employee()
    resp = client.post(
        "/safety-check/check",
        data={"employee_id": employee_id, "file": _make_image_file()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 503
    data = resp.json
    assert data["status"] == "error"
    assert data["code"] == "PPE_MODEL_UNAVAILABLE"
    assert "recommended_model" in data


def test_check_success_with_detector(client, register_employee, monkeypatch):
    """Real detection finding helmet+vest (no boots) yields NON-COMPLIANT."""
    _inject(
        client,
        monkeypatch,
        {
            "helmet_detected": True,
            "vest_detected": True,
            "confidence_score": 82.5,
            "detections": [
                {"class": "helmet", "confidence": 0.91},
                {"class": "vest", "confidence": 0.74},
            ],
        },
    )
    employee_id = register_employee()
    resp = client.post(
        "/safety-check/check",
        data={"employee_id": employee_id, "file": _make_image_file()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["compliant"] is False
    assert data["detected_gear"] == ["helmet", "vest"]
    assert data["missing_gear"] == ["boots"]
    assert data["confidence_score"] == 82.5
    assert data["check_id"] is not None
    assert len(data["detections"]) == 2


def test_check_success_missing_only_gloves_is_compliant(client, register_employee, monkeypatch):
    """Real detection finding helmet+vest+boots (gloves missing) yields COMPLIANT."""
    _inject(
        client,
        monkeypatch,
        {
            "helmet_detected": True,
            "vest_detected": True,
            "gloves_detected": False,
            "boots_detected": True,
            "confidence_score": 90.0,
        },
    )
    employee_id = register_employee()
    resp = client.post(
        "/safety-check/check",
        data={"employee_id": employee_id, "file": _make_image_file()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["compliant"] is True
    assert data["detected_gear"] == ["helmet", "vest", "boots"]
    assert data["missing_gear"] == []


def test_check_success_fully_compliant(client, register_employee, monkeypatch):
    """Real detection finding all required gear (helmet, vest, boots) yields COMPLIANT."""
    _inject(
        client,
        monkeypatch,
        {
            "helmet_detected": True,
            "vest_detected": True,
            "gloves_detected": True,
            "boots_detected": True,
            "confidence_score": 95.0,
        },
    )
    employee_id = register_employee()
    resp = client.post(
        "/safety-check/check",
        data={"employee_id": employee_id, "file": _make_image_file()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["compliant"] is True
    assert data["detected_gear"] == ["helmet", "vest", "boots"]
    assert data["missing_gear"] == []
    assert data["confidence_score"] == 95.0


def test_get_check_result_not_found(client):
    resp = client.get("/safety-check/results/9999")
    assert resp.status_code == 404
    assert resp.json["status"] == "error"


def test_get_check_result_success(client, register_employee, monkeypatch):
    _inject(
        client,
        monkeypatch,
        {"helmet_detected": True, "vest_detected": True, "confidence_score": 80.0},
    )
    employee_id = register_employee()
    check_resp = client.post(
        "/safety-check/check",
        data={"employee_id": employee_id, "file": _make_image_file()},
        content_type="multipart/form-data",
    )
    check_id = check_resp.json["check_id"]
    resp = client.get(f"/safety-check/results/{check_id}")
    assert resp.status_code == 200
    assert resp.json["check"]["id"] == check_id
    assert resp.json["check"]["helmet_detected"] is True
    assert resp.json["check"]["confidence_score"] == 80.0


def test_compliance_report_missing_dates(client):
    resp = client.get("/safety-check/compliance-report")
    assert resp.status_code == 400
    assert "Both start_date and end_date" in resp.json["message"]


def test_compliance_report_invalid_dates(client):
    resp = client.get("/safety-check/compliance-report?start_date=bad&end_date=also-bad")
    assert resp.status_code == 400
    assert "Invalid date format" in resp.json["message"]


def test_compliance_report_invalid_range(client):
    resp = client.get(
        "/safety-check/compliance-report?start_date=2024-12-31&end_date=2024-01-01"
    )
    assert resp.status_code == 400
    assert "before or equal" in resp.json["message"]


def test_compliance_report_success(client):
    resp = client.get(
        "/safety-check/compliance-report?start_date=2024-01-01&end_date=2024-12-31"
    )
    assert resp.status_code == 200
    assert resp.json["report"]["total_checks"] == 0
    assert resp.json["report"]["compliance_rate"] == 0.0


def test_safety_gear_service_evaluate_compliance():
    service = SafetyGearService(detector=FakePPEDetector())
    results = {
        "helmet_detected": True,
        "vest_detected": False,
        "gloves_detected": True,
        "boots_detected": False,
    }
    verdict = service.evaluate_compliance(results)
    assert verdict["is_compliant"] is False
    # Gloves is detected but excluded from the required detected gear.
    assert verdict["detected_gear"] == ["helmet"]
    assert verdict["missing_gear"] == ["vest", "boots"]
