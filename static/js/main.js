/* ============================================================
   main.js
   =======
   SmartFactoryAttendance — Core Industrial Dashboard Client Logic
   Provides:
   - Dynamic Navigation & Breadcrumbs
   - Live Plant System Clock (IST / UTC)
   - Mobile Sidebar Toggle & Backdrop
   - Lucide Icons Initialization
   - Real-time System Status Health Polling
   - HTML Escaping & Formatting Utilities
   ============================================================ */

document.addEventListener("DOMContentLoaded", function () {
    initLucideIcons();
    initNavigation();
    initPlantClock();
    initSidebarToggle();
    initTooltips();
    checkQuickSystemStatus();
});

/**
 * Initialize Lucide icons if loaded.
 */
function initLucideIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
        window.lucide.createIcons();
    }
}

/**
 * Highlight active navigation item based on current location.
 */
function initNavigation() {
    var currentPath = window.location.pathname;
    var navLinks = document.querySelectorAll(".sidebar-nav-item");

    navLinks.forEach(function (link) {
        var linkPath = link.getAttribute("href");
        if (linkPath) {
            // Check exact or subpath match
            if (linkPath === "/" && currentPath === "/") {
                link.classList.add("active");
            } else if (linkPath !== "/" && currentPath.indexOf(linkPath) === 0) {
                link.classList.add("active");
            }
        }
    });
}

/**
 * Live plant clock running in top navigation bar.
 */
function initPlantClock() {
    var clockEl = document.getElementById("topbar-live-clock");
    if (!clockEl) return;

    function updateTime() {
        var now = new Date();
        var year = now.getFullYear();
        var month = String(now.getMonth() + 1).padStart(2, "0");
        var day = String(now.getDate()).padStart(2, "0");
        var hours = String(now.getHours()).padStart(2, "0");
        var minutes = String(now.getMinutes()).padStart(2, "0");
        var seconds = String(now.getSeconds()).padStart(2, "0");

        clockEl.textContent = year + "-" + month + "-" + day + " " + hours + ":" + minutes + ":" + seconds;
    }

    updateTime();
    setInterval(updateTime, 1000);
}

/**
 * Sidebar drawer toggle for mobile screens.
 */
function initSidebarToggle() {
    var toggleBtn = document.getElementById("sidebar-toggle");
    var sidebar = document.getElementById("app-sidebar");
    if (!toggleBtn || !sidebar) return;

    toggleBtn.addEventListener("click", function () {
        sidebar.classList.toggle("show");
    });

    // Close on outside click on mobile
    document.addEventListener("click", function (e) {
        if (window.innerWidth <= 992) {
            if (!sidebar.contains(e.target) && !toggleBtn.contains(e.target)) {
                sidebar.classList.remove("show");
            }
        }
    });
}

/**
 * Initialize Bootstrap tooltips.
 */
function initTooltips() {
    if (window.bootstrap && typeof window.bootstrap.Tooltip === "function") {
        var tooltipTriggerList = [].slice.call(
            document.querySelectorAll('[data-bs-toggle="tooltip"]')
        );
        tooltipTriggerList.forEach(function (el) {
            new bootstrap.Tooltip(el);
        });
    }
}

/**
 * Check overall system health in background.
 */
function checkQuickSystemStatus() {
    var indicator = document.getElementById("topbar-status-indicator");
    if (!indicator) return;

    fetch("/api/system-status")
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.status === "ok") {
                var allHealthy = data.database_healthy && data.face_model_available && data.ppe_model_available;
                if (allHealthy) {
                    indicator.className = "pulse-indicator";
                    indicator.title = "All AI Models & Services Online";
                } else {
                    indicator.className = "pulse-indicator";
                    indicator.style.background = "var(--warning)";
                    indicator.style.boxShadow = "0 0 8px var(--warning)";
                    indicator.title = "Some AI Services Offline";
                }
            }
        })
        .catch(function () {
            // Keep default indicator if endpoint not reachable
        });
}

/**
 * Escape HTML in dynamic strings to prevent XSS.
 */
function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

/**
 * Format ISO datetime string to localized string.
 */
function formatDateTime(isoStr) {
    if (!isoStr) return "-";
    try {
        var d = new Date(isoStr);
        if (isNaN(d.getTime())) return isoStr;
        return d.toLocaleString();
    } catch (e) {
        return isoStr;
    }
}

/**
 * Format ISO date string.
 */
function formatDate(isoStr) {
    if (!isoStr) return "-";
    try {
        var d = new Date(isoStr);
        if (isNaN(d.getTime())) return isoStr;
        return d.toLocaleDateString();
    } catch (e) {
        return isoStr;
    }
}

/**
 * Show a dismissible alert inside a container element.
 */
function showAlert(containerId, message, type) {
    type = type || "info";
    var container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML =
        "<div class='alert alert-" + type + " alert-dismissible fade show' role='alert'>" +
        message +
        "<button type='button' class='btn-close btn-close-white' data-bs-dismiss='alert' aria-label='Close'></button>" +
        "</div>";
    initLucideIcons();
}

/**
 * Fetch JSON helper with error tolerance.
 */
function fetchJSON(url, options) {
    options = options || {};
    return fetch(url, options)
        .then(function (response) {
            return response.json().catch(function () {
                return { status: "error", message: "Server response could not be parsed." };
            });
        });
}
