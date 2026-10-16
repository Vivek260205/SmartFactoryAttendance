"""
tests/test_face_attendance.py
=============================
Tests for the face attendance blueprint and the face recognition service.

Face detection/recognition depends on OpenCV's YuNet model, which requires a
real image with a detectable face. To keep tests deterministic and
environment-independent, route tests that exercise recognition use a mocked
FaceRecognitionService. The service's pure math (encoding size, distance,
serialization, threshold logic) is tested directly.
"""

import base64
import io

import cv2
import numpy as np
import pytest

from services.face_recognition_service import (
    FaceRecognitionService,
    FaceRecognitionError,
)


def _make_image_file(filename="face.png", content=None):
    """Return a (BytesIO, filename) tuple containing a valid PNG image."""
    if content is None:
        # Generate a valid, realistic image (not blank) so cv2.imread works.
        img = np.full((200, 200, 3), 128, dtype=np.uint8)
        # Add some gradient variation so the image is non-trivial.
        img[:, :, 0] = np.linspace(40, 200, 200, dtype=np.uint8)[None, :]
        img[:, :, 1] = np.linspace(90, 160, 200, dtype=np.uint8)[:, None]
        ok, buf = cv2.imencode(".png", img)
        assert ok
        content = buf.tobytes()
    return (io.BytesIO(content), filename)


