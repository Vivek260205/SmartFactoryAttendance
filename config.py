"""
config.py
=========
Configuration settings for the Smart Factory Attendance application.

Holds environment-specific settings such as secret keys, database URIs,
and feature flags. Business logic is intentionally left unimplemented.
"""

import os


class Config:
    """Base configuration class with common settings."""

    # Secret key for session management and CSRF protection
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")

    # Database URI (SQLite for development; switch to PostgreSQL/MySQL in production)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///smart_factory.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload folder for safety gear images / attendance snapshots
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")

    # Allowed file extensions for uploads
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "mp4"}

    # Maximum request body size (10 MB).
    # This accommodates base64-encoded camera frames sent from the face
    # attendance and enrollment pages. Without an explicit limit Flask
    # defaults to unlimited, but setting a sane ceiling prevents
    # accidentally oversized payloads from exhausting server memory.
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    MAX_FORM_MEMORY_SIZE = 10 * 1024 * 1024
    # Safety gear detection settings.
    # Path to a trained PPE YOLO weights file (e.g. best.pt) covering exactly:
    # helmet, vest, gloves, boots. The real model ships with the repository at
    # weights/best.pt and is used by default. Compliance is determined by the
    # required gear (helmet, vest, boots); gloves is detected/reported but not
    # required. When the model path is empty, real detection is disabled and
    # the app reports that no model is configured (it never fabricates
    # results). Override with the PPE_MODEL_PATH env var.
    _DEFAULT_MODEL_PATH = os.path.join(
        os.path.dirname(__file__), "weights", "best.pt"
    )
    PPE_MODEL_PATH = os.environ.get("PPE_MODEL_PATH", _DEFAULT_MODEL_PATH)

    # Minimum confidence to accept a PPE detection.
    PPE_CONFIDENCE_THRESHOLD = float(os.environ.get("PPE_CONFIDENCE_THRESHOLD", "0.35"))

    # Face detection model (OpenCV YuNet ONNX) for face recognition.
    # Ships with the repository at weights/face_detection_yunet_2023mar.onnx.
    _DEFAULT_FACE_MODEL = os.path.join(
        os.path.dirname(__file__), "weights", "face_detection_yunet_2023mar.onnx"
    )
    FACE_DETECTION_MODEL = os.environ.get(
        "FACE_DETECTION_MODEL", _DEFAULT_FACE_MODEL
    )

    # Face recognition match threshold (Euclidean distance).
    FACE_MATCH_THRESHOLD = float(os.environ.get("FACE_MATCH_THRESHOLD", "18.0"))

    # Notification settings (placeholder)
    NOTIFICATION_ENABLED = True


class DevelopmentConfig(Config):
    """Development-specific configuration."""

    DEBUG = True
    ENV = "development"


class ProductionConfig(Config):
    """Production-specific configuration."""

    DEBUG = False
    ENV = "production"


class TestingConfig(Config):
    """Testing-specific configuration."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    DEBUG = True


# Dictionary to map environment names to config classes
config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
