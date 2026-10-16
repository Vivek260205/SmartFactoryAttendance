"""
routes/dashboard.py
===================
Route handlers for the main dashboard (overview of attendance & safety).
"""

from datetime import date, datetime, time

from flask import Blueprint, jsonify, render_template

from models.attendance import Attendance
from models.employee import Employee
from models.safety_check import SafetyCheck
from services.notification_service import NotificationService
from services.safety_gear_service import SafetyGearService

# Create the dashboard blueprint
dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

# Shared service instances
safety_gear_service = SafetyGearService()
notification_service = NotificationService()


@dashboard_bp.route("/")
def dashboard_view():
    """Render the main dashboard page."""
    return render_template("dashboard.html")


@dashboard_bp.route("/stats", methods=["GET"])
def dashboard_stats():
    """
    Return dashboard statistics as JSON (for AJAX / API consumers).

    Statistics include the number of employees currently present, the safety
    compliance rate for today, and the count of active alerts.
    """
    today = date.today()

    # Employees present = checked in today with no check-out time
    present_count = Attendance.query.filter(
        Attendance.date == today,
        Attendance.check_out_time.is_(None),
    ).count()

    # Safety compliance rate for today
    start_of_day = datetime.combine(today, time.min)
    now = datetime.utcnow()
    report = safety_gear_service.get_compliance_report(start_of_day, now)
    compliance_rate = report.get("compliance_rate", 0.0)

    total_employees = Employee.query.filter_by(is_active=True).count()
    checked_in_today = Attendance.query.filter(Attendance.date == today).count()
    absent_count = max(0, total_employees - checked_in_today)
    attendance_pct = round((checked_in_today / total_employees * 100), 1) if total_employees > 0 else 0.0

    total_ppe_checks = SafetyCheck.query.count()
    todays_ppe_checks = SafetyCheck.query.filter(
        SafetyCheck.check_time >= start_of_day,
        SafetyCheck.check_time <= now,
    ).count()

    alerts_count = len(notification_service.get_recent_alerts())

    return jsonify(
        {
            "status": "ok",
            "present_count": present_count,
            "checked_in_count": checked_in_today,
            "absent_count": absent_count,
            "total_employees": total_employees,
            "attendance_percentage": attendance_pct,
            "compliance_rate": compliance_rate,
            "total_ppe_checks": total_ppe_checks,
            "todays_ppe_checks": todays_ppe_checks,
            "alerts_count": alerts_count,
        }
    )


