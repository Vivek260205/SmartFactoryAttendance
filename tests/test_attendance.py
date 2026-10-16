"""
tests/test_attendance.py
========================
Tests for the attendance blueprint: check-in, check-out, and records.
"""


def test_attendance_page_loads(client):
    """The attendance page should render successfully."""
    resp = client.get("/attendance/")
    assert resp.status_code == 200
    assert b"Attendance Management" in resp.data


def test_check_in_missing_employee_id(client):
    """Check-in without an employee ID should return an error."""
    resp = client.post("/attendance/check-in", data={})
    assert resp.status_code == 400
    assert resp.json["status"] == "error"
    assert "Employee ID is required" in resp.json["message"]


def test_check_in_unknown_employee(client):
    """Check-in for a non-existent employee should return an error."""
    resp = client.post("/attendance/check-in", data={"employee_id": "NOPE-123"})
    assert resp.status_code == 400
    assert resp.json["status"] == "error"
    assert "not found" in resp.json["message"].lower()


def test_check_in_success(client, register_employee):
    """A valid check-in should create an attendance record."""
    employee_id = register_employee()
    resp = client.post("/attendance/check-in", data={"employee_id": employee_id})
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert "record_id" in resp.json


def test_check_in_default_method_is_manual(client, register_employee):
    """A check-in without a method should default to 'manual'."""
    employee_id = register_employee()
    client.post("/attendance/check-in", data={"employee_id": employee_id})

    resp = client.get("/attendance/records")
    assert resp.status_code == 200
    records = resp.json["records"]
    assert len(records) == 1
    assert records[0]["attendance_method"] == "manual"


def test_check_in_duplicate(client, register_employee):
    """A second check-in on the same day should be rejected."""
    employee_id = register_employee()
    client.post("/attendance/check-in", data={"employee_id": employee_id})

    resp = client.post("/attendance/check-in", data={"employee_id": employee_id})
    assert resp.status_code == 400
    assert resp.json["status"] == "error"
    assert "already checked in" in resp.json["message"]


def test_check_out_missing_employee_id(client):
    """Check-out without an employee ID should return an error."""
    resp = client.post("/attendance/check-out", data={})
    assert resp.status_code == 400
    assert resp.json["status"] == "error"


def test_check_out_without_check_in(client, register_employee):
    """Check-out before any check-in should return an error."""
    employee_id = register_employee()
    resp = client.post("/attendance/check-out", data={"employee_id": employee_id})
    assert resp.status_code == 400
    assert "No check-in record" in resp.json["message"]


def test_check_out_success(client, register_employee):
    """A valid check-out after check-in should update the record."""
    employee_id = register_employee()
    client.post("/attendance/check-in", data={"employee_id": employee_id})

    resp = client.post("/attendance/check-out", data={"employee_id": employee_id})
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"


def test_get_records_empty(client):
    """The records endpoint should return an empty list initially."""
    resp = client.get("/attendance/records")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert resp.json["records"] == []


def test_get_records_with_check_in(client, register_employee):
    """Records should appear after a check-in with employee info attached."""
    employee_id = register_employee()
    client.post("/attendance/check-in", data={"employee_id": employee_id})

    resp = client.get("/attendance/records")
    assert resp.status_code == 200
    records = resp.json["records"]
    assert len(records) == 1
    assert records[0]["employee_id"] == employee_id
    assert records[0]["employee_name"] == "John Doe"


def test_get_records_filter_by_employee(client, register_employee):
    """Records should be filterable by employee ID string."""
    employee_id = register_employee()
    client.post("/attendance/check-in", data={"employee_id": employee_id})

    resp = client.get(f"/attendance/records?employee_id={employee_id}")
    assert resp.status_code == 200
    assert len(resp.json["records"]) == 1

    resp = client.get("/attendance/records?employee_id=WRONG-999")
    assert resp.status_code == 200
    assert resp.json["records"] == []


def test_get_records_invalid_date(client):
    """An invalid date filter should return a 400 error."""
    resp = client.get("/attendance/records?date=not-a-date")
    assert resp.status_code == 400
    assert "Invalid date format" in resp.json["message"]