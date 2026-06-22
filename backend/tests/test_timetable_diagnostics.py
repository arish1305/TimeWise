import copy
import logging

from timetable_diagnostics import log_generation_payload_diagnostics


def test_backend_generation_diagnostics_verifies_payload_without_mutation(caplog):
    subjects = [
        {
            "id": 1,
            "name": "Programming in Java",
            "weekly_hours": 3,
            "continuous_hours": 2,
            "faculty_id": 10,
            "faculty_ids": [10],
            "department_locked_slots": [1],
            "section_override_slots": [2],
            "section_override_applied": True,
            "lock_source": "Section Override",
            "is_cbcs_shared": False,
            "is_elective": False,
        }
    ]
    faculty = [{"id": 10, "name": "Dr. One"}]
    timeslots = [
        {"id": 1, "day": "Monday", "time": "09:00:00", "is_break": False},
        {"id": 2, "day": "Tuesday", "time": "10:00:00", "is_break": False},
    ]
    locked_slots = [
        {
            "subject_id": 1,
            "faculty_id": 10,
            "faculty_ids": [10],
            "timeslot_id": 2,
            "lock_source": "Section Override",
        }
    ]
    constraints = {
        "faculty_availability": {
            10: {"preferred_slots": [1], "unavailable_slots": []},
        },
        "prior_commitments": {10: []},
        "prior_commitment_entries": {10: []},
        "approved_commitments": {10: []},
    }
    original = copy.deepcopy((subjects, faculty, timeslots, locked_slots, constraints))

    with caplog.at_level(logging.INFO, logger="timewise.backend.timetable_diagnostics"):
        log_generation_payload_diagnostics(
            section={"id": 7, "name": "A"},
            department={"id": 3, "name": "Computer Science"},
            semester=4,
            subjects=subjects,
            faculty=faculty,
            timeslots=timeslots,
            locked_slots=locked_slots,
            constraints=constraints,
            database_subject_ids=[1],
            database_faculty_ids=[10],
        )

    assert "BACKEND TIMETABLE GENERATION SUMMARY" in caplog.text
    assert "Programming in Java" in caplog.text
    assert "AI PAYLOAD VERIFICATION" in caplog.text
    assert "Database Match: YES" in caplog.text
    assert (subjects, faculty, timeslots, locked_slots, constraints) == original