@dashboard_bp.route("/analytics", methods=["GET"])
def dashboard_analytics():
    """
    Return comprehensive, real-database analytics for dashboard charts & feeds:
    - 7-day attendance trends
    - PPE compliance breakdown
    - Department workforce and attendance summary
    - Recent attendance logs (up to 8)
    - Recent safety inspections (up to 8)
    """
    from datetime import timedelta

    today = date.today()
    now = datetime.utcnow()
    total_employees = Employee.query.filter_by(is_active=True).count()

    # 1. Past 7 days attendance trends
    trend_labels = []
    trend_counts = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        count = Attendance.query.filter(Attendance.date == day).count()
        trend_labels.append(day.strftime("%b %d"))
        trend_counts.append(count)

    # 2. PPE Compliance breakdown (All time)
    total_safety = SafetyCheck.query.count()
    compliant_safety = SafetyCheck.query.filter_by(is_compliant=True).count()
    non_compliant_safety = total_safety - compliant_safety
    all_time_compliance_rate = round((compliant_safety / total_safety * 100), 1) if total_safety > 0 else 0.0

    # 3. Department breakdown
    departments = ["Production", "Maintenance", "Quality", "Logistics", "Administration"]
    dept_stats = []
    for dept in departments:
        dept_total = Employee.query.filter_by(department=dept, is_active=True).count()
        # present in this dept today
        dept_present = (
            Attendance.query.join(Employee, Attendance.employee_id == Employee.id)
            .filter(Attendance.date == today, Employee.department == dept, Attendance.check_out_time.is_(None))
            .count()
        )
        dept_stats.append({
            "department": dept,
            "total": dept_total,
            "present": dept_present,
            "rate": round((dept_present / dept_total * 100), 1) if dept_total > 0 else 0.0,
        })

    # 4. Recent attendance activity (with employee name)
    recent_att_query = (
        Attendance.query.join(Employee, Attendance.employee_id == Employee.id)
        .order_by(Attendance.check_in_time.desc())
        .limit(8)
        .all()
    )
    recent_attendance = []
    for a in recent_att_query:
        emp = Employee.query.get(a.employee_id)
        recent_attendance.append({
            "id": a.id,
            "employee_id": emp.employee_id if emp else f"ID-{a.employee_id}",
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "Unknown",
            "department": emp.department if emp else "-",
            "check_in_time": a.check_in_time.isoformat() if a.check_in_time else None,
            "check_out_time": a.check_out_time.isoformat() if a.check_out_time else None,
            "date": a.date.isoformat() if a.date else None,
            "status": a.status,
            "attendance_method": a.attendance_method,
        })

    # 5. Recent safety inspection activity
    recent_safety_query = (
        SafetyCheck.query.order_by(SafetyCheck.check_time.desc())
        .limit(8)
        .all()
    )
    recent_safety = []
    for s in recent_safety_query:
        emp = Employee.query.get(s.employee_id)
        recent_safety.append({
            "id": s.id,
            "employee_id": emp.employee_id if emp else f"ID-{s.employee_id}",
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "Unknown",
            "check_time": s.check_time.isoformat() if s.check_time else None,
            "helmet_detected": s.helmet_detected,
            "vest_detected": s.vest_detected,
            "gloves_detected": s.gloves_detected,
            "boots_detected": s.boots_detected,
            "is_compliant": s.is_compliant,
            "confidence_score": s.confidence_score,
        })

    return jsonify({
        "status": "ok",
        "trend_labels": trend_labels,
        "trend_counts": trend_counts,
        "compliance": {
            "total_checks": total_safety,
            "compliant": compliant_safety,
            "non_compliant": non_compliant_safety,
            "compliance_rate": all_time_compliance_rate,
        },
        "departments": dept_stats,
        "recent_attendance": recent_attendance,
        "recent_safety": recent_safety,
    })



@dashboard_bp.route("/alerts", methods=["GET"])
def dashboard_alerts():
    """Return recent alerts (safety violations, attendance anomalies)."""
    alerts = notification_service.get_recent_alerts()
    return jsonify({"status": "ok", "alerts": alerts})


@dashboard_bp.route("/home-stats", methods=["GET"])
def home_stats():
    """
    Return high-level statistics for the home page.

    Statistics include total registered employees, today's attendance count,
    PPE-compliant checks today, and PPE violations today. All values are
    computed from real database records — nothing is fabricated.
    """
    today = date.today()

    total_employees = Employee.query.filter_by(is_active=True).count()

    todays_attendance = Attendance.query.filter(
        Attendance.date == today
    ).count()

    start_of_day = datetime.combine(today, time.min)
    now = datetime.utcnow()
    ppe_compliant = SafetyCheck.query.filter(
        SafetyCheck.check_time >= start_of_day,
        SafetyCheck.check_time <= now,
        SafetyCheck.is_compliant.is_(True),
    ).count()
    ppe_violations = SafetyCheck.query.filter(
        SafetyCheck.check_time >= start_of_day,
        SafetyCheck.check_time <= now,
        SafetyCheck.is_compliant.is_(False),
    ).count()

    return jsonify(
        {
            "status": "ok",
            "total_employees": total_employees,
            "todays_attendance": todays_attendance,
            "ppe_compliant": ppe_compliant,
            "ppe_violations": ppe_violations,
        }
    )
