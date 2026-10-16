"""
services/notification_service.py
================================
Business logic for sending alerts and notifications.

Handles safety violations, attendance anomalies, and system alerts via
email, SMS, or in-app channels. External integrations are deferred; the
service logs alerts in-memory for the dashboard placeholder.
"""

from datetime import datetime


class NotificationService:
    """Service class for dispatching notifications and alerts."""

    def __init__(self):
        # In-memory store for recent alerts (placeholder for persistence layer)
        self._alerts = []

    def send_safety_violation_alert(self, employee_id, violation_details):
        """
        Send an alert when an employee fails a safety gear check.

        Args:
            employee_id: Employee who violated safety gear requirements.
            violation_details: Dict describing the missing gear and context.

        Returns:
            dict: Result of the notification dispatch.
        """
        alert = {
            "type": "safety_violation",
            "employee_id": employee_id,
            "details": violation_details,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._alerts.append(alert)
        return {"status": "ok", "message": "Safety violation alert recorded.", "alert": alert}

    def send_attendance_anomaly_alert(self, employee_id, anomaly_type):
        """
        Send an alert for attendance anomalies (e.g., late, absent, duplicate).

        Args:
            employee_id: Employee with the anomaly.
            anomaly_type: Type of anomaly (late, absent, duplicate check-in).

        Returns:
            dict: Result of the notification dispatch.
        """
        alert = {
            "type": "attendance_anomaly",
            "employee_id": employee_id,
            "anomaly_type": anomaly_type,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._alerts.append(alert)
        return {"status": "ok", "message": "Attendance anomaly alert recorded.", "alert": alert}

    def send_email(self, recipient, subject, body):
        """
        Send an email notification.

        Email provider integration is not implemented yet; this returns a
        placeholder success response.

        Args:
            recipient: Email address of the recipient.
            subject: Email subject line.
            body: Email body content.

        Returns:
            dict: Result of the email send operation.
        """
        return {
            "status": "ok",
            "message": "Email sending is not implemented yet.",
            "recipient": recipient,
            "subject": subject,
        }

    def get_recent_alerts(self, limit=10):
        """
        Retrieve recent alerts for the dashboard.

        Args:
            limit: Maximum number of alerts to return.

        Returns:
            list: Recent alert records (most recent first).
        """
        return list(reversed(self._alerts))[:limit]