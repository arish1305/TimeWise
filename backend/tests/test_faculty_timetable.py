from datetime import time

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from routers.timetable import (
    COMMITMENT_STATUSES,
    _build_faculty_timetable_payload,
    _solve_timetable_locally,
    validate_timetable_internal,
)


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
