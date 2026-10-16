"""
services/ppe_detector.py
========================
PPE (Personal Protective Equipment) object detection abstraction.

This module defines the interface for a trained PPE object detection model and
provides a concrete implementation built on Ultralytics YOLO.

IMPORTANT
---------
A trained PPE model ships with this repository at ``weights/best.pt`` and is
used by default. When a model is NOT configured, detection is NOT performed
and NO results are fabricated. The ``NoModelPPEDetector`` raises
:class:`PPEDetectionError` so callers can clearly report that real detection
is unavailable.

To enable real detection, provide a YOLO weights file (e.g. ``best.pt``)
trained on the detected classes: ``helmet``, ``vest``, ``gloves``, ``boots``
(``human`` is detected but ignored for compliance). Only the required PPE
classes (``helmet``, ``vest``, ``boots``) are used for the compliance verdict;
``gloves`` is still detected and reported but is NOT required for compliance.
Set the ``PPE_MODEL_PATH`` environment variable (or the ``PPE_MODEL_PATH``
config value) to the file's path.
"""

import os

# Required PPE classes used for compliance evaluation. Gloves is intentionally
# removed from the required set: an employee is COMPLIANT when helmet + vest +
# boots are detected. Gloves is still detected/reported but does not affect the
# compliance verdict.
PPE_CLASSES = ["helmet", "vest", "boots"]

# Classes the model may output that are NOT considered PPE gear. These are
# intentionally ignored for compliance evaluation (e.g. the real model at
# weights/best.pt also detects 'human'). Detected humans are used to confirm a
# person is present but never affect the PPE compliance verdict.
IGNORED_CLASSES = {"human"}

# Class-name aliases commonly found in PPE datasets. The detector maps a
# model's raw class names to the canonical PPE_CLASSES names so that models
# trained with slightly different labels (e.g. "hardhat" vs "helmet") still
# integrate cleanly.
CLASS_ALIASES = {
    "helmet": ["helmet", "hardhat", "hard_hat", "safety_helmet", "helmet_face"],
    "vest": [
        "vest",
        "safety_vest",
        "hi_vis_vest",
        "high_visibility_vest",
        "reflective_vest",
    ],
    "gloves": ["gloves", "safety_gloves", "work_gloves"],
    "boots": ["boots", "safety_boots", "work_boots", "steel_toe_boots"],
}

# Message describing the exact model/dataset required. Surfaced to operators
# when detection cannot run.
RECOMMENDED_MODEL = (
    "A YOLO weights file (e.g. best.pt) trained on exactly these 4 PPE "
    "classes: helmet, vest, gloves, boots. Recommended datasets include the "
    "'Safety Objects Detection Action' (SODA) dataset or a Roboflow/Kaggle "
    "PPE detection dataset. Place the file on disk and set PPE_MODEL_PATH to "
    "its path."
)


class PPEDetectionError(Exception):
    """Raised when PPE detection cannot be performed."""


class PPEDetector:
    """Interface for a PPE object detection model."""

    def is_available(self):
        """Return True if a real model is available to run detection."""
        raise NotImplementedError

    def detect(self, image_path):
        """Run detection on an image and return structured PPE results.

        Args:
            image_path: Path to the image file to analyze.

        Returns:
            dict: Detection results keyed by the canonical PPE classes.
        """
        raise NotImplementedError


class NoModelPPEDetector(PPEDetector):
    """Detector used when no trained PPE model is configured.

    This detector does NOT run detection and does NOT invent results. It is
    intentionally the default so the application never fabricates compliance
    data when a real model is unavailable.
    """

    def is_available(self):
        return False

    def detect(self, image_path):
        raise PPEDetectionError(
            "No trained PPE detection model is configured. "
            f"{RECOMMENDED_MODEL}"
        )


