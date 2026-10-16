"""
tests/test_main.py
==================
Tests for the main blueprint: home page and employee registration.
"""


def test_index_page_loads(client):
    """The home page should render successfully."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Smart Factory Attendance" in resp.data


def test_register_page_loads(client):
    """The registration page should render successfully."""
    resp = client.get("/register")
    assert resp.status_code == 200
    assert b"Employee Registration" in resp.data


def test_register_employee_success(client):
    """A valid registration should redirect after creating the employee."""
    resp = client.post(
        "/register",
        data={
            "employee_id": "PRD-0001",
            "first_name": "John",
            "last_name": "Doe",
            "department": "Production",
            "shift": "Morning",
        },
    )
    assert resp.status_code == 302


def test_register_employee_missing_fields(client):
    """Registration with missing fields should re-render with errors."""
    resp = client.post(
        "/register",
        data={
            "employee_id": "",
            "first_name": "",
            "last_name": "Doe",
            "department": "Production",
            "shift": "Morning",
        },
    )
    assert resp.status_code == 200
    assert b"First name is required" in resp.data


def test_register_duplicate_employee_id(client):
    """Registering the same employee ID twice should show an error."""
    payload = {
        "employee_id": "PRD-0001",
        "first_name": "John",
        "last_name": "Doe",
        "department": "Production",
        "shift": "Morning",
    }
    client.post("/register", data=payload)

    resp = client.post(
        "/register",
        data={
            "employee_id": "PRD-0001",
            "first_name": "Jane",
            "last_name": "Smith",
            "department": "Quality",
            "shift": "Night",
        },
    )
    assert resp.status_code == 200
    assert b"already exists" in resp.data


def test_list_employees_empty(client):
    """The employees endpoint should return an empty list initially."""
    resp = client.get("/employees")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert resp.json["employees"] == []


def test_list_employees_after_registration(client, register_employee):
    """Registered employees should appear in the listing."""
    employee_id = register_employee()
    resp = client.get("/employees")
    assert resp.status_code == 200
    employees = resp.json["employees"]
    assert len(employees) == 1
    assert employees[0]["employee_id"] == employee_id
    assert employees[0]["first_name"] == "John"
    assert employees[0]["department"] == "Production"


def test_list_employees_filter_by_department(client, register_employee):
    """Employees should be filterable by department (case-insensitive)."""
    register_employee()
    register_employee(
        employee_id="QC-0002",
        first_name="Jane",
        last_name="Smith",
        department="Quality",
        shift="Night",
    )

    resp = client.get("/employees?department=quality")
    assert resp.status_code == 200
    employees = resp.json["employees"]
    assert len(employees) == 1
    assert employees[0]["employee_id"] == "QC-0002"


def test_list_employees_filter_by_active(client, register_employee):
    """Employees should be filterable by active status."""
    register_employee()
    resp = client.get("/employees?active=false")
    assert resp.status_code == 200
    assert resp.json["employees"] == []

    resp = client.get("/employees?active=true")
    assert resp.status_code == 200
    assert len(resp.json["employees"]) == 1
