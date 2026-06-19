from datetime import time

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import sys
import os
from pathlib import Path

# Add ai_engine to path so we can import scheduler_core
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT.parent / "ai_engine"))

from scheduler_core.cp_sat_solver import CPSatSolver
import models
from database import Base
from routers.timetable import (
    COMMITMENT_STATUSES,
    _attempt_duplicate_repair,
    _is_duplicate_section_timetable,
    _timetable_signature,
    _section_similarity_score,
    _build_faculty_timetable_payload,
    validate_timetable_internal,
)

def _solve_timetable_locally(subjects, faculty, timeslots, constraints, locked_slots):
    # Map 'credits' to 'weekly_hours' if any test data uses 'credits' instead of 'weekly_hours'
    for s in subjects:
        if "weekly_hours" not in s:
            s["weekly_hours"] = s.get("credits") or 1
            
    # Normalize timeslots for the capacity check
    for t in timeslots:
        if "is_break" not in t:
            t["is_break"] = False
            
    solver = CPSatSolver(
        subjects=subjects,
        faculty=faculty,
        timeslots=timeslots,
        constraints=constraints,
        locked_slots=locked_slots
    )
    return solver.solve()


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_faculty_timetable_includes_multiple_subjects_for_same_faculty():
    db = make_session()

    department = models.Department(name="Computer Science", code="CSE")
    year = models.AcademicYear(name="Year 2", level=2, department=department)
    section_a = models.Section(name="A", academic_year=year)
    section_b = models.Section(name="B", academic_year=year)
    faculty = models.Faculty(name="Dr. Multi", faculty_id_code="FAC100")
    subject_one = models.Subject(
        name="Data Structures",
        code="CS201",
        department=department,
        semester=3,
        weekly_hours=1,
    )
    subject_two = models.Subject(
        name="Operating Systems",
        code="CS202",
        department=department,
        semester=3,
        weekly_hours=1,
    )
    slot_one = models.TimeSlot(day="Monday", start_time=time(9, 0), end_time=time(10, 0))
    slot_two = models.TimeSlot(day="Tuesday", start_time=time(10, 0), end_time=time(11, 0))
    timetable_a = models.Timetable(section=section_a, semester=3, status="DRAFT")
    timetable_b = models.Timetable(section=section_b, semester=3, status="ACTIVE")

    db.add_all([
        department,
        year,
        section_a,
        section_b,
        faculty,
        subject_one,
        subject_two,
        slot_one,
        slot_two,
        timetable_a,
        timetable_b,
    ])
    db.flush()

    db.add_all([
        models.TimetableEntry(
            timetable=timetable_a,
            subject=subject_one,
            faculty=faculty,
            timeslot=slot_one,
        ),
        models.TimetableEntry(
            timetable=timetable_b,
            subject=subject_two,
            faculty=faculty,
            timeslot=slot_two,
        ),
    ])
    db.commit()

    payload = _build_faculty_timetable_payload(faculty, db)

    assert {entry["subject_code"] for entry in payload["entries"]} == {"CS201", "CS202"}
    assert {entry["section_name"] for entry in payload["entries"]} == {"A", "B"}
    assert {entry["timetable_status"] for entry in payload["entries"]} == {"DRAFT", "ACTIVE"}


def test_subject_code_can_repeat_across_departments_but_not_within_one_department():
    db = make_session()

    ai = models.Department(name="Artificial Intelligence", code="AI")
    bct = models.Department(name="Blockchain Technology", code="BCT")
    db.add_all([ai, bct])
    db.flush()

    db.add_all([
        models.Subject(name="Software Project Management", code="SCSB400", department=ai, semester=7),
        models.Subject(name="Software Project Management", code="SCSB400", department=bct, semester=7),
    ])
    db.commit()

    db.add(models.Subject(name="Duplicate", code="SCSB400", department=ai, semester=7))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    else:
        raise AssertionError("Duplicate subject code in the same department should fail")


def test_section_conflict_is_reported_for_unrelated_subjects_in_same_slot():
    db = make_session()

    department = models.Department(name="AI", code="AI")
    year = models.AcademicYear(name="Year 3", level=3, department=department)
    section = models.Section(name="A1", academic_year=year)
    slot = models.TimeSlot(day="Monday", start_time=time(9, 0), end_time=time(10, 0), department_id=1)
    subject_one = models.Subject(name="Subject One", code="S1", department=department, semester=5, weekly_hours=1)
    subject_two = models.Subject(name="Subject Two", code="S2", department=department, semester=5, weekly_hours=1)
    timetable = models.Timetable(section=section, semester=5, status="DRAFT")

    db.add_all([department, year, section, slot, subject_one, subject_two, timetable])
    db.flush()
    db.add_all([
        models.TimetableEntry(timetable=timetable, subject=subject_one, timeslot=slot),
        models.TimetableEntry(timetable=timetable, subject=subject_two, timeslot=slot),
    ])
    db.commit()

    result = validate_timetable_internal(timetable, db)

    assert result["status"] == "FAIL"
    assert "Multiple unrelated subjects overlap" in result["errors"][0]