class UltralyticsPPEDetector(PPEDetector):
    """Real PPE detector built on Ultralytics YOLO.

    Loads a trained YOLO weights file and maps the model's detected class
    names to the canonical PPE classes (helmet, vest, gloves, boots). Only
    detections whose class maps to a required PPE class are reported.
    """

    def __init__(self, model_path, confidence_threshold=0.35):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self._model = None

    def is_available(self):
        return bool(self.model_path)

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover - depends on runtime env
            raise PPEDetectionError(
                "The 'ultralytics' package is not installed. "
                "Install it with: pip install ultralytics"
            ) from exc
        if not os.path.exists(self.model_path):
            raise PPEDetectionError(
                f"PPE model file not found at: {self.model_path}. "
                f"{RECOMMENDED_MODEL}"
            )
        self._model = YOLO(self.model_path)
        return self._model

    @staticmethod
    def _canonical_class(raw_name):
        """Map a raw model class name to a canonical PPE class name.

        Args:
            raw_name: Class name as reported by the model (e.g. "Hardhat").

        Returns:
            str or None: Canonical PPE class name, or None if unknown.
        """
        raw = (raw_name or "").strip().lower().replace(" ", "_")
        if raw in IGNORED_CLASSES:
            # Detected class is intentionally ignored for PPE compliance
            # (e.g. "human"). Return None so it is not treated as gear.
            return None
        for canonical, aliases in CLASS_ALIASES.items():
            if raw == canonical or raw in aliases:
                return canonical
        return None

    def detect(self, image_path):
        model = self._load_model()
        results = model.predict(
            source=image_path, conf=self.confidence_threshold, verbose=False
        )

        # Accumulate the highest confidence per canonical PPE class. Gloves is
        # still detected and reported even though it is NOT part of the required
        # compliance set (PPE_CLASSES = helmet, vest, boots).
        confidences = {cls: 0.0 for cls in PPE_CLASSES}
        gloves_confidence = 0.0
        raw_detections = []
        ignored_detections = []
        for result in results:
            for box in result.boxes:
                raw_name = result.names[int(box.cls)]
                canonical = self._canonical_class(raw_name)
                if canonical is None:
                    # Detected object is not one of the required PPE classes.
                    # This includes ignored classes (e.g. "human") and any
                    # unknown classes. Such detections never affect compliance.
                    if (raw_name or "").strip().lower() in IGNORED_CLASSES:
                        ignored_detections.append(
                            {"class": raw_name, "confidence": float(box.conf)}
                        )
                    continue
                conf = float(box.conf)
                raw_detections.append({"class": canonical, "confidence": conf})
                if conf > confidences.get(canonical, 0.0):
                    confidences[canonical] = conf
                if canonical == "gloves" and conf > gloves_confidence:
                    gloves_confidence = conf

        detected = {cls: confidences[cls] > 0.0 for cls in PPE_CLASSES}
        overall = (
            sum(confidences.values()) / len(PPE_CLASSES)
            if any(detected.values())
            else 0.0
        )

        annotated_image_path = None
        for result in results:
            if hasattr(result, "plot"):
                try:
                    annotated_bgr = result.plot()
                    if annotated_bgr is not None:
                        import cv2
                        dir_name = os.path.dirname(image_path)
                        base_name = os.path.basename(image_path)
                        annotated_filename = f"annotated_{base_name}"
                        full_annotated_path = os.path.join(dir_name, annotated_filename)
                        cv2.imwrite(full_annotated_path, annotated_bgr)
                        annotated_image_path = full_annotated_path
                except Exception:
                    annotated_image_path = None

        return {
            "detection_status": "completed",
            "helmet_detected": detected["helmet"],
            "vest_detected": detected["vest"],
            "gloves_detected": gloves_confidence > 0.0,
            "boots_detected": detected["boots"],
            "confidence_score": round(overall * 100, 2),
            "detections": raw_detections,
            "ignored_detections": ignored_detections,
            "image_path": image_path,
            "annotated_image_path": annotated_image_path,
            "message": "PPE detection completed.",
        }



def get_ppe_detector(model_path=None, confidence_threshold=0.35):
    """Return the appropriate PPEDetector based on configuration.

    If a trained model path is provided, returns an ``UltralyticsPPEDetector``.
    Otherwise returns a ``NoModelPPEDetector`` that refuses to fabricate
    detection results.

    Args:
        model_path: Path to a trained PPE YOLO weights file, or None.
        confidence_threshold: Minimum confidence to accept a detection.

    Returns:
        PPEDetector: The detector to use for this configuration.
    """
    if model_path:
        return UltralyticsPPEDetector(model_path, confidence_threshold)
    return NoModelPPEDetector()
