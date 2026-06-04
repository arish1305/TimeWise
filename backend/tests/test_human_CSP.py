from datetime import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from human_score_engine import score_timetable
from repair_engine import repair_timetable

def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()

def test_human_scoring_subject_spread_and_clustering():
    db = make_session()

    department = models.Department(name="Computer Science", code="CSE")
    year = models.AcademicYear(name="Year 2", level=2, department=department)
    section = models.Section(name="A", academic_year=year)
    
    # We create a subject with credits = 3
    subject = models.Subject(
        name="Data Structures",
        code="CS201",
        department=department,
        semester=3,
        weekly_hours=3,
        continuous_hours=1
    )
    
    # Setup slots (non-consecutive on the same day to simulate clustering)
    slot_mon1 = models.TimeSlot(day="Monday", start_time=time(9, 0), end_time=time(10, 0))
    slot_mon2 = models.TimeSlot(day="Monday", start_time=time(13, 0), end_time=time(14, 0))
    
    timetable = models.Timetable(section=section, semester=3, status="DRAFT")
    
    db.add_all([department, year, section, subject, slot_mon1, slot_mon2, timetable])
    db.flush()
    
    db.add_all([
        models.TimetableEntry(timetable=timetable, subject=subject, timeslot=slot_mon1),
        models.TimetableEntry(timetable=timetable, subject=subject, timeslot=slot_mon2),
    ])
    db.commit()

    score_res = score_timetable(timetable, db)
    
    # Check that clustering penalty is applied
    assert score_res["subscores"]["subject_spread"] < 25.0
    assert any("clustered sessions" in issue for issue in score_res["issues"])

def test_human_scoring_faculty_overload():
    db = make_session()

    department = models.Department(name="Computer Science", code="CSE")
    year = models.AcademicYear(name="Year 2", level=2, department=department)
    section = models.Section(name="A", academic_year=year)
    faculty = models.Faculty(name="Dr. Smith", faculty_id_code="FAC001", min_hours_per_week=5, max_hours_per_week=18)
    
    subject = models.Subject(name="Java Programming", code="CS202", department=department, semester=3)
    
    # Setup 5 slots on Monday
    slots = [
        models.TimeSlot(day="Monday", start_time=time(9 + i, 0), end_time=time(10 + i, 0))
        for i in range(5)
    ]
    
    timetable = models.Timetable(section=section, semester=3, status="DRAFT")
    
    db.add_all([department, year, section, faculty, subject, timetable] + slots)
    db.flush()
    
    for slot in slots:
        db.add(models.TimetableEntry(timetable=timetable, subject=subject, faculty=faculty, timeslot=slot))
    db.commit()

    score_res = score_timetable(timetable, db)
    
    # Check that faculty overload penalty was applied
    assert score_res["subscores"]["faculty_comfort"] < 20.0
    assert any("overloaded" in issue for issue in score_res["issues"])

def test_human_scoring_heavy_subjects_student_comfort():
    db = make_session()

    department = models.Department(name="Computer Science", code="CSE")
    year = models.AcademicYear(name="Year 2", level=2, department=department)
    section = models.Section(name="A", academic_year=year)
    
    # Heavy subjects: AI and Blockchain and Cryptography
    sub_ai = models.Subject(name="Artificial Intelligence", code="CS301", department=department, semester=5)
    sub_bc = models.Subject(name="Blockchain Technology", code="CS302", department=department, semester=5)
    sub_crypto = models.Subject(name="Cryptography", code="CS303", department=department, semester=5)
    
    slot1 = models.TimeSlot(day="Monday", start_time=time(9, 0), end_time=time(10, 0))
    slot2 = models.TimeSlot(day="Monday", start_time=time(10, 0), end_time=time(11, 0))
    slot3 = models.TimeSlot(day="Monday", start_time=time(12, 0), end_time=time(13, 0))
    
    timetable = models.Timetable(section=section, semester=5, status="DRAFT")
    
    db.add_all([department, year, section, sub_ai, sub_bc, sub_crypto, slot1, slot2, slot3, timetable])
    db.flush()
    
    db.add_all([
        models.TimetableEntry(timetable=timetable, subject=sub_ai, timeslot=slot1),
        models.TimetableEntry(timetable=timetable, subject=sub_bc, timeslot=slot2),
        models.TimetableEntry(timetable=timetable, subject=sub_crypto, timeslot=slot3),
    ])
    db.commit()

    score_res = score_timetable(timetable, db)
    
    # Check that heavy subjects clustering penalty was applied
    assert score_res["subscores"]["student_comfort"] < 20.0
    assert any("heavy courses" in issue for issue in score_res["issues"])

def test_repair_engine_improves_score_without_clashing():
    db = make_session()

    department = models.Department(name="Computer Science", code="CSE")
    db.add(department)
    db.flush()

    year = models.AcademicYear(name="Year 2", level=2, department=department)
    section = models.Section(name="A", academic_year=year)
    
    # Subject CS201 has 3 credits (weekly_hours = 2 for this test)
    subject = models.Subject(name="DBMS", code="CS203", department=department, semester=3, weekly_hours=2, continuous_hours=1)
    
    # 2 slots on Monday, 1 slot on Wednesday
    slot_mon1 = models.TimeSlot(day="Monday", start_time=time(9, 0), end_time=time(10, 0), department_id=department.id)
    slot_mon2 = models.TimeSlot(day="Monday", start_time=time(13, 0), end_time=time(14, 0), department_id=department.id)
    slot_wed = models.TimeSlot(day="Wednesday", start_time=time(9, 0), end_time=time(10, 0), department_id=department.id)
    
    timetable = models.Timetable(section=section, semester=3, status="DRAFT")
    
    db.add_all([year, section, subject, slot_mon1, slot_mon2, slot_wed, timetable])
    db.flush()
    
    # We place both DB entries on Mon1 and Mon2 (which is clustered, bad spread score)
    db.add_all([
        models.TimetableEntry(timetable=timetable, subject=subject, timeslot=slot_mon1, is_locked=False),
        models.TimetableEntry(timetable=timetable, subject=subject, timeslot=slot_mon2, is_locked=False),
    ])
    db.commit()

    initial_score = score_timetable(timetable, db)["total_score"]
    
    # Run repair engine to move one of them to Wednesday (improving spread score)
    repair_res = repair_timetable(timetable, db, threshold=95.0, max_iterations=5)
    
    final_score = score_timetable(timetable, db)["total_score"]
    
    assert final_score > initial_score
    assert repair_res["final_score"] > repair_res["initial_score"]