def test_validation_fails_for_faculty_unavailable_slot():
    db = make_session()

    department = models.Department(name="AI Availability", code="AIA")
    year = models.AcademicYear(name="Year 3", level=3, department=department)
    section = models.Section(name="A", academic_year=year)
    faculty = models.Faculty(name="Dr. Busy", faculty_id_code="BUSY1")
    slot = models.TimeSlot(day="Monday", start_time=time(9, 0), end_time=time(10, 0), department_id=1)
    subject = models.Subject(name="ML", code="ML501", department=department, semester=5, weekly_hours=1)
    timetable = models.Timetable(section=section, semester=5, status="DRAFT")

    db.add_all([department, year, section, faculty, slot, subject, timetable])
    db.flush()
    db.add_all([
        models.FacultyAvailability(
            faculty=faculty,
            timeslot=slot,
            status=models.FacultyAvailabilityStatus.UNAVAILABLE.value,
        ),
        models.TimetableEntry(timetable=timetable, subject=subject, faculty=faculty, timeslot=slot),
    ])
    db.commit()

    result = validate_timetable_internal(timetable, db)

    assert result["status"] == "FAIL"
    assert any("Faculty availability violation" in error for error in result["errors"])


def test_validation_reports_approved_commitment_conflict():
    db = make_session()

    department = models.Department(name="AI Commitment", code="AIC")
    year = models.AcademicYear(name="Year 3", level=3, department=department)
    section_a = models.Section(name="A", academic_year=year)
    section_b = models.Section(name="B", academic_year=year)
    faculty = models.Faculty(name="Dr. Committed", faculty_id_code="COM1")
    slot = models.TimeSlot(day="Tuesday", start_time=time(10, 0), end_time=time(11, 0), department_id=1)
    subject_one = models.Subject(name="NLP", code="NLP501", department=department, semester=5, weekly_hours=1)
    subject_two = models.Subject(name="RL", code="RL501", department=department, semester=5, weekly_hours=1)
    approved = models.Timetable(section=section_a, semester=5, status="APPROVED")
    draft = models.Timetable(section=section_b, semester=5, status="DRAFT")

    db.add_all([department, year, section_a, section_b, faculty, slot, subject_one, subject_two, approved, draft])
    db.flush()
    db.add_all([
        models.TimetableEntry(timetable=approved, subject=subject_one, faculty=faculty, timeslot=slot),
        models.TimetableEntry(timetable=draft, subject=subject_two, faculty=faculty, timeslot=slot),
    ])
    db.commit()

    result = validate_timetable_internal(draft, db)

    assert result["status"] == "FAIL"
    assert any("Faculty commitment conflict" in error for error in result["errors"])


def test_draft_timetables_are_treated_as_faculty_commitments():
    assert "DRAFT" in COMMITMENT_STATUSES

    schedule = _solve_timetable_locally(
        subjects=[
            {"id": 1, "name": "Operating Systems", "credits": 1, "faculty_id": 10},
        ],
        faculty=[{"id": 10, "name": "Dr. Multi"}],
        timeslots=[
            {"id": 101, "day": "Monday", "time": "09:00:00"},
            {"id": 102, "day": "Monday", "time": "10:00:00"},
        ],
        constraints={
            "prior_commitments": {10: [101]},
            "prior_commitment_entries": {10: [{"timeslot_id": 101, "subject_id": 99}]},
            "faculty_preferences": {10: {"max_hours": 18}},
        },
        locked_slots=[],
    )

    assert schedule == [{"subject_id": 1, "faculty_id": 10, "timeslot_id": 102}]