def _make_base64_image():
    """Return a base64 data-URL string of a small test image."""
    img = np.full((100, 100, 3), 128, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return "data:image/png;base64," + b64


def _make_large_base64_image(width=1280, height=720):
    """Return a base64 data-URL of a large image (simulating full-res capture).

    Random noise does not compress well in PNG, so this produces a realistically
    large payload similar to what the old frontend sent before the JPEG/resize
    fix. 1280x720 keeps the base64 payload well under the 10 MB
    MAX_CONTENT_LENGTH ceiling.
    """
    img = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return "data:image/png;base64," + b64


class FakeFaceService:
    """Deterministic fake face service for exercising the real routes."""

    def __init__(self, recognized=False, employee=None, no_face=False,
                 cascade_available=True, match_threshold=10.0, multiple_faces=False):
        self.recognized = recognized
        self.employee = employee
        self.no_face = no_face
        self.cascade_available = cascade_available
        self.match_threshold = match_threshold
        self.multiple_faces = multiple_faces

    def detect_faces(self, image_array):
        if self.no_face:
            return []
        if self.multiple_faces:
            return [(10, 10, 100, 100), (200, 200, 80, 80)]
        return [(10, 10, 100, 100)]

    def encode_face(self, image_array):
        return np.arange(16, dtype=np.float32) if not self.no_face else None

    def bytes_to_encoding(self, data):
        return np.frombuffer(data, dtype=np.float32) if data is not None else None

    def match_encoding(self, probe, enrolled):
        return 5.0 if self.recognized else 99.0

    def is_match(self, distance):
        return distance <= self.match_threshold

    def recognize(self, image_array):
        """Fake recognize that returns a result dict matching the real service."""
        if self.no_face:
            return {
                "recognized": False,
                "employee": None,
                "distance": None,
                "message": "No face detected in the image.",
            }
        if self.recognized:
            # Query the DB for the first employee with a face encoding.
            from models.employee import Employee
            emp = Employee.query.filter(
                Employee.face_encoding.isnot(None)
            ).first()
            if emp:
                return {
                    "recognized": True,
                    "employee": emp,
                    "distance": 5.0,
                    "message": "Face recognized.",
                }
        return {
            "recognized": False,
            "employee": None,
            "distance": 99.0,
            "message": (
                "Face detected but did not match any enrolled employee. "
                "Please use the manual fallback."
            ),
        }

    def enroll_from_array(self, employee, image_array):
        """Fake enrollment that always succeeds."""
        employee.face_encoding = np.arange(16, dtype=np.float32).tobytes()
        return {
            "status": "ok",
            "message": "Face enrolled successfully.",
            "encoding_size": len(employee.face_encoding),
        }


def _build_employee(client, employee_id="PRD-0001"):
    """Register an employee and return the employee_id."""
    resp = client.post(
        "/register",
        data={
            "employee_id": employee_id,
            "first_name": "John",
            "last_name": "Doe",
            "department": "Production",
            "shift": "Morning",
        },
    )
    assert resp.status_code == 302
    return employee_id


def _inject_face(client, monkeypatch, **kwargs):
    from routes.face_attendance import _build_face_service

    fake = FakeFaceService(**kwargs)

    def fake_build():
        return fake

    monkeypatch.setattr("routes.face_attendance._build_face_service", fake_build)
    return fake


# ------------------------------------------------------------------ pages
def test_face_attendance_page_loads(client):
    resp = client.get("/face-attendance/")
    assert resp.status_code == 200
    assert b"Face Attendance" in resp.data


def test_face_enroll_page_loads(client):
    resp = client.get("/face-attendance/enroll")
    assert resp.status_code == 200
    assert b"Enroll Employee Face" in resp.data


def test_face_enroll_page_with_employee_id(client):
    resp = client.get("/face-attendance/enroll?employee_id=PRD-0001")
    assert resp.status_code == 200
    assert b"PRD-0001" in resp.data


# ------------------------------------------------------------- enrollment
def test_enroll_missing_employee_id(client):
    resp = client.post(
        "/face-attendance/enroll",
        data={"file": _make_image_file()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "Employee ID is required" in resp.json["message"]


def test_enroll_unknown_employee(client):
    resp = client.post(
        "/face-attendance/enroll",
        data={"employee_id": "NOPE-123", "file": _make_image_file()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 404


def test_enroll_missing_file(client, register_employee):
    employee_id = register_employee()
    resp = client.post(
        "/face-attendance/enroll",
        data={"employee_id": employee_id},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "valid image" in resp.json["message"]


# ----------------------------------------------------- live enrollment
def test_enroll_capture_missing_employee_id(client):
    resp = client.post(
        "/face-attendance/enroll-capture",
        data={"image_data": _make_base64_image()},
    )
    assert resp.status_code == 400
    assert "Employee ID is required" in resp.json["message"]


def test_enroll_capture_unknown_employee(client):
    resp = client.post(
        "/face-attendance/enroll-capture",
        data={"employee_id": "NOPE-123", "image_data": _make_base64_image()},
    )
    assert resp.status_code == 404


def test_enroll_capture_invalid_image(client, register_employee):
    employee_id = register_employee()
    resp = client.post(
        "/face-attendance/enroll-capture",
        data={"employee_id": employee_id, "image_data": "not-a-data-url"},
    )
    assert resp.status_code == 400
    assert "decode" in resp.json["message"].lower()


def test_enroll_capture_success(client, register_employee, monkeypatch):
    employee_id = register_employee()
    _inject_face(client, monkeypatch)
    resp = client.post(
        "/face-attendance/enroll-capture",
        data={"employee_id": employee_id, "image_data": _make_base64_image()},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "ok"
    assert data["employee"]["employee_id"] == employee_id

    # Verify the encoding was persisted.
    with client.application.app_context():
        from models.employee import Employee
        emp = Employee.query.filter_by(employee_id=employee_id).first()
        assert emp.face_encoding is not None


def test_enroll_page_sends_camera_capture_as_jpeg(client):
    """Live enrollment must not submit oversized base64 PNG camera frames."""
    resp = client.get("/face-attendance/enroll?employee_id=PRD-0001")

    assert resp.status_code == 200
    assert b'canvas.toDataURL("image/jpeg", 0.8)' in resp.data
    assert b'canvas.toDataURL("image/png")' not in resp.data


# ------------------------------------------------------------- recognition
def test_recognize_missing_file(client):
    resp = client.post("/face-attendance/recognize", data={})
    assert resp.status_code == 400
    assert "valid image" in resp.json["message"]


def test_recognize_no_face(client, register_employee, monkeypatch):
    _build_employee(client)
    _inject_face(client, monkeypatch, no_face=True)
    resp = client.post(
        "/face-attendance/recognize",
        data={"file": _make_image_file()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "ok"
    assert data["recognized"] is False
    assert data["manual"] is True


def test_recognize_unknown_person(client, register_employee, monkeypatch):
    _build_employee(client)
    _inject_face(client, monkeypatch, recognized=False)
    resp = client.post(
        "/face-attendance/recognize",
        data={"file": _make_image_file()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["recognized"] is False
    assert data["manual"] is True


def test_recognize_matched_employee(client, register_employee, monkeypatch):
    _build_employee(client)

    # The matching loop only considers employees with a stored face encoding.
    # Enroll PRD-0001 by writing a face encoding directly so the loop finds it.
    with client.application.app_context():
        from models import db
        from models.employee import Employee

        emp = Employee.query.filter_by(employee_id="PRD-0001").first()
        emp.face_encoding = np.arange(16, dtype=np.float32).tobytes()
        db.session.commit()

    _inject_face(client, monkeypatch, recognized=True)
    resp = client.post(
        "/face-attendance/recognize",
        data={"file": _make_image_file()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["recognized"] is True
    assert data["employee"]["employee_id"] == "PRD-0001"
    assert data["employee"]["first_name"] == "John"
    assert data["manual"] is False


def test_recognize_face_service_error(client, register_employee, monkeypatch):
    """A face-service failure should be reported as a 500, not crash."""
    _build_employee(client)

    def boom():
        raise FaceRecognitionError("cascade missing")

    monkeypatch.setattr("routes.face_attendance._build_face_service", boom)
    resp = client.post(
        "/face-attendance/recognize",
        data={"file": _make_image_file()},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 500


# ----------------------------------------------------- live recognition
def test_capture_missing_image(client):
    resp = client.post("/face-attendance/capture", data={})
    assert resp.status_code == 400
    assert "decode" in resp.json["message"].lower()


def test_capture_no_face(client, register_employee, monkeypatch):
    _build_employee(client)
    _inject_face(client, monkeypatch, no_face=True)
    resp = client.post(
        "/face-attendance/capture",
        data={"image_data": _make_base64_image()},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["recognized"] is False
    assert data["manual"] is True


def test_capture_unknown_person(client, register_employee, monkeypatch):
    _build_employee(client)
    _inject_face(client, monkeypatch, recognized=False)
    resp = client.post(
        "/face-attendance/capture",
        data={"image_data": _make_base64_image()},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["recognized"] is False
    assert data["manual"] is True


def test_capture_matched_employee(client, register_employee, monkeypatch):
    _build_employee(client)

    with client.application.app_context():
        from models import db
        from models.employee import Employee

        emp = Employee.query.filter_by(employee_id="PRD-0001").first()
        emp.face_encoding = np.arange(16, dtype=np.float32).tobytes()
        db.session.commit()

    _inject_face(client, monkeypatch, recognized=True)
    resp = client.post(
        "/face-attendance/capture",
        data={"image_data": _make_base64_image()},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["recognized"] is True
    assert data["employee"]["employee_id"] == "PRD-0001"
    assert data["manual"] is False


def test_capture_large_image_no_413(client, register_employee, monkeypatch):
    """A large (but under-limit) image must not trigger HTTP 413.

    This simulates the old frontend sending a full-resolution PNG frame.
    With MAX_CONTENT_LENGTH set to 10 MB the request should be accepted
    (not rejected with 413) and processed normally.
    """
    _build_employee(client)
    _inject_face(client, monkeypatch, no_face=True)
    large_data_url = _make_large_base64_image()
    resp = client.post(
        "/face-attendance/capture",
        data={"image_data": large_data_url},
    )
    assert resp.status_code != 413
    assert resp.status_code == 200


def test_capture_oversized_image_returns_413(client, register_employee, monkeypatch):
    """A payload exceeding MAX_CONTENT_LENGTH (10 MB) must return HTTP 413."""
    _build_employee(client)
    _inject_face(client, monkeypatch, no_face=True)
    # Build a data-URL whose base64 payload alone exceeds 10 MB.
    oversized = "data:image/png;base64," + ("A" * (11 * 1024 * 1024))
    resp = client.post(
        "/face-attendance/capture",
        data={"image_data": oversized},
    )
    assert resp.status_code == 413


# ------------------------------------------------------------------ mark
def test_mark_missing_employee_id(client):
    resp = client.post("/face-attendance/mark", data={})
    assert resp.status_code == 400
    assert "Employee ID is required" in resp.json["message"]


def test_mark_unknown_employee(client):
    resp = client.post("/face-attendance/mark", data={"employee_id": "NOPE-123"})
    assert resp.status_code == 400
    assert "not found" in resp.json["message"]


def test_mark_attendance_recognized(client, register_employee):
    _build_employee(client)
    resp = client.post(
        "/face-attendance/mark",
        data={"employee_id": "PRD-0001", "via_face": "true"},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "ok"
    assert data["via_face"] is True
    assert data["attendance_method"] == "face_recognition"
    assert "record_id" in data

    # Verify the method is persisted on the attendance record.
    with client.application.app_context():
        from models.attendance import Attendance

        record = Attendance.query.first()
        assert record is not None
        assert record.attendance_method == "face_recognition"


def test_mark_attendance_manual(client, register_employee):
    _build_employee(client)
    resp = client.post(
        "/face-attendance/mark",
        data={"employee_id": "PRD-0001", "via_face": "false"},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "ok"
    assert data["via_face"] is False
    assert data["attendance_method"] == "manual"

    # Verify the method is persisted on the attendance record.
    with client.application.app_context():
        from models.attendance import Attendance

        record = Attendance.query.first()
        assert record is not None
        assert record.attendance_method == "manual"


def test_mark_check_out_face(client, register_employee):
    """Check-out via face recognition should record check-out."""
    _build_employee(client)
    # First check-in
    client.post(
        "/attendance/check-in",
        data={"employee_id": "PRD-0001"},
    )
    # Then check-out via face
    resp = client.post(
        "/face-attendance/mark",
        data={"employee_id": "PRD-0001", "via_face": "true", "action": "check-out"},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "ok"
    assert data["action"] == "check-out"

    # Verify check-out time was set
    with client.application.app_context():
        from models.attendance import Attendance
        record = Attendance.query.first()
        assert record.check_out_time is not None


def test_mark_check_out_manual(client, register_employee):
    """Check-out via manual fallback should record check-out."""
    _build_employee(client)
    client.post(
        "/attendance/check-in",
        data={"employee_id": "PRD-0001"},
    )
    resp = client.post(
        "/face-attendance/mark",
        data={"employee_id": "PRD-0001", "via_face": "false", "action": "check-out"},
    )
    assert resp.status_code == 200
    assert resp.json["action"] == "check-out"


def test_mark_check_out_without_check_in(client, register_employee):
    """Check-out without prior check-in should return an error."""
    _build_employee(client)
    resp = client.post(
        "/face-attendance/mark",
        data={"employee_id": "PRD-0001", "via_face": "true", "action": "check-out"},
    )
    assert resp.status_code == 400
    assert "No check-in" in resp.json["message"]


def test_mark_checkout_endpoint(client, register_employee):
    """The /mark-checkout endpoint should record check-out."""
    _build_employee(client)
    client.post(
        "/attendance/check-in",
        data={"employee_id": "PRD-0001"},
    )
    resp = client.post(
        "/face-attendance/mark-checkout",
        data={"employee_id": "PRD-0001", "via_face": "true"},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "ok"
    assert data["attendance_method"] == "face_recognition"


def test_mark_checkout_missing_employee_id(client):
    resp = client.post("/face-attendance/mark-checkout", data={})
    assert resp.status_code == 400
    assert "Employee ID is required" in resp.json["message"]


# ------------------------------------------------------------- check-status
def test_check_status_missing_employee_id(client):
    resp = client.get("/face-attendance/check-status")
    assert resp.status_code == 400
    assert "Employee ID is required" in resp.json["message"]


def test_check_status_unknown_employee(client):
    resp = client.get("/face-attendance/check-status?employee_id=NOPE-123")
    assert resp.status_code == 404


def test_check_status_not_checked_in(client, register_employee):
    employee_id = register_employee()
    resp = client.get(f"/face-attendance/check-status?employee_id={employee_id}")
    assert resp.status_code == 200
    data = resp.json
    assert data["checked_in"] is False
    assert data["checked_out"] is False


def test_check_status_checked_in_not_out(client, register_employee):
    employee_id = register_employee()
    client.post("/attendance/check-in", data={"employee_id": employee_id})
    resp = client.get(f"/face-attendance/check-status?employee_id={employee_id}")
    assert resp.status_code == 200
    data = resp.json
    assert data["checked_in"] is True
    assert data["checked_out"] is False


def test_check_status_checked_out(client, register_employee):
    employee_id = register_employee()
    client.post("/attendance/check-in", data={"employee_id": employee_id})
    client.post("/attendance/check-out", data={"employee_id": employee_id})
    resp = client.get(f"/face-attendance/check-status?employee_id={employee_id}")
    assert resp.status_code == 200
    data = resp.json
    assert data["checked_in"] is True
    assert data["checked_out"] is True


# ------------------------------------------------------------- employees list
def test_list_enrollable_employees(client, register_employee):
    _build_employee(client)
    resp = client.get("/face-attendance/employees")
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "ok"
    assert len(data["employees"]) == 1
    assert data["employees"][0]["employee_id"] == "PRD-0001"


# ------------------------------------------------------- auto-attendance page
def test_auto_attendance_page_loads(client):
    """The automatic kiosk attendance page should render successfully at /auto-attendance."""
    resp = client.get("/auto-attendance")
    assert resp.status_code == 200
    assert b"SMART FACTORY ATTENDANCE" in resp.data


def test_auto_attendance_page_loads_blueprint_alias(client):
    """The /face-attendance/auto-attendance alias should also work."""
    resp = client.get("/face-attendance/auto-attendance")
    assert resp.status_code == 200
    assert b"SMART FACTORY ATTENDANCE" in resp.data


# ------------------------------------------------------- detect-face endpoint
def test_detect_face_missing_image(client):
    resp = client.post("/face-attendance/detect-face", data={})
    assert resp.status_code == 400
    assert "decode" in resp.json["message"].lower()


def test_detect_face_no_face(client, register_employee, monkeypatch):
    _build_employee(client)
    _inject_face(client, monkeypatch, no_face=True)
    resp = client.post(
        "/face-attendance/detect-face",
        data={"image_data": _make_base64_image()},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["face_detected"] is False
    assert data["face_count"] == 0


def test_detect_face_single_face(client, register_employee, monkeypatch):
    _build_employee(client)
    _inject_face(client, monkeypatch, recognized=False)
    resp = client.post(
        "/face-attendance/detect-face",
        data={"image_data": _make_base64_image()},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["face_detected"] is True
    assert data["face_count"] == 1


def test_detect_face_multiple_faces(client, register_employee, monkeypatch):
    _build_employee(client)
    _inject_face(client, monkeypatch, multiple_faces=True)
    resp = client.post(
        "/face-attendance/detect-face",
        data={"image_data": _make_base64_image()},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["face_detected"] is True
    assert data["face_count"] == 2


# ------------------------------------------------------- auto-process endpoint
def _enroll_face(client, employee_id="PRD-0001"):
    """Write a face encoding directly to the employee record for testing."""
    with client.application.app_context():
        from models import db
        from models.employee import Employee

        emp = Employee.query.filter_by(employee_id=employee_id).first()
        emp.face_encoding = np.arange(16, dtype=np.float32).tobytes()
        db.session.commit()


def test_auto_process_missing_image(client):
    resp = client.post("/face-attendance/auto-process", data={})
    assert resp.status_code == 400
    assert "decode" in resp.json["message"].lower()


def test_auto_process_no_face(client, register_employee, monkeypatch):
    _build_employee(client)
    _inject_face(client, monkeypatch, no_face=True)
    resp = client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-in"},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["recognized"] is False
    assert data["no_face"] is True


def test_auto_process_multiple_faces(client, register_employee, monkeypatch):
    _build_employee(client)
    _inject_face(client, monkeypatch, multiple_faces=True)
    resp = client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-in"},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["recognized"] is False
    assert data["multiple_faces"] is True


def test_auto_process_unknown_face(client, register_employee, monkeypatch):
    _build_employee(client)
    _inject_face(client, monkeypatch, recognized=False)
    resp = client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-in"},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["recognized"] is False
    assert data["unknown"] is True
    assert data["manual"] is True


def test_auto_process_check_in_success(client, register_employee, monkeypatch):
    """Recognized employee in check-in mode should auto-create a check-in record."""
    _build_employee(client)
    _enroll_face(client)
    _inject_face(client, monkeypatch, recognized=True)
    resp = client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-in"},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "ok"
    assert data["recognized"] is True
    assert data["action"] == "check-in"
    assert data["attendance_method"] == "face_recognition"
    assert "check_in_time" in data
    assert "record_id" in data

    # Verify the record was persisted with face_recognition method
    with client.application.app_context():
        from models.attendance import Attendance
        record = Attendance.query.first()
        assert record is not None
        assert record.attendance_method == "face_recognition"
        assert record.check_out_time is None


def test_auto_process_check_in_duplicate(client, register_employee, monkeypatch):
    """A second auto-process for the same employee on the same day should
    report already_checked_in without creating a duplicate record."""
    _build_employee(client)
    _enroll_face(client)
    _inject_face(client, monkeypatch, recognized=True)

    # First check-in
    resp = client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-in"},
    )
    assert resp.status_code == 200
    assert resp.json["action"] == "check-in"

    # Second attempt — should report already checked in
    resp = client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-in"},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["recognized"] is True
    assert data["already_checked_in"] is True

    # Verify only one record exists
    with client.application.app_context():
        from models.attendance import Attendance
        assert Attendance.query.count() == 1


def test_auto_process_check_out_success(client, register_employee, monkeypatch):
    """Recognized employee in check-out mode (after check-in) should auto-record check-out."""
    _build_employee(client)
    _enroll_face(client)
    _inject_face(client, monkeypatch, recognized=True)

    # First check-in
    client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-in"},
    )

    # Then check-out
    resp = client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-out"},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "ok"
    assert data["recognized"] is True
    assert data["action"] == "check-out"
    assert data["attendance_method"] == "face_recognition"
    assert "check_out_time" in data

    # Verify check-out time was set
    with client.application.app_context():
        from models.attendance import Attendance
        record = Attendance.query.first()
        assert record.check_out_time is not None


def test_auto_process_check_out_without_check_in(client, register_employee, monkeypatch):
    """Check-out without prior check-in should report no_check_in."""
    _build_employee(client)
    _enroll_face(client)
    _inject_face(client, monkeypatch, recognized=True)
    resp = client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-out"},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["recognized"] is True
    assert data["no_check_in"] is True


def test_auto_process_check_out_already_checked_out(client, register_employee, monkeypatch):
    """Already checked-out employee should report already_checked_out."""
    _build_employee(client)
    _enroll_face(client)
    _inject_face(client, monkeypatch, recognized=True)

    # Check-in then check-out
    client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-in"},
    )
    client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-out"},
    )

    # Third attempt in check-out mode — should report already checked out
    resp = client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-out"},
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["recognized"] is True
    assert data["already_checked_out"] is True


def test_auto_process_face_service_error(client, register_employee, monkeypatch):
    """A face-service failure should be reported as a 500, not crash."""
    _build_employee(client)

    def boom():
        raise FaceRecognitionError("cascade missing")

    monkeypatch.setattr("routes.face_attendance._build_face_service", boom)
    resp = client.post(
        "/face-attendance/auto-process",
        data={"image_data": _make_base64_image(), "mode": "check-in"},
    )
    assert resp.status_code == 500


# ------------------------------------------------------------- service maths
def test_service_is_available_with_cascade():
    service = FaceRecognitionService()
    # Encoding vector size = 64*64
    enc = np.zeros(64 * 64, dtype=np.float32)
    assert service.encoding_to_bytes(enc) is not None


def test_encoding_roundtrip():
    service = FaceRecognitionService()
    enc = np.arange(100, dtype=np.float32)
    data = service.encoding_to_bytes(enc)
    back = service.bytes_to_encoding(data)
    assert np.allclose(enc, back)


def test_match_distance_and_threshold():
    service = FaceRecognitionService(match_threshold=10.0)
    a = np.zeros(64 * 64, dtype=np.float32)
    # Tiny perturbation across a few elements keeps distance below threshold.
    b = a.copy()
    b[:5] += 1.0
    distance = service.match_encoding(a, b)
    assert distance > 0
    assert service.is_match(distance) is True

    # Large perturbation across all elements far exceeds the threshold.
    far = a + 1000.0
    assert service.is_match(service.match_encoding(a, far)) is False


def test_service_raises_on_missing_model(tmp_path):
    """When both YuNet and Haar cascade are unavailable, detect_faces raises."""
    missing_yunet = str(tmp_path / "nonexistent.onnx")
    missing_cascade = str(tmp_path / "nonexistent.xml")
    service = FaceRecognitionService(
        yunet_model_path=missing_yunet, cascade_path=missing_cascade
    )
    with pytest.raises(FaceRecognitionError):
        service.detect_faces(np.zeros((50, 50, 3), dtype=np.uint8))
