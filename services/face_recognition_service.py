"""
services/face_recognition_service.py
====================================
Face detection and recognition for gallery-based and live-camera attendance.

This module provides a lightweight face-recognition implementation built on
OpenCV. It is intentionally dependency-light so the college prototype can run
without installing the heavy ``face_recognition`` / ``dlib`` / ``deepface``
packages.

Approach
--------
* Face detection uses OpenCV's **YuNet** neural detector
  (``cv2.FaceDetectorYN_create``) with the ONNX model shipped at
  ``weights/face_detection_yunet_2023mar.onnx``. This is the primary detector.
  A Haar-cascade fallback (``cv2.CascadeClassifier``) is used only when the
  YuNet model is unavailable, so the service degrades gracefully.
* A "face encoding" is a small normalized grayscale patch (the detected face
  resized to a fixed size and flattened). It is stored as a numpy ``float32``
  array serialized to bytes in the ``employees.face_encoding`` BLOB column.
* Matching compares the probe encoding against enrolled encodings using
  Euclidean distance. The closest match below a tuned threshold is considered
  the same person; otherwise the result is "unknown".

This is a prototype-grade approach suitable for a college demonstration. It is
NOT a production-grade face recognition system (no illumination/pose
invariance, no neural embeddings). A future production version can swap in a
deep-learning face embedding model (e.g. FaceNet, ArcFace) behind the same
service interface without changing the routes.
"""

import os

import cv2
import numpy as np

# Fixed size used to normalize a detected face into a single encoding vector.
ENCODING_WIDTH = 64
ENCODING_HEIGHT = 64

# Euclidean-distance threshold below which two encodings are considered the
# same person. Lower = stricter, higher = more permissive.
MATCH_THRESHOLD = 18.0

# Default Haar cascade path included with OpenCV.
HAAR_CASCADE_PATH = os.path.join(
    os.path.dirname(cv2.data.haarcascades), "haarcascade_frontalface_default.xml"
)

# Default YuNet ONNX model path (shipped with the repository).
DEFAULT_YUNET_MODEL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "weights",
    "face_detection_yunet_2023mar.onnx",
)

# Input size expected by the YuNet model.
YUNET_INPUT_SIZE = (320, 320)


class FaceRecognitionError(Exception):
    """Raised when face recognition cannot be performed."""


