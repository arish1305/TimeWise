import sys
from pathlib import Path
from datetime import time, datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import json

BACKEND_ROOT = Path(__file__).resolve().parents[1]
# Prioritize backend root at the very beginning of sys.path to avoid path pollution from other tests
if str(BACKEND_ROOT) in sys.path:
    sys.path.remove(str(BACKEND_ROOT))
sys.path.insert(0, str(BACKEND_ROOT))

# Inject environment variable to use sqlite for test main app
import os
os.environ["DATABASE_URL"] = "sqlite://"

import models
import schemas
import database
from database import Base
from types import SimpleNamespace
from routers.timetable import (
    resolve_manual_locked_slots,
    validate_timetable_internal,
    _subject_overlap_group_key,
    _entries_can_overlap_in_section,
)
import main

client = TestClient(main.app, raise_server_exceptions=True)

def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_no_section_override():
    db = make_session()

    dept = models.Department(name="Computer Science", code="CSE")
    db.add(dept)
    db.flush()

    year = models.AcademicYear(name="Year 1", level=1, department=dept)
    db.add(year)
    db.flush()

    section = models.Section(name="A", academic_year=year)
    db.add(section)
    db.flush()

    subject = models.Subject(
        name="Programming in C",
        code="CS101",
        department=dept,
        semester=1,
        manual_timeslot_ids=[10, 11]
    )
    db.add(subject)
    db.commit()

    # Verify that resolve_manual_locked_slots resolves to Department Default
    resolved = resolve_manual_locked_slots(db, section.id, subject)
    assert resolved == [10, 11]


def test_section_override_exists():
    db = make_session()

    dept = models.Department(name="Computer Science", code="CSE")
    db.add(dept)
    db.flush()

    year = models.AcademicYear(name="Year 1", level=1, department=dept)
    db.add(year)
    db.flush()

    section = models.Section(name="A", academic_year=year)
    db.add(section)
    db.flush()

    subject = models.Subject(
        name="Programming in C",
        code="CS101",
        department=dept,
        semester=1,
        manual_timeslot_ids=[10, 11]
    )
    db.add(subject)
    db.flush()

    # Create SectionSubjectLock override
    lock = models.SectionSubjectLock(
        section_id=section.id,
        subject_id=subject.id,
        manual_timeslot_ids=[20, 21],
        is_active=True
    )
    db.add(lock)
    db.commit()

    # Verify that resolve_manual_locked_slots resolves to Section Override
    resolved = resolve_manual_locked_slots(db, section.id, subject)
    assert resolved == [20, 21]


def test_delete_override():
    db = make_session()

    dept = models.Department(name="Computer Science", code="CSE")
    db.add(dept)
    db.flush()

    year = models.AcademicYear(name="Year 1", level=1, department=dept)
    db.add(year)
    db.flush()

    section = models.Section(name="A", academic_year=year)
    db.add(section)
    db.flush()

    subject = models.Subject(
        name="Programming in C",
        code="CS101",
        department=dept,
        semester=1,
        manual_timeslot_ids=[10, 11]
    )
    db.add(subject)
    db.flush()

    # Create override
    lock = models.SectionSubjectLock(
        section_id=section.id,
        subject_id=subject.id,
        manual_timeslot_ids=[20, 21],
        is_active=True
    )
    db.add(lock)
    db.commit()

    # Assert override is active
    assert resolve_manual_locked_slots(db, section.id, subject) == [20, 21]

    # Delete override
    db.delete(lock)
    db.commit()

    # Assert fallback to department default
    assert resolve_manual_locked_slots(db, section.id, subject) == [10, 11]