def test_local_solver_spreads_subject_across_different_time_keys_when_possible():
    schedule = _solve_timetable_locally(
        subjects=[
            {"id": 1, "name": "Distributed Systems", "credits": 3, "faculty_id": None},
        ],
        faculty=[],
        timeslots=[
            {"id": 1, "day": "Monday", "time": "09:00:00"},
            {"id": 2, "day": "Monday", "time": "10:00:00"},
            {"id": 3, "day": "Tuesday", "time": "09:00:00"},
            {"id": 4, "day": "Tuesday", "time": "10:00:00"},
            {"id": 5, "day": "Wednesday", "time": "09:00:00"},
            {"id": 6, "day": "Wednesday", "time": "10:00:00"},
        ],
        constraints={"rules": {"spread_subjects": True}, "random_seed": 12345},
        locked_slots=[],
    )

    chosen_slots = {entry["timeslot_id"] for entry in schedule}
    slot_to_time = {
        1: "09:00:00",
        2: "10:00:00",
        3: "09:00:00",
        4: "10:00:00",
        5: "09:00:00",
        6: "10:00:00",
    }
    chosen_time_keys = {slot_to_time[slot_id] for slot_id in chosen_slots}

    assert len(schedule) == 3
    assert len(chosen_time_keys) >= 2


def test_duplicate_section_timetable_is_reported_as_hard_fail():
    db = make_session()

    department = models.Department(name="CSE", code="CSE")
    db.add(department)
    db.flush()

    year = models.AcademicYear(name="Year 3", level=3, department=department)
    section_a = models.Section(name="A", academic_year=year, section_name="A", year=3, independent_schedule=True)
    section_b = models.Section(name="B", academic_year=year, section_name="B", year=3, independent_schedule=True)
    slot_1 = models.TimeSlot(day="Monday", start_time=time(9, 0), end_time=time(10, 0), department_id=department.id)
    slot_2 = models.TimeSlot(day="Tuesday", start_time=time(10, 0), end_time=time(11, 0), department_id=department.id)
    subject = models.Subject(name="Compiler Design", code="CS301", department=department, semester=5, weekly_hours=2)
    tt_a = models.Timetable(section=section_a, semester=5, status="ACTIVE")
    tt_b = models.Timetable(section=section_b, semester=5, status="DRAFT")

    db.add_all([year, section_a, section_b, slot_1, slot_2, subject, tt_a, tt_b])
    db.flush()

    db.add_all([
        models.TimetableEntry(timetable=tt_a, subject=subject, timeslot=slot_1),
        models.TimetableEntry(timetable=tt_a, subject=subject, timeslot=slot_2),
        models.TimetableEntry(timetable=tt_b, subject=subject, timeslot=slot_1),
        models.TimetableEntry(timetable=tt_b, subject=subject, timeslot=slot_2),
    ])
    db.commit()

    result = validate_timetable_internal(tt_b, db)

    assert result["status"] == "FAIL"
    assert any("Section uniqueness conflict" in error for error in result["errors"])


def test_timetable_signature_ignores_elective_and_cbcs_entries():
    db = make_session()

    department = models.Department(name="CSE2", code="CSE2")
    db.add(department)
    db.flush()

    year = models.AcademicYear(name="Year 4", level=4, department=department)
    section = models.Section(name="A", academic_year=year, section_name="A", year=4, independent_schedule=True)
    slot_1 = models.TimeSlot(day="Monday", start_time=time(9, 0), end_time=time(10, 0), department_id=department.id)
    slot_2 = models.TimeSlot(day="Tuesday", start_time=time(10, 0), end_time=time(11, 0), department_id=department.id)
    elective = models.Subject(
        name="Open Elective",
        code="OE401",
        department=department,
        semester=7,
        weekly_hours=1,
        is_elective=True,
        elective_group_id="OE",
    )
    cbcs = models.Subject(
        name="Shared CBCS",
        code="CB401",
        department=department,
        semester=7,
        weekly_hours=1,
        allowed_department_ids=[999],
    )
    regular = models.Subject(name="Compiler", code="CS401", department=department, semester=7, weekly_hours=1)
    timetable = models.Timetable(section=section, semester=7, status="DRAFT")

    db.add_all([year, section, slot_1, slot_2, elective, cbcs, regular, timetable])
    db.flush()
    db.add_all([
        models.TimetableEntry(timetable=timetable, subject=elective, timeslot=slot_1),
        models.TimetableEntry(timetable=timetable, subject=cbcs, timeslot=slot_1),
        models.TimetableEntry(timetable=timetable, subject=regular, timeslot=slot_2),
    ])
    db.commit()
    db.refresh(timetable)

    assert _timetable_signature(timetable) == ((slot_2.id, regular.id),)


