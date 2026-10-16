"""
tests/test_dashboard.py
=======================
Tests for the dashboard blueprint: stats and alerts endpoints.
"""


def test_dashboard_page_loads(client):
    """The dashboard page should render successfully."""
    resp = client.get("/dashboard/")
    assert resp.status_code == 200
    assert b"Dashboard" in resp.data


def test_stats_empty(client):
    """Initial dashboard stats should be all zeros."""
    resp = client.get("/dashboard/stats")
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "ok"
    assert data["present_count"] == 0
    assert data["compliance_rate"] == 0.0
    assert data["alerts_count"] == 0


def test_stats_with_active_employee(client, register_employee):
    """A checked-in employee (no check-out) should count as present."""
    employee_id = register_employee()
    client.post("/attendance/check-in", data={"employee_id": employee_id})

    resp = client.get("/dashboard/stats")
    assert resp.status_code == 200
    assert resp.json["present_count"] == 1


def test_stats_after_check_out(client, register_employee):
    """An employee who checked out should no longer count as present."""
    employee_id = register_employee()
    client.post("/attendance/check-in", data={"employee_id": employee_id})
    client.post("/attendance/check-out", data={"employee_id": employee_id})

    resp = client.get("/dashboard/stats")
    assert resp.status_code == 200
    assert resp.json["present_count"] == 0


def test_alerts_empty(client):
    """The alerts endpoint should return an empty list initially."""
    resp = client.get("/dashboard/alerts")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert resp.json["alerts"] == []