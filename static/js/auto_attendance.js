/* ============================================================
   auto_attendance.js
   ===================
   Client-side logic for the automatic (kiosk) face attendance page.

   - Auto-starts the webcam on page load
   - Continuously captures frames at ~700ms intervals
   - Sends each frame to /face-attendance/auto-process for detection,
     recognition, and automatic attendance marking
   - Handles: recognized, unknown, multiple faces, no face,
     already checked in/out, and manual fallback
   - Enforces a cooldown after a successful check-in/out to prevent
     duplicate processing while the same employee remains in frame
   ============================================================ */

(function () {
    "use strict";

    // ---- DOM references ----
    var video = document.getElementById("video");
    var canvas = document.getElementById("canvas");
    var cameraStatusBar = document.getElementById("camera-status-bar");
    var statusText = document.querySelector(".kiosk-status-text");
    var faceOverlay = document.getElementById("face-overlay");
    var promptText = document.getElementById("prompt-text");
    var waitingState = document.getElementById("waiting-state");
    var employeeCard = document.getElementById("employee-card");
    var attendanceResult = document.getElementById("attendance-result");
    var manualFallback = document.getElementById("manual-fallback");
    var manualEmployeeId = document.getElementById("manual-employee-id");
    var manualSubmitBtn = document.getElementById("manual-submit-btn");
    var modeCheckin = document.getElementById("mode-checkin");
    var modeCheckout = document.getElementById("mode-checkout");
    var modeIndicator = document.getElementById("mode-indicator");
    var currentDateEl = document.getElementById("current-date");
    var currentTimeEl = document.getElementById("current-time");

    // ---- State ----
    var stream = null;
    var currentMode = "check-in";
    var processing = false;
    var cooldownActive = false;
    var cooldownTimer = null;
    var captureInterval = null;
    var cameraReady = false;
    var lastRecognizedEmployeeId = null;

    // Configuration
    var FRAME_INTERVAL_MS = 700;       // ~700ms between frame captures
    var COOLDOWN_MS = 15000;           // 15s lockout after a successful action
    var FRAME_MAX_WIDTH = 640;         // downscale for smaller payload
    var FRAME_MAX_HEIGHT = 480;

    // ---- Utility helpers ----
    function escapeHtml(str) {
        if (str === null || str === undefined) return "";
        var div = document.createElement("div");
        div.textContent = String(str);
        return div.innerHTML;
    }

    function formatDateTime(isoString) {
        if (!isoString) return "--";
        try {
            var d = new Date(isoString);
            return d.toLocaleTimeString();
        } catch (e) {
            return isoString;
        }
    }

    function updateCameraStatus(message, dotClass) {
        if (statusText) {
            statusText.textContent = message;
        }
        if (cameraStatusBar) {
            var dot = cameraStatusBar.querySelector(".status-dot");
            if (dot) {
                dot.className = "status-dot " + (dotClass || "blue");
            }
        }
    }

    function showFaceOverlay(show) {
        if (faceOverlay) {
            faceOverlay.classList.toggle("d-none", !show);
        }
    }

    function showPrompt(text) {
        if (promptText) {
            var p = promptText.querySelector("p");
            if (p) {
                p.textContent = text;
            }
        }
    }

    function showWaiting() {
        if (waitingState) waitingState.classList.remove("d-none");
        if (employeeCard) employeeCard.classList.add("d-none");
        if (attendanceResult) attendanceResult.innerHTML = "";
        if (manualFallback) manualFallback.classList.add("d-none");
        showFaceOverlay(false);
        showPrompt("Please stand in front of the camera");
    }

    function showEmployeeCard(emp) {
        if (waitingState) waitingState.classList.add("d-none");
        if (employeeCard) employeeCard.classList.remove("d-none");
        if (attendanceResult) attendanceResult.innerHTML = "";
        if (manualFallback) manualFallback.classList.add("d-none");

        document.getElementById("emp-employee-id").textContent = emp.employee_id || "-";
        document.getElementById("emp-name").textContent =
            (emp.first_name || "") + " " + (emp.last_name || "");
        document.getElementById("emp-department").textContent = emp.department || "-";
        document.getElementById("emp-shift").textContent = emp.shift || "-";
        document.getElementById("emp-distance").textContent =
            emp.distance != null ? emp.distance.toFixed(2) : "-";
    }

    function showAttendanceResult(html, type) {
        if (attendanceResult) {
            attendanceResult.innerHTML = html;
        }
    }

    function showManualFallback(message) {
        if (waitingState) waitingState.classList.add("d-none");
        if (employeeCard) employeeCard.classList.add("d-none");
        if (attendanceResult) attendanceResult.innerHTML = "";
        if (manualFallback) manualFallback.classList.remove("d-none");
        showFaceOverlay(false);
        showPrompt(message || "Face not recognized. Use manual entry below.");
        manualEmployeeId.value = "";
        manualSubmitBtn.disabled = true;
    }

    function setMode(mode) {
        currentMode = mode;
        if (mode === "check-in") {
            modeCheckin.classList.add("active");
            modeCheckout.classList.remove("active");
            if (modeIndicator) {
                modeIndicator.innerHTML =
                    '<span class="badge bg-kiosk-checkin">' +
                    '<i class="bi bi-box-arrow-in-right me-1"></i> CHECK-IN MODE</span>';
            }
        } else {
            modeCheckin.classList.remove("active");
            modeCheckout.classList.add("active");
            if (modeIndicator) {
                modeIndicator.innerHTML =
                    '<span class="badge bg-kiosk-checkout">' +
                    '<i class="bi bi-box-arrow-right me-1"></i> CHECK-OUT MODE</span>';
            }
        }
        // Reset state when mode changes
        showWaiting();
        lastRecognizedEmployeeId = null;
        if (cooldownActive) {
            endCooldown();
        }
    }

    function startCooldown() {
        cooldownActive = true;
        updateCameraStatus("Processing complete. Please step away.", "blue");
        if (captureInterval) {
            clearInterval(captureInterval);
            captureInterval = null;
        }
        cooldownTimer = setTimeout(function () {
            endCooldown();
        }, COOLDOWN_MS);
    }

    function endCooldown() {
        cooldownActive = false;
        lastRecognizedEmployeeId = null;
        if (cooldownTimer) {
            clearTimeout(cooldownTimer);
            cooldownTimer = null;
        }
        showWaiting();
        updateCameraStatus("Camera active. Ready for next employee.", "blue");
        startCaptureLoop();
    }

    // ---- Date / time ----
    function updateDateTime() {
        var now = new Date();
        if (currentDateEl) {
            currentDateEl.textContent = now.toLocaleDateString(undefined, {
                weekday: "long",
                year: "numeric",
                month: "long",
                day: "numeric",
            });
        }
        if (currentTimeEl) {
            currentTimeEl.textContent = now.toLocaleTimeString();
        }
    }

    // ---- Camera ----
    function startCamera() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            updateCameraStatus(
                "Camera not supported by this browser. Please use a modern browser.",
                "red"
            );
            return;
        }

        navigator.mediaDevices
            .getUserMedia({ video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } } })
            .then(function (s) {
                stream = s;
                video.srcObject = s;
                video.play();
                cameraReady = true;
                updateCameraStatus("Camera active. Please stand in front of the camera.", "blue");
                startCaptureLoop();
            })
            .catch(function (err) {
                cameraReady = false;
                var msg = "Camera access denied or unavailable: " + err.message;
                if (err.name === "NotAllowedError") {
                    msg = "Camera permission denied. Please allow camera access and reload the page.";
                } else if (err.name === "NotFoundError") {
                    msg = "No camera found. Please connect a webcam and reload the page.";
                }
                updateCameraStatus(msg, "red");
            });
    }

    function stopCamera() {
        if (stream) {
            stream.getTracks().forEach(function (t) { t.stop(); });
            stream = null;
        }
        cameraReady = false;
    }

    // ---- Frame capture & processing ----
    function captureFrame() {
        if (!cameraReady || !video.videoWidth || !video.videoHeight) {
            return null;
        }

        var ratio = Math.min(
            FRAME_MAX_WIDTH / video.videoWidth,
            FRAME_MAX_HEIGHT / video.videoHeight,
            1
        );
        var drawWidth = Math.round(video.videoWidth * ratio);
        var drawHeight = Math.round(video.videoHeight * ratio);

        canvas.width = drawWidth;
        canvas.height = drawHeight;
        var ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, drawWidth, drawHeight);

        // Use JPEG at 0.8 quality for a smaller payload
        return canvas.toDataURL("image/jpeg", 0.8);
    }

    function startCaptureLoop() {
        if (captureInterval) {
            clearInterval(captureInterval);
        }
        captureInterval = setInterval(function () {
            if (processing || cooldownActive) {
                return;
            }
            processFrame();
        }, FRAME_INTERVAL_MS);
    }

    function processFrame() {
        if (processing || cooldownActive || !cameraReady) {
            return;
        }

        var dataURL = captureFrame();
        if (!dataURL) {
            return;
        }

        processing = true;
        updateCameraStatus("Recognizing face...", "blue");

        var fd = new FormData();
        fd.append("image_data", dataURL);
        fd.append("mode", currentMode);

        fetch(window.AUTO_ATTENDANCE_URLS.autoProcess, {
            method: "POST",
            body: fd,
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                processing = false;
                handleProcessResponse(data);
            })
            .catch(function () {
                processing = false;
                updateCameraStatus("Network error. Retrying...", "red");
            });
    }

    function handleProcessResponse(data) {
        if (data.status === "error") {
            updateCameraStatus(data.message || "Server error.", "red");
            return;
        }

        // Multiple faces
        if (data.multiple_faces) {
            showWaiting();
            updateCameraStatus(data.message, "red");
            showFaceOverlay(true);
            showPrompt("Please ensure only one employee is in front of the camera.");
            return;
        }

        // No face detected
        if (data.no_face) {
            showWaiting();
            updateCameraStatus("Camera active. Waiting for face...", "blue");
            return;
        }

        // Face recognized
        if (data.recognized && data.employee) {
            showEmployeeCard(data.employee);
            updateCameraStatus("Face recognized! " +
                data.employee.first_name + " " + data.employee.last_name, "green");
            showFaceOverlay(true);

            // Already checked in today (check-in mode)
            if (data.already_checked_in) {
                showAttendanceResult(
                    '<div class="alert alert-info mb-0">' +
                    '<i class="bi bi-info-circle me-1"></i>' +
                    '<strong>Already Checked In Today</strong><br>' +
                    '<small>Check-in time: ' + formatDateTime(data.check_in_time) + '</small>' +
                    '</div>',
                    "info"
                );
                startCooldown();
                return;
            }

            // Already checked out today (check-out mode)
            if (data.already_checked_out) {
                showAttendanceResult(
                    '<div class="alert alert-info mb-0">' +
                    '<i class="bi bi-info-circle me-1"></i>' +
                    '<strong>Already Checked Out Today</strong><br>' +
                    '<small>Check-out time: ' + formatDateTime(data.check_out_time) + '</small>' +
                    '</div>',
                    "info"
                );
                startCooldown();
                return;
            }

            // No check-in for check-out mode
            if (data.no_check_in) {
                showAttendanceResult(
                    '<div class="alert alert-warning mb-0">' +
                    '<i class="bi bi-exclamation-triangle me-1"></i>' +
                    '<strong>Not Checked In</strong><br>' +
                    '<small>' + data.message + '</small>' +
                    '</div>',
                    "warning"
                );
                startCooldown();
                return;
            }

            // Successful check-in
            if (data.action === "check-in") {
                showAttendanceResult(
                    '<div class="kiosk-success-card">' +
                    '<div class="d-flex align-items-center mb-3">' +
                    '<i class="bi bi-check-circle-fill display-4 text-success me-3"></i>' +
                    '<div>' +
                    '<h3 class="h3 mb-0 text-success">CHECK-IN SUCCESSFUL</h3>' +
                    '<div class="text-muted small">Welcome, ' +
                    escapeHtml(data.employee.first_name + " " + data.employee.last_name) +
                    '</div>' +
                    '</div>' +
                    '</div>' +
                    '<div class="kiosk-result-details">' +
                    '<div class="row g-3 text-center">' +
                    '<div class="col-6">' +
                    '<div class="text-muted small">Employee ID</div>' +
                    '<div class="fw-bold fs-5">' + escapeHtml(data.employee.employee_id) + '</div>' +
                    '</div>' +
                    '<div class="col-6">' +
                    '<div class="text-muted small">Time</div>' +
                    '<div class="fw-bold fs-5">' + formatDateTime(data.check_in_time) + '</div>' +
                    '</div>' +
                    '</div>' +
                    '</div>' +
                    '</div>',
                    "success"
                );
                lastRecognizedEmployeeId = data.employee.employee_id;
                startCooldown();
                return;
            }

            // Successful check-out
            if (data.action === "check-out") {
                showAttendanceResult(
                    '<div class="kiosk-success-card">' +
                    '<div class="d-flex align-items-center mb-3">' +
                    '<i class="bi bi-check-circle-fill display-4 text-success me-3"></i>' +
                    '<div>' +
                    '<h3 class="h3 mb-0 text-success">CHECK-OUT SUCCESSFUL</h3>' +
                    '<div class="text-muted small">Goodbye, ' +
                    escapeHtml(data.employee.first_name + " " + data.employee.last_name) +
                    '</div>' +
                    '</div>' +
                    '</div>' +
                    '<div class="kiosk-result-details">' +
                    '<div class="row g-3 text-center">' +
                    '<div class="col-6">' +
                    '<div class="text-muted small">Employee ID</div>' +
                    '<div class="fw-bold fs-5">' + escapeHtml(data.employee.employee_id) + '</div>' +
                    '</div>' +
                    '<div class="col-6">' +
                    '<div class="text-muted small">Time</div>' +
                    '<div class="fw-bold fs-5">' + formatDateTime(data.check_out_time) + '</div>' +
                    '</div>' +
                    '</div>' +
                    '</div>' +
                    '</div>',
                    "success"
                );
                lastRecognizedEmployeeId = data.employee.employee_id;
                startCooldown();
                return;
            }
        }

        // Unknown face — show manual fallback
        if (data.unknown || data.manual) {
            showManualFallback(data.message || "Face not recognized.");
            updateCameraStatus("Face not recognized. Use manual fallback below.", "red");
            showFaceOverlay(false);
            return;
        }

        // Default: waiting
        showWaiting();
        updateCameraStatus("Camera active. Please stand in front of the camera.", "blue");
    }

    // ---- Manual fallback ----
    function submitManual() {
        var empId = manualEmployeeId.value.trim();
        if (!empId) {
            return;
        }

        manualSubmitBtn.disabled = true;
        manualSubmitBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i> Recording...';

        var fd = new FormData();
        fd.append("employee_id", empId);
        fd.append("via_face", "false");
        fd.append("action", currentMode);

        fetch(window.AUTO_ATTENDANCE_URLS.markAttendance, {
            method: "POST",
            body: fd,
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                manualSubmitBtn.disabled = false;
                manualSubmitBtn.innerHTML = '<i class="bi bi-check me-1"></i> Submit';

                if (data.status === "ok") {
                    // Fetch employee info for display
                    fetch(window.AUTO_ATTENDANCE_URLS.checkStatus + "?employee_id=" +
                        encodeURIComponent(empId))
                        .then(function (r) { return r.json(); })
                        .then(function (info) {
                            if (info.status === "ok" && info.employee) {
                                showEmployeeCard(info.employee);
                            }
                            if (currentMode === "check-in") {
                                showAttendanceResult(
                                    '<div class="kiosk-success-card">' +
                                    '<div class="d-flex align-items-center mb-3">' +
                                    '<i class="bi bi-check-circle-fill display-4 text-success me-3"></i>' +
                                    '<div>' +
                                    '<h3 class="h3 mb-0 text-success">CHECK-IN SUCCESSFUL</h3>' +
                                    '<div class="text-muted small">Welcome, ' +
                                    escapeHtml(info.employee ? (info.employee.first_name + " " + info.employee.last_name) : empId) +
                                    '</div>' +
                                    '</div>' +
                                    '</div>' +
                                    '<div class="kiosk-result-details">' +
                                    '<div class="row g-3 text-center">' +
                                    '<div class="col-6">' +
                                    '<div class="text-muted small">Employee ID</div>' +
                                    '<div class="fw-bold fs-5">' + escapeHtml(empId) + '</div>' +
                                    '</div>' +
                                    '<div class="col-6">' +
                                    '<div class="text-muted small">Time</div>' +
                                    '<div class="fw-bold fs-5">' + formatDateTime(new Date().toISOString()) + '</div>' +
                                    '</div>' +
                                    '</div>' +
                                    '</div>' +
                                    '</div>',
                                    "success"
                                );
                            } else {
                                showAttendanceResult(
                                    '<div class="kiosk-success-card">' +
                                    '<div class="d-flex align-items-center mb-3">' +
                                    '<i class="bi bi-check-circle-fill display-4 text-success me-3"></i>' +
                                    '<div>' +
                                    '<h3 class="h3 mb-0 text-success">CHECK-OUT SUCCESSFUL</h3>' +
                                    '<div class="text-muted small">Goodbye, ' +
                                    escapeHtml(info.employee ? (info.employee.first_name + " " + info.employee.last_name) : empId) +
                                    '</div>' +
                                    '</div>' +
                                    '</div>' +
                                    '<div class="kiosk-result-details">' +
                                    '<div class="row g-3 text-center">' +
                                    '<div class="col-6">' +
                                    '<div class="text-muted small">Employee ID</div>' +
                                    '<div class="fw-bold fs-5">' + escapeHtml(empId) + '</div>' +
                                    '</div>' +
                                    '<div class="col-6">' +
                                    '<div class="text-muted small">Time</div>' +
                                    '<div class="fw-bold fs-5">' + formatDateTime(new Date().toISOString()) + '</div>' +
                                    '</div>' +
                                    '</div>' +
                                    '</div>' +
                                    '</div>',
                                    "success"
                                );
                            }
                            startCooldown();
                        })
                        .catch(function () {
                            showAttendanceResult(
                                '<div class="alert alert-success mb-0">' +
                                '<i class="bi bi-check-circle me-1"></i>' +
                                escapeHtml(data.message || "Attendance recorded.") +
                                '</div>',
                                "success"
                            );
                            startCooldown();
                        });
                } else {
                    showAttendanceResult(
                        '<div class="alert alert-danger mb-0">' +
                        '<i class="bi bi-x-circle me-1"></i>' +
                        escapeHtml(data.message || "Operation failed.") +
                        '</div>',
                        "danger"
                    );
                }
            })
            .catch(function () {
                manualSubmitBtn.disabled = false;
                manualSubmitBtn.innerHTML = '<i class="bi bi-check me-1"></i> Submit';
                showAttendanceResult(
                    '<div class="alert alert-danger mb-0">' +
                    '<i class="bi bi-x-circle me-1"></i>An error occurred while recording attendance.' +
                    '</div>',
                    "danger"
                );
            });
    }

    // ---- Init ----
    document.addEventListener("DOMContentLoaded", function () {
        // Update date/time immediately and every second
        updateDateTime();
        setInterval(updateDateTime, 1000);

        // Set up mode toggle
        modeCheckin.addEventListener("click", function () { setMode("check-in"); });
        modeCheckout.addEventListener("click", function () { setMode("check-out"); });

        // Manual fallback submit
        manualEmployeeId.addEventListener("input", function () {
            manualSubmitBtn.disabled = this.value.trim().length > 0;
        });
        manualSubmitBtn.addEventListener("click", submitManual);

        // Start the camera
        startCamera();
    });

    // ---- Cleanup on page unload ----
    window.addEventListener("beforeunload", function () {
        if (captureInterval) {
            clearInterval(captureInterval);
        }
        if (cooldownTimer) {
            clearTimeout(cooldownTimer);
        }
        stopCamera();
    });
})();