def test_duplicate_section_timetable_is_auto_repaired_when_free_slot_exists():
    db = make_session()

    department = models.Department(name="IT", code="IT")
    db.add(department)
    db.flush()

    year = models.AcademicYear(name="Year 2", level=2, department=department)
    section_a = models.Section(name="A", academic_year=year, section_name="A", year=2, independent_schedule=True)
    section_b = models.Section(name="B", academic_year=year, section_name="B", year=2, independent_schedule=True)
    slot_1 = models.TimeSlot(day="Monday", start_time=time(9, 0), end_time=time(10, 0), department_id=department.id)
    slot_2 = models.TimeSlot(day="Monday", start_time=time(10, 0), end_time=time(11, 0), department_id=department.id)
    slot_3 = models.TimeSlot(day="Tuesday", start_time=time(9, 0), end_time=time(10, 0), department_id=department.id)
    subject_a = models.Subject(name="Math", code="M201", department=department, semester=3, weekly_hours=1)
    subject_b = models.Subject(name="Physics", code="P201", department=department, semester=3, weekly_hours=1)

    tt_active = models.Timetable(section=section_a, semester=3, status="ACTIVE")
    tt_draft = models.Timetable(section=section_b, semester=3, status="DRAFT")

    db.add_all([year, section_a, section_b, slot_1, slot_2, slot_3, subject_a, subject_b, tt_active, tt_draft])
    db.flush()

    db.add_all([
        models.TimetableEntry(timetable=tt_active, subject=subject_a, timeslot=slot_1, is_locked=False),
        models.TimetableEntry(timetable=tt_active, subject=subject_b, timeslot=slot_2, is_locked=False),
        models.TimetableEntry(timetable=tt_draft, subject=subject_a, timeslot=slot_1, is_locked=False),
        models.TimetableEntry(timetable=tt_draft, subject=subject_b, timeslot=slot_2, is_locked=False),
    ])
    db.commit()
    db.refresh(tt_draft)

    assert _is_duplicate_section_timetable(tt_draft, db) is True

    repaired = _attempt_duplicate_repair(tt_draft, db, [slot_1, slot_2, slot_3])
    db.flush()

    assert repaired is True
    assert _is_duplicate_section_timetable(tt_draft, db) is False


def test_similarity_score_detects_same_slot_subject_pattern():
    db = make_session()

    department = models.Department(name="ECE", code="ECE")
    db.add(department)
    db.flush()

    year = models.AcademicYear(name="Year 1", level=1, department=department)
    section_a = models.Section(name="A", academic_year=year, section_name="A", year=1, independent_schedule=True)
    section_b = models.Section(name="B", academic_year=year, section_name="B", year=1, independent_schedule=True)
    slot = models.TimeSlot(day="Monday", start_time=time(9, 0), end_time=time(10, 0), department_id=department.id)
    subject = models.Subject(name="Basics", code="EC101", department=department, semester=1, weekly_hours=1)

    tt_active = models.Timetable(section=section_a, semester=1, status="ACTIVE")
    tt_draft = models.Timetable(section=section_b, semester=1, status="DRAFT")

    db.add_all([year, section_a, section_b, slot, subject, tt_active, tt_draft])
    db.flush()

    db.add(models.TimetableEntry(timetable=tt_active, subject=subject, timeslot=slot, is_locked=False))
    db.add(models.TimetableEntry(timetable=tt_draft, subject=subject, timeslot=slot, is_locked=False))
    db.commit()
    db.refresh(tt_draft)

    score = _section_similarity_score(tt_draft, db)
    assert score > 0


def test_backend_validation_bypasses_combined_locked_class_conflicts():
    db = make_session()

    department = models.Department(name="CSE", code="CSE")
    db.add(department)
    db.flush()

    year = models.AcademicYear(name="Year 3", level=3, department=department)
    section_a = models.Section(name="A1", academic_year=year, section_name="A1", year=3)
    section_b = models.Section(name="A2", academic_year=year, section_name="A2", year=3)
    
    faculty = models.Faculty(name="Ms. R. Abirami", faculty_id_code="FAC200")
    slot = models.TimeSlot(day="Monday", start_time=time(9, 0), end_time=time(10, 0), department_id=department.id)
    
    db.add_all([year, section_a, section_b, faculty, slot])
    db.flush()
    
    subject = models.Subject(
        name="5G Networks",
        code="SCSB4001",
        department=department,
        semester=5,
        weekly_hours=3,
        is_elective=True,
        manual_timeslot_ids=[slot.id]
    )

    tt_a = models.Timetable(section=section_a, semester=5, status="APPROVED")
    tt_b = models.Timetable(section=section_b, semester=5, status="DRAFT")

    db.add_all([subject, tt_a, tt_b])
    db.flush()

    db.add(models.TimetableEntry(timetable=tt_a, subject=subject, faculty=faculty, timeslot=slot, is_locked=True))
    db.add(models.TimetableEntry(timetable=tt_b, subject=subject, faculty=faculty, timeslot=slot, is_locked=True))
    db.commit()

    result = validate_timetable_internal(tt_b, db)
    assert result["errors"] == []
    assert result["status"] == "PASS"