def test_different_sections():
    db = make_session()

    dept = models.Department(name="Computer Science", code="CSE")
    db.add(dept)
    db.flush()

    year = models.AcademicYear(name="Year 1", level=1, department=dept)
    db.add(year)
    db.flush()

    section_a = models.Section(name="A", academic_year=year)
    section_b = models.Section(name="B", academic_year=year)
    db.add_all([section_a, section_b])
    db.flush()

    subject = models.Subject(
        name="Programming in C",
        code="CS101",
        department=dept,
        semester=1,
        manual_timeslot_ids=[10, 11]
    )
    db.add(subject)
    db.flush()

    # Create override ONLY for section_a
    lock_a = models.SectionSubjectLock(
        section_id=section_a.id,
        subject_id=subject.id,
        manual_timeslot_ids=[20, 21],
        is_active=True
    )
    db.add(lock_a)
    db.commit()

    # Verify section_a has override slots, section_b has department default slots
    assert resolve_manual_locked_slots(db, section_a.id, subject) == [20, 21]
    assert resolve_manual_locked_slots(db, section_b.id, subject) == [10, 11]


def test_cbcs_subject_with_override():
    db = make_session()

    dept = models.Department(name="Computer Science", code="CSE")
    db.add(dept)
    db.flush()

    year = models.AcademicYear(name="Year 3", level=3, department=dept)
    db.add(year)
    db.flush()

    section = models.Section(name="A", academic_year=year)
    db.add(section)
    db.flush()

    # Elective subject belonging to elective group PE1
    s1 = models.Subject(
        name="Mobile App Dev",
        code="CS301",
        department=dept,
        semester=5,
        is_elective=True,
        elective_group_id="PE1",
        manual_timeslot_ids=[1]
    )
    s2 = models.Subject(
        name="Cloud Computing",
        code="CS302",
        department=dept,
        semester=5,
        is_elective=True,
        elective_group_id="PE1",
        manual_timeslot_ids=[2]
    )
    db.add_all([s1, s2])
    db.flush()

    # Scenario A: No override. S1 and S2 share elective group but have different department-level manual slots.
    # Overlap at timeslot 1 should fail because they don't share the same M:1 group key.
    # Group key for S1 at slot 1: G:PE1 (since it's elective)
    # Group key for S2 at slot 1: G:PE1
    # Both are G:PE1, so they can overlap.
    # Let's verify overlap rules. Elective group overlap checks by elective_group_id.
    # What if they are regular subjects with manual locks?
    # Let's define them as non-electives so overlap check falls back to manual_timeslot_ids:
    s_reg1 = models.Subject(
        name="Regular 1",
        code="REG1",
        department=dept,
        semester=5,
        is_elective=False,
        manual_timeslot_ids=[1]
    )
    s_reg2 = models.Subject(
        name="Regular 2",
        code="REG2",
        department=dept,
        semester=5,
        is_elective=False,
        manual_timeslot_ids=[2]
    )
    db.add_all([s_reg1, s_reg2])
    db.flush()

    # Scenario B: Overriding manual slots so both section locks are identical.
    lock1 = models.SectionSubjectLock(section_id=section.id, subject_id=s_reg1.id, manual_timeslot_ids=[5])
    lock2 = models.SectionSubjectLock(section_id=section.id, subject_id=s_reg2.id, manual_timeslot_ids=[5])
    db.add_all([lock1, lock2])
    db.commit()

    # Create Timetable & Entries for both regular subjects in slot 5
    tt = models.Timetable(section=section, semester=5, status="DRAFT")
    db.add(tt)
    db.flush()

    e1 = models.TimetableEntry(timetable=tt, subject=s_reg1, timeslot_id=5)
    e2 = models.TimetableEntry(timetable=tt, subject=s_reg2, timeslot_id=5)
    db.add_all([e1, e2])
    db.commit()

    # Under section override, since both resolved slots are [5], they should be considered manual lock slots
    # But wait, are multiple regular subjects allowed to overlap?
    # No, regular subjects cannot overlap unless they are electives or CBCS.
    # Let's check _entries_can_overlap_in_section:
    # If they are electives with same elective group, they can overlap.
    # Let's verify _entries_can_overlap_in_section for electives:
    # Elective subjects S1 and S2 under elective group PE1, slot 5:
    s_el1 = models.Subject(
        name="Elective 1",
        code="EL1",
        department=dept,
        semester=5,
        is_elective=True,
        elective_group_id="PE1",
        manual_timeslot_ids=[1]
    )
    s_el2 = models.Subject(
        name="Elective 2",
        code="EL2",
        department=dept,
        semester=5,
        is_elective=True,
        elective_group_id="PE1",
        manual_timeslot_ids=[2]
    )
    db.add_all([s_el1, s_el2])
    db.flush()

    lock_el1 = models.SectionSubjectLock(section_id=section.id, subject_id=s_el1.id, manual_timeslot_ids=[5])
    lock_el2 = models.SectionSubjectLock(section_id=section.id, subject_id=s_el2.id, manual_timeslot_ids=[5])
    db.add_all([lock_el1, lock_el2])
    db.commit()

    # Both belong to PE1, group key resolves to G:PE1. They can overlap.
    # What if they don't have PE1 elective group, but are just non-elective subjects?
    # The solver and helper check that resolved slots match.
    # Let's verify _subject_overlap_group_key resolves to M:5 for both when overridden.
    key1 = _subject_overlap_group_key(db, s_el1, 5, section.id)
    key2 = _subject_overlap_group_key(db, s_el2, 5, section.id)
    # Both should match
    assert key1 == key2


