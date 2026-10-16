# Task: Persist Attendance Method (Face Recognition / Manual)

## Goal
Add persistence of the attendance method ("face_recognition" or "manual") to
the attendance record so the system records how each check-in was performed.
Keep the existing face attendance workflow, PPE logic, model, and weights
untouched.

## Plan
- [x] 0. Baseline established: 72 tests pass (face attendance workflow already implemented).
- [x] 1. Add `attendance_method` column to `models/attendance.py` (nullable, default 'manual').
- [x] 2. Add `attendance_method` column to `database/schema.sql`.
- [x] 3. Update `services/attendance_service.py` `check_in()` to accept and persist `attendance_method`.
- [x] 4. Update `routes/face_attendance.py` `/mark` to pass method based on `via_face`.
- [x] 5. Update `routes/attendance.py` `_serialize_record` to include `attendance_method` (via `to_dict`).
- [x] 6. Update `templates/attendance.html` records table to display the method.
- [x] 7. Update tests (`test_face_attendance.py`, `test_attendance.py`) to assert method persistence.
- [x] 8. Run full pytest suite and confirm all tests pass (73 passed).
</content>