class FaceRecognitionService:
    """Face detection, encoding, enrollment, and matching logic."""

    def __init__(
        self,
        cascade_path=None,
        yunet_model_path=None,
        match_threshold=MATCH_THRESHOLD,
    ):
        self.cascade_path = cascade_path or HAAR_CASCADE_PATH
        self.yunet_model_path = yunet_model_path or DEFAULT_YUNET_MODEL
        self.match_threshold = match_threshold
        self._cascade = None
        self._yunet = None

    # ------------------------------------------------------------------ yunet
    def _get_yunet(self):
        """Load (and cache) the YuNet face detector lazily on first use."""
        if self._yunet is not None:
            return self._yunet
        if not os.path.exists(self.yunet_model_path):
            raise FaceRecognitionError(
                f"YuNet model file not found at {self.yunet_model_path}. "
                "Face detection is unavailable."
            )
        self._yunet = cv2.FaceDetectorYN_create(
            self.yunet_model_path,
            "",
            YUNET_INPUT_SIZE,
        )
        return self._yunet

    def _get_cascade(self):
        """Load (and cache) the Haar cascade lazily on first use."""
        if self._cascade is not None:
            return self._cascade
        if not os.path.exists(self.cascade_path):
            raise FaceRecognitionError(
                f"Haar cascade file not found at {self.cascade_path}. "
                "OpenCV face detection is unavailable."
            )
        self._cascade = cv2.CascadeClassifier(self.cascade_path)
        return self._cascade

    # ---------------------------------------------------------------- detect
    def detect_faces(self, image_array):
        """
        Detect faces in a BGR image (as loaded by OpenCV).

        Uses the YuNet neural detector as the primary method. Falls back to
        the Haar cascade if YuNet is unavailable.

        Args:
            image_array: 3-channel BGR numpy array (uint8).

        Returns:
            list of (x, y, w, h) rectangles for detected faces. Empty if none.
        """
        if image_array is None:
            return []

        # Try YuNet first (primary detector).
        yunet_ok = False
        try:
            detector = self._get_yunet()
            yunet_ok = True
            # YuNet requires a specific input size; resize for detection only.
            h, w = image_array.shape[:2]
            input_w, input_h = YUNET_INPUT_SIZE
            scale_x = w / input_w
            scale_y = h / input_h

            resized = cv2.resize(image_array, (input_w, input_h))
            # cv2.FaceDetectorYN.detect() returns a tuple (retval, faces)
            # where faces is a numpy array of shape (N, 15) or None when no
            # faces are detected. We must unpack the tuple rather than pass
            # it directly to np.asarray(), which would fail on the
            # inhomogeneous (scalar, array) sequence.
            retval, faces = detector.detect(resized)
            if faces is not None:
                # Each row is [x, y, w, h, confidence, ...]. Coordinates are
                # in the resized (input) image space and must be scaled back.
                faces = np.asarray(faces)
                if faces.ndim == 1:
                    # Single face returned as 1-D — reshape to 2-D.
                    faces = faces.reshape(1, -1)
                if faces.shape[0] > 0:
                    result_faces = []
                    for face in faces:
                        x = int(face[0] * scale_x)
                        y = int(face[1] * scale_y)
                        fw = int(face[2] * scale_x)
                        fh = int(face[3] * scale_y)
                        result_faces.append((x, y, fw, fh))
                    if result_faces:
                        return result_faces

        except (FaceRecognitionError, cv2.error, TypeError, IndexError):
            pass

        # Fallback: Haar cascade.
        try:
            cascade = self._get_cascade()
            gray = cv2.cvtColor(image_array, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(40, 40),
            )
            return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]
        except (FaceRecognitionError, cv2.error, AttributeError):
            pass

        # If neither detector is available, raise so the caller can report it.
        if not yunet_ok:
            raise FaceRecognitionError(
                "No face detection model is available. "
                "Ensure the YuNet ONNX model or Haar cascade is configured."
            )
        return []

    # ---------------------------------------------------------------- encode
    def encode_face(self, image_array):
        """
        Produce a normalized face encoding for the largest detected face.

        Args:
            image_array: BGR image array.

        Returns:
            np.ndarray(float32): Flattened normalized grayscale face patch.
            Returns None if no face is detected.
        """
        faces = self.detect_faces(image_array)
        if not faces:
            return None

        # Use the largest detected face for the encoding.
        largest = max(faces, key=lambda r: r[2] * r[3])
        x, y, w, h = largest
        gray = cv2.cvtColor(image_array, cv2.COLOR_BGR2GRAY)
        face = gray[y : y + h, x : x + w]
        resized = cv2.resize(face, (ENCODING_WIDTH, ENCODING_HEIGHT))
        # Normalize to [0,1] and flatten.
        encoding = resized.astype(np.float32) / 255.0
        return encoding.flatten()

    # --------------------------------------------------------------- serialize
    @staticmethod
    def encoding_to_bytes(encoding):
        """Serialize a numpy encoding to bytes for storage in a BLOB column."""
        if encoding is None:
            return None
        return encoding.tobytes()

    @staticmethod
    def bytes_to_encoding(data):
        """Deserialize bytes back into a numpy float32 array."""
        if data is None:
            return None
        return np.frombuffer(data, dtype=np.float32)

    # ---------------------------------------------------------------- match
    def match_encoding(self, probe, enrolled):
        """Euclidean distance between two encodings."""
        if probe is None or enrolled is None:
            return float("inf")
        return float(np.linalg.norm(probe - enrolled))

    def is_match(self, distance):
        """Return True if a distance is within the match threshold."""
        return distance <= self.match_threshold

    # ------------------------------------------------------------- enrollment
    def enroll(self, employee, image_path):
        """
        Enroll (store) the face encoding for an employee from an image file.

        Args:
            employee: Employee ORM instance.
            image_path: Path to a face photo (single-person portrait).

        Returns:
            dict: {status, message, encoding?}
        """
        image_array = cv2.imread(image_path)
        if image_array is None:
            return {"status": "error", "message": "Could not read the uploaded image."}

        return self.enroll_from_array(employee, image_array)

    def enroll_from_array(self, employee, image_array):
        """
        Enroll (store) the face encoding for an employee from an image array.

        Args:
            employee: Employee ORM instance.
            image_array: BGR numpy array.

        Returns:
            dict: {status, message, encoding_size?}
        """
        if image_array is None:
            return {"status": "error", "message": "Could not read the image."}

        encoding = self.encode_face(image_array)
        if encoding is None:
            return {
                "status": "error",
                "message": (
                    "No face detected in the image. Please ensure a clear, "
                    "front-facing face is visible and try again."
                ),
            }

        employee.face_encoding = self.encoding_to_bytes(encoding)
        return {
            "status": "ok",
            "message": "Face enrolled successfully.",
            "encoding_size": len(employee.face_encoding),
        }

    # ------------------------------------------------------------- recognition
    def recognize(self, image_array):
        """
        Detect a face in an image array and identify the employee.

        Matches the probe encoding against all enrolled employees and returns
        the best match (if within threshold) or None.

        Args:
            image_array: BGR numpy array.

        Returns:
            dict: {
                "recognized": bool,
                "employee": Employee or None,
                "distance": float or None,
                "message": str,
            }
        """
        if image_array is None:
            return {
                "recognized": False,
                "employee": None,
                "distance": None,
                "message": "Could not read the image.",
            }

        faces = self.detect_faces(image_array)
        if not faces:
            return {
                "recognized": False,
                "employee": None,
                "distance": None,
                "message": "No face detected in the image.",
            }

        probe = self.encode_face(image_array)
        if probe is None:
            return {
                "recognized": False,
                "employee": None,
                "distance": None,
                "message": "Could not encode the detected face.",
            }

        # Match against all enrolled employees.
        best_employee = None
        best_distance = float("inf")
        for employee in Employee.query.filter(
            Employee.face_encoding.isnot(None)
        ).all():
            enrolled = self.bytes_to_encoding(employee.face_encoding)
            distance = self.match_encoding(probe, enrolled)
            if distance < best_distance:
                best_distance = distance
                best_employee = employee

        if best_employee is not None and self.is_match(best_distance):
            return {
                "recognized": True,
                "employee": best_employee,
                "distance": round(best_distance, 2),
                "message": "Face recognized.",
            }

        return {
            "recognized": False,
            "employee": None,
            "distance": round(best_distance, 2) if best_employee else None,
            "message": (
                "Face detected but did not match any enrolled employee. "
                "Please use the manual fallback."
            ),
        }


# Late import to avoid circular dependency (Employee model needs db).
from models.employee import Employee  # noqa: E402
