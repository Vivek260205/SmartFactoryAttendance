"""
tests/test_ppe_detector.py
==========================
Tests for the PPE detector abstraction (services/ppe_detector.py).
"""

import os

import pytest

from services.ppe_detector import (
    IGNORED_CLASSES,
    NoModelPPEDetector,
    PPEDetectionError,
    UltralyticsPPEDetector,
    get_ppe_detector,
)


def test_no_model_detector_not_available():
    detector = NoModelPPEDetector()
    assert detector.is_available() is False


def test_no_model_detector_refuses_to_detect():
    detector = NoModelPPEDetector()
    with pytest.raises(PPEDetectionError):
        detector.detect("/tmp/image.png")


def test_get_ppe_detector_no_model_returns_no_model():
    detector = get_ppe_detector()
    assert isinstance(detector, NoModelPPEDetector)
    assert detector.is_available() is False


def test_get_ppe_detector_with_model_returns_ultralytics():
    detector = get_ppe_detector("/models/best.pt")
    assert isinstance(detector, UltralyticsPPEDetector)
    assert detector.is_available() is True


def test_canonical_class_mapping():
    detector = UltralyticsPPEDetector("/models/best.pt")
    assert detector._canonical_class("helmet") == "helmet"
    assert detector._canonical_class("Hardhat") == "helmet"
    assert detector._canonical_class("safety_vest") == "vest"
    assert detector._canonical_class("work_boots") == "boots"
    assert detector._canonical_class("gloves") == "gloves"
    assert detector._canonical_class("person") is None
    assert detector._canonical_class("") is None


def test_human_class_is_ignored_for_compliance():
    """The real model's 'human' class must never map to PPE gear."""
    assert "human" in IGNORED_CLASSES
    detector = UltralyticsPPEDetector("/models/best.pt")
    assert detector._canonical_class("human") is None


def test_default_model_path_points_to_real_weights():
    """The default config should reference the shipped weights/best.pt file."""
    from config import Config

    path = Config.PPE_MODEL_PATH
    assert path.endswith(os.path.join("weights", "best.pt"))
    assert os.path.exists(path), f"Expected real model at {path}"


def test_real_model_loads_expected_classes():
    """The real weights/best.pt loads and exposes the 5 expected classes."""
    from config import Config

    path = Config.PPE_MODEL_PATH
    if not os.path.exists(path):
        pytest.skip(f"Real model not present at {path}")

    detector = UltralyticsPPEDetector(path)
    model = detector._load_model()
    names = {int(i): str(n) for i, n in model.names.items()}
    assert set(names.values()) == {"boots", "gloves", "helmet", "human", "vest"}
    # boots, gloves, helmet, vest map to canonical PPE; human is ignored.
    mapped = {UltralyticsPPEDetector._canonical_class(n) for n in names.values()}
    assert mapped == {None, "boots", "gloves", "helmet", "vest"}