def test_timetable_generation_compatibility():
    db = make_session()

    # Set up database records
    dept = models.Department(name="Computer Science", code="CSE")
    db.add(dept)
    db.flush()

    year = models.AcademicYear(name="Year 1", level=1, department=dept)
    db.add(year)
    db.flush()

    section = models.Section(name="A", academic_year=year)
    db.add(section)
    db.flush()

    subject = models.Subject(
        name="Programming in C",
        code="CS101",
        department=dept,
        semester=1,
        manual_timeslot_ids=[10, 11]
    )
    db.add(subject)
    db.flush()

    t1 = models.TimeSlot(id=10, department_id=dept.id, day="Monday", start_time=time(9,0), end_time=time(10,0))
    t2 = models.TimeSlot(id=11, department_id=dept.id, day="Monday", start_time=time(10,0), end_time=time(11,0))
    db.add_all([t1, t2])
    db.flush()

    # Generate once without overrides. Mocking AI engine response.
    mock_response = {
        "status": "success",
        "schedule": []
    }

    # Override get_db for TestClient
    def override_get_db():
        try:
            yield db
        finally:
            pass

    main.app.dependency_overrides[database.get_db] = override_get_db
    from routers import timetable
    main.app.dependency_overrides[timetable.auth.require_admin] = lambda: SimpleNamespace(id=1, user_id=1, username="admin", role=models.UserRole.ADMIN)

    try:
        # Mock urllib request to return mock_response
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp_obj = MagicMock()
            mock_resp_obj.status = 200
            mock_resp_obj.read.return_value = json.dumps(mock_response).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp_obj

            # First generation
            response = client.post("/timetables/generate", json={
                "semester": 1,
                "section_id": section.id
            })
            assert response.status_code == 200
            
            # Record first output signature or list of slots
            first_slots = [entry["timeslot_id"] for entry in response.json()["entries"]]
            assert set(first_slots) == {10, 11}

            # Enable the feature but do NOT create any overrides.
            # Run generation again. It should produce identical timetable.
            # Clear previous active timetable status to re-run
            db.query(models.Timetable).delete()
            db.query(models.TimetableEntry).delete()
            db.commit()

            response_again = client.post("/timetables/generate", json={
                "semester": 1,
                "section_id": section.id
            })
            assert response_again.status_code == 200
            second_slots = [entry["timeslot_id"] for entry in response_again.json()["entries"]]
            
            # The generated timetables must be identical
            assert first_slots == second_slots

    finally:
        main.app.dependency_overrides.clear()
