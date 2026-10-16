# Smart Factory Attendance with Safety Gear Check

A production-ready Flask web application for managing factory employee attendance with integrated safety gear (PPE) verification using computer vision.

## Features

- **Employee Attendance Tracking** — Check-in/check-out with timestamp logging
- **Safety Gear Detection** — Automated PPE compliance checks (helmet, vest, boots)
- **Dashboard** — Real-time overview of attendance and safety compliance
- **Notifications** — Alerts for non-compliance and attendance anomalies
- **REST API** — Endpoints for integration with external systems

## Real PPE Detection

The safety check pipeline is wired to a pluggable PPE detector (`services/ppe_detector.py`).
When a trained YOLO model is configured, uploaded images are actually analyzed and the
result shows detected gear, missing gear, confidence score, and COMPLIANT / NON-COMPLIANT
status. When no model is configured, the app **never fabricates detection results** — it
returns a clear `503` with code `PPE_MODEL_UNAVAILABLE` and an explanation.

### Required model

A YOLO weights file (e.g. `best.pt`) trained on **these classes**:

| Class   | Required for compliance |
|---------|-------------------------|
| helmet  | Yes                     |
| vest    | Yes                     |
| gloves  | No (detected, not required) |
| boots   | Yes                     |

An employee is considered **COMPLIANT** when **helmet + vest + boots** are
detected. `gloves` is still detected and reported in the results, but it is
**not part of the required compliance set** — a missing pair of gloves no
longer makes an employee non-compliant.

The model may also output a `human` class, which is detected but **ignored for
PPE compliance** (it confirms a person is present but never affects the
verdict).

### Enable real detection

The repository ships with a real model at `weights/best.pt` and it is used by
**default**. No extra configuration is required to enable real PPE detection.

1. Ensure the detection runtime is installed:
   ```bash
   pip install ultralytics
   ```
2. (Optional) Override the model path via the `PPE_MODEL_PATH` env var in your
   `.env`:
   ```bash
   export PPE_MODEL_PATH=/path/to/best.pt
   ```
3. Start the app. The safety check page will indicate the model is active, and
   uploads will produce real detection results (detected gear, missing gear,
   confidence score, per-detection details, and COMPLIANT / NON-COMPLIANT
   status).

Optional tuning via `PPE_CONFIDENCE_THRESHOLD` (default `0.35`).

## Project Structure

```
SmartFactoryAttendance/
├── app.py                  # Main Flask application entry point
├── config.py               # Configuration settings
├── requirements.txt        # Python dependencies
├── README.md               # Project documentation
├── .gitignore              # Git ignore rules
├── routes/                 # Route handlers (Flask Blueprints)
│   ├── __init__.py
│   ├── attendance.py
│   ├── safety_gear.py
│   └── dashboard.py
├── models/                 # Data models
│   ├── __init__.py
│   ├── employee.py
│   ├── attendance.py
│   └── safety_check.py
├── services/               # Business logic layer
│   ├── __init__.py
│   ├── attendance_service.py
│   ├── safety_gear_service.py
│   └── notification_service.py
├── database/               # Database layer
│   ├── __init__.py
│   ├── db_setup.py
│   └── schema.sql
├── utils/                  # Utility helpers
│   ├── __init__.py
│   ├── helpers.py
│   └── validators.py
├── templates/              # Jinja2 HTML templates
│   ├── base.html
│   ├── dashboard.html
│   ├── attendance.html
│   └── safety_check.html
└── static/                 # Static assets
    ├── css/
    │   └── style.css
    ├── js/
    │   └── main.js
    └── images/
        └── .gitkeep
```

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd SmartFactoryAttendance
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate        # Linux/Mac
   venv\Scripts\activate           # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env            # Create .env file (if provided)
   ```

5. **Initialize the database**
   The database tables are created automatically on first run via `init_db()` in `app.py`. No manual step is required.

6. **Run the application**
   ```bash
   python app.py
   ```

7. **Access the application**
   Open your browser at `http://127.0.0.1:5000`

## Configuration

The application supports three environments via `config.py`:

| Environment | Class               | Description                     |
|-------------|---------------------|---------------------------------|
| Development | `DevelopmentConfig` | Debug mode, SQLite database     |
| Production  | `ProductionConfig`  | No debug, production DB         |
| Testing     | `TestingConfig`     | In-memory database for tests    |

Set the environment using the `FLASK_ENV` variable:
```bash
export FLASK_ENV=development
```

## Usage

- **Dashboard**: View attendance and safety compliance overview
- **Attendance**: Mark and review employee check-in/check-out
- **Safety Check**: Upload images/video for PPE detection

## Running Tests

The project includes a pytest test suite covering the main, attendance, safety gear, and dashboard blueprints.

```bash
pip install -r requirements.txt
pytest tests/ -v
```

> **Note:** The pinned versions in `requirements.txt` (e.g., Flask 3.0.0, SQLAlchemy 2.0.23, Pillow 10.2.0) predate Python 3.14 and may not install cleanly on it. For Python 3.14, install the latest compatible versions instead:
> ```bash
> pip install flask flask-sqlalchemy sqlalchemy pytest
> ```

## Tech Stack

| Layer        | Technology                  |
|--------------|-----------------------------|
| Backend      | Flask (Python)              |
| Database     | SQLAlchemy + SQLite/PostgreSQL |
| Frontend     | Jinja2, HTML, CSS, JS       |
| AI/CV        | Ultralytics YOLO (PPE detector) |
| Deployment   | Gunicorn (WSGI)             |

## License

This project is licensed under the MIT License.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Commit changes (`git commit -m "Add new feature"`)
4. Push to branch (`git push origin feature/new-feature`)
5. Open a Pull Request