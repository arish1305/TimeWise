import pytest
from pathlib import Path
import sys

AI_ROOT = Path(__file__).resolve().parents[1]
if str(AI_ROOT) in sys.path:
    sys.path.remove(str(AI_ROOT))
sys.path.insert(0, str(AI_ROOT))

from scheduler_core.cp_sat_solver import CPSatSolver

def _build_base_timeslots():
    # 5 days, 4 slots per day
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    times = [
        ("09:00:00", "10:00:00"),
        ("10:00:00", "11:00:00"),
        ("11:00:00", "12:00:00"),
        ("12:00:00", "13:00:00")
    ]
    timeslots = []
    slot_id = 1
    for day in days:
        for t_start, t_end in times:
            timeslots.append({
                "id": slot_id,
                "day": day,
                "time": t_start,
                "end_time": t_end,
                "is_break": False
            })
            slot_id += 1
    return timeslots

def test_single_section_generation():
    timeslots = _build_base_timeslots()
    subjects = [
        {"id": 1, "name": "Maths", "weekly_hours": 3, "faculty_id": 10, "is_elective": False},
        {"id": 2, "name": "Physics", "weekly_hours": 3, "faculty_id": 11, "is_elective": False}
    ]
    faculty = [
        {"id": 10, "name": "Dr. Turing"},
        {"id": 11, "name": "Dr. Hopper"}
    ]
    constraints = {"random_seed": 42}
    
    solver = CPSatSolver(subjects, faculty, timeslots, constraints)
    schedule = solver.solve()
    assert len(schedule) == 6  # 3 + 3 = 6 scheduled hours

def test_faculty_assigned_no_clash():
    timeslots = _build_base_timeslots()
    # Faculty 10 is assigned to both subjects, total hours = 4
    subjects = [
        {"id": 1, "name": "Maths", "weekly_hours": 2, "faculty_id": 10, "is_elective": False},
        {"id": 2, "name": "Physics", "weekly_hours": 2, "faculty_id": 10, "is_elective": False}
    ]
    faculty = [{"id": 10, "name": "Dr. Turing"}]
    constraints = {"random_seed": 42}
    
    solver = CPSatSolver(subjects, faculty, timeslots, constraints)
    schedule = solver.solve()
    # Check that Faculty 10 is never scheduled in the same timeslot twice
    fac_slots = [e["timeslot_id"] for e in schedule if e["faculty_id"] == 10]
    assert len(fac_slots) == len(set(fac_slots))

def test_no_faculty_assigned_succeeds():
    timeslots = _build_base_timeslots()
    subjects = [
        {"id": 1, "name": "Self Study", "weekly_hours": 3, "faculty_id": None, "is_elective": False}
    ]
    faculty = []
    constraints = {"random_seed": 42}
    
    solver = CPSatSolver(subjects, faculty, timeslots, constraints)
    schedule = solver.solve()
    assert len(schedule) == 3
    for entry in schedule:
        assert entry["faculty_id"] is None

def test_cbcs_parallel_scheduling():
    timeslots = _build_base_timeslots()
    subjects = [
        {"id": 1, "name": "Elective A", "weekly_hours": 3, "faculty_id": 10, "is_elective": True, "elective_group_id": "E1"},
        {"id": 2, "name": "Elective B", "weekly_hours": 3, "faculty_id": 11, "is_elective": True, "elective_group_id": "E1"}
    ]
    faculty = [
        {"id": 10, "name": "Dr. Turing"},
        {"id": 11, "name": "Dr. Hopper"}
    ]
    constraints = {"random_seed": 42}
    
    solver = CPSatSolver(subjects, faculty, timeslots, constraints)
    schedule = solver.solve()
    
    slots_a = sorted([e["timeslot_id"] for e in schedule if e["subject_id"] == 1])
    slots_b = sorted([e["timeslot_id"] for e in schedule if e["subject_id"] == 2])
    assert slots_a == slots_b

def test_locked_slots_respected():
    timeslots = _build_base_timeslots()
    subjects = [
        {"id": 1, "name": "Maths", "weekly_hours": 3, "faculty_id": 10, "is_elective": False}
    ]
    faculty = [{"id": 10, "name": "Dr. Turing"}]
    locked_slots = [
        {"subject_id": 1, "timeslot_id": 5, "faculty_id": 10}
    ]
    constraints = {"random_seed": 42}
    
    solver = CPSatSolver(subjects, faculty, timeslots, constraints, locked_slots)
    schedule = solver.solve()
    
    dbms_in_slot_5 = False
    for entry in schedule:
        if entry["subject_id"] == 1 and entry["timeslot_id"] == 5:
            dbms_in_slot_5 = True
            break
    assert dbms_in_slot_5 is True

def test_labs_continuous_blocks():
    timeslots = _build_base_timeslots()
    subjects = [
        {"id": 1, "name": "Lab Chemistry", "weekly_hours": 2, "faculty_id": 10, "subject_type": "LAB", "continuous_hours": 2}
    ]
    faculty = [{"id": 10, "name": "Dr. Turing"}]
    constraints = {"random_seed": 42}
    
    solver = CPSatSolver(subjects, faculty, timeslots, constraints)
    schedule = solver.solve()
    
    lab_slots = sorted([e["timeslot_id"] for e in schedule if e["subject_id"] == 1])
    assert len(lab_slots) == 2
    s1, s2 = lab_slots[0], lab_slots[1]
    assert s2 == s1 + 1
    t1 = next(t for t in timeslots if t["id"] == s1)
    t2 = next(t for t in timeslots if t["id"] == s2)
    assert t1["day"] == t2["day"]


def test_lab_block_with_remainder_hour_is_filled():
    timeslots = _build_base_timeslots()
    subjects = [
        {"id": 1, "name": "Vision Lab", "weekly_hours": 3, "faculty_id": None, "subject_type": "LAB", "continuous_hours": 2}
    ]
    constraints = {"random_seed": 42}

    solver = CPSatSolver(subjects, [], timeslots, constraints)
    schedule = solver.solve()

    lab_slots = sorted([entry["timeslot_id"] for entry in schedule if entry["subject_id"] == 1])
    assert len(lab_slots) == 3

    slot_days = {slot["id"]: slot["day"] for slot in timeslots}
    has_block = any(
        later == earlier + 1 and slot_days[later] == slot_days[earlier]
        for earlier, later in zip(lab_slots, lab_slots[1:])
    )
    assert has_block


def test_weekly_hours_exact_fulfillment():
    timeslots = _build_base_timeslots()
    subjects = [
        {"id": 1, "name": "Maths", "weekly_hours": 4, "faculty_id": 10, "is_elective": False},
        {"id": 2, "name": "Physics", "weekly_hours": 3, "faculty_id": 11, "is_elective": False}
    ]
    faculty = [
        {"id": 10, "name": "Dr. Turing"},
        {"id": 11, "name": "Dr. Hopper"}
    ]
    constraints = {"random_seed": 42}
    
    solver = CPSatSolver(subjects, faculty, timeslots, constraints)
    schedule = solver.solve()
    
    maths_hours = len([e for e in schedule if e["subject_id"] == 1])
    physics_hours = len([e for e in schedule if e["subject_id"] == 2])
    assert maths_hours == 4
    assert physics_hours == 3

def test_partial_coverage_fills_available_slots_without_failing():
    timeslots = [
        {"id": 1, "day": "Monday", "time": "09:00:00", "end_time": "10:00:00", "is_break": False},
        {"id": 2, "day": "Monday", "time": "10:00:00", "end_time": "11:00:00", "is_break": False},
        {"id": 3, "day": "Tuesday", "time": "09:00:00", "end_time": "10:00:00", "is_break": False},
    ]
    subjects = [
        {"id": 1, "name": "DBMS", "weekly_hours": 3, "faculty_id": 10, "is_elective": False}
    ]
    faculty = [{"id": 10, "name": "Dr. Turing"}]
    constraints = {
        "random_seed": 42,
        "coverage_mode": "fill_remaining",
        "allow_partial_schedule": True,
        "prior_commitments": {10: [1, 2]},
    }

    solver = CPSatSolver(subjects, faculty, timeslots, constraints)
    schedule = solver.solve()

    assert len(schedule) == 1
    assert schedule[0]["timeslot_id"] == 3


def test_faculty_unavailable_slot_is_hard_constraint():
    timeslots = [
        {"id": 1, "day": "Monday", "time": "09:00:00", "end_time": "10:00:00", "is_break": False},
        {"id": 2, "day": "Monday", "time": "10:00:00", "end_time": "11:00:00", "is_break": False},
    ]
    subjects = [
        {"id": 1, "name": "DBMS", "weekly_hours": 1, "faculty_id": 10, "is_elective": False}
    ]
    faculty = [{"id": 10, "name": "Dr. Turing"}]
    constraints = {
        "random_seed": 42,
        "faculty_availability": {10: {"preferred_slots": [], "unavailable_slots": [1]}},
    }

    solver = CPSatSolver(subjects, faculty, timeslots, constraints)
    schedule = solver.solve()

    assert schedule == [{"subject_id": 1, "faculty_id": 10, "timeslot_id": 2}]


def test_approved_commitment_slot_is_hard_constraint():
    timeslots = [
        {"id": 1, "day": "Monday", "time": "09:00:00", "end_time": "10:00:00", "is_break": False},
        {"id": 2, "day": "Monday", "time": "10:00:00", "end_time": "11:00:00", "is_break": False},
    ]
    subjects = [
        {"id": 1, "name": "DBMS", "weekly_hours": 1, "faculty_id": 10, "is_elective": False}
    ]
    faculty = [{"id": 10, "name": "Dr. Turing"}]
    constraints = {
        "random_seed": 42,
        "approved_commitments": {10: [1]},
    }

    solver = CPSatSolver(subjects, faculty, timeslots, constraints)
    schedule = solver.solve()

    assert schedule == [{"subject_id": 1, "faculty_id": 10, "timeslot_id": 2}]


def test_faculty_preferred_slot_is_soft_bonus():
    timeslots = [
        {"id": 1, "day": "Monday", "time": "09:00:00", "end_time": "10:00:00", "is_break": False},
        {"id": 2, "day": "Tuesday", "time": "09:00:00", "end_time": "10:00:00", "is_break": False},
    ]
    subjects = [
        {"id": 1, "name": "DBMS", "weekly_hours": 1, "faculty_id": 10, "is_elective": False}
    ]
    faculty = [{"id": 10, "name": "Dr. Turing"}]
    constraints = {
        "random_seed": 42,
        "faculty_availability": {10: {"preferred_slots": [2], "unavailable_slots": []}},
    }

    solver = CPSatSolver(subjects, faculty, timeslots, constraints)
    schedule = solver.solve()

    assert schedule == [{"subject_id": 1, "faculty_id": 10, "timeslot_id": 2}]


def test_peer_timetable_constraint_avoids_duplicate_section_signature():
    timeslots = [
        {"id": 1, "day": "Monday", "time": "09:00:00", "end_time": "10:00:00", "is_break": False},
        {"id": 2, "day": "Tuesday", "time": "09:00:00", "end_time": "10:00:00", "is_break": False},
        {"id": 3, "day": "Wednesday", "time": "09:00:00", "end_time": "10:00:00", "is_break": False},
    ]
    subjects = [
        {"id": 1, "name": "Maths", "weekly_hours": 1, "faculty_id": None, "is_elective": False},
        {"id": 2, "name": "Physics", "weekly_hours": 1, "faculty_id": None, "is_elective": False},
    ]
    constraints = {
        "random_seed": 42,
        "coverage_mode": "fill_remaining",
        "allow_partial_schedule": True,
        "peer_timetables": [
            {
                "timetable_id": 100,
                "section_id": 1,
                "entries": [
                    {"subject_id": 1, "timeslot_id": 1, "day": "Monday", "time": "09:00:00"},
                    {"subject_id": 2, "timeslot_id": 2, "day": "Tuesday", "time": "09:00:00"},
                ],
            }
        ],
        "enforce_distinct_sections": True,
    }

    solver = CPSatSolver(subjects, [], timeslots, constraints)
    schedule = solver.solve()

    assert len(schedule) == 2
    peer_signature = {(1, 1), (2, 2)}
    generated_signature = {(entry["subject_id"], entry["timeslot_id"]) for entry in schedule}
    assert generated_signature != peer_signature


def test_partial_coverage_skips_impossible_continuous_block_subject():
    timeslots = [
        {"id": 1, "day": "Monday", "time": "09:00:00", "end_time": "10:00:00", "is_break": False},
        {"id": 2, "day": "Monday", "time": "10:00:00", "end_time": "11:00:00", "is_break": False},
        {"id": 3, "day": "Monday", "time": "11:00:00", "end_time": "11:15:00", "is_break": True},
        {"id": 4, "day": "Monday", "time": "11:15:00", "end_time": "12:15:00", "is_break": False},
        {"id": 5, "day": "Monday", "time": "12:15:00", "end_time": "13:15:00", "is_break": False},
    ]
    subjects = [
        {"id": 1, "name": "Project Work", "weekly_hours": 4, "continuous_hours": 4, "faculty_id": None, "is_elective": False},
        {"id": 2, "name": "Theory", "weekly_hours": 1, "continuous_hours": 1, "faculty_id": None, "is_elective": False},
    ]
    constraints = {
        "random_seed": 42,
        "coverage_mode": "fill_remaining",
        "allow_partial_schedule": True,
    }

    solver = CPSatSolver(subjects, [], timeslots, constraints)
    schedule = solver.solve()

    assert all(entry["subject_id"] != 1 for entry in schedule)
    assert any(entry["subject_id"] == 2 for entry in schedule)


def test_theory_subject_continuous_redefinition_5_hours():
    timeslots = _build_base_timeslots()
    subjects = [
        {"id": 1, "name": "Theory A", "weekly_hours": 5, "continuous_hours": 2, "subject_type": "THEORY", "faculty_id": None, "is_elective": False}
    ]
    constraints = {"random_seed": 42}
    
    solver = CPSatSolver(subjects, [], timeslots, constraints)
    schedule = solver.solve()
    
    assert len(schedule) == 5
    
    slots_map = {t["id"]: t for t in timeslots}
    day_counts = {}
    for entry in schedule:
        slot = slots_map[entry["timeslot_id"]]
        day = slot["day"]
        day_counts[day] = day_counts.get(day, 0) + 1
        
    counts = sorted(list(day_counts.values()))
    assert counts == [1, 1, 1, 2]


def test_theory_subject_continuous_redefinition_4_hours():
    timeslots = _build_base_timeslots()
    subjects = [
        {"id": 1, "name": "Theory B", "weekly_hours": 4, "continuous_hours": 2, "subject_type": "THEORY", "faculty_id": None, "is_elective": False}
    ]
    constraints = {"random_seed": 42}
    
    solver = CPSatSolver(subjects, [], timeslots, constraints)
    schedule = solver.solve()
    
    assert len(schedule) == 4
    
    slots_map = {t["id"]: t for t in timeslots}
    day_counts = {}
    for entry in schedule:
        slot = slots_map[entry["timeslot_id"]]
        day = slot["day"]
        day_counts[day] = day_counts.get(day, 0) + 1
        
    counts = sorted(list(day_counts.values()))
    assert counts == [1, 1, 2]


def test_lab_subject_continuous_redefinition_4_hours():
    timeslots = _build_base_timeslots()
    subjects = [
        {"id": 1, "name": "Lab Chem", "weekly_hours": 4, "continuous_hours": 2, "subject_type": "LAB", "faculty_id": None, "is_elective": False}
    ]
    constraints = {"random_seed": 42}
    
    solver = CPSatSolver(subjects, [], timeslots, constraints)
    schedule = solver.solve()
    
    assert len(schedule) == 4
    
    slots_map = {t["id"]: t for t in timeslots}
    day_counts = {}
    for entry in schedule:
        slot = slots_map[entry["timeslot_id"]]
        day = slot["day"]
        day_counts[day] = day_counts.get(day, 0) + 1
        
    counts = sorted(list(day_counts.values()))
    assert counts == [1, 1, 2]


def test_combined_cbcselect_locked_same_faculty_succeeds():
    timeslots = _build_base_timeslots()
    subjects = [
        {
            "id": 1,
            "name": "5G Networks",
            "weekly_hours": 3,
            "continuous_hours": 1,
            "faculty_id": 10,
            "is_elective": True,
            "is_cbcs": True,
            "manual_timeslot_ids": [5, 12, 19]
        }
    ]
    faculty = [{"id": 10, "name": "Ms. R. Abirami"}]
    locked_slots = [
        {"subject_id": 1, "timeslot_id": 5, "faculty_id": 10},
        {"subject_id": 1, "timeslot_id": 12, "faculty_id": 10},
        {"subject_id": 1, "timeslot_id": 19, "faculty_id": 10}
    ]
    constraints = {
        "random_seed": 42,
        "section_name": "A2",
        "prior_commitments": {10: [5, 12, 19]},
        "prior_commitment_entries": {
            10: [
                {"timeslot_id": 5, "subject_id": 1, "section_name": "A1"},
                {"timeslot_id": 12, "subject_id": 1, "section_name": "A1"},
                {"timeslot_id": 19, "subject_id": 1, "section_name": "A1"}
            ]
        }
    }
    solver = CPSatSolver(subjects, faculty, timeslots, constraints, locked_slots)
    schedule = solver.solve()
    assert len(schedule) == 3
    scheduled_slots = {e["timeslot_id"] for e in schedule}
    assert scheduled_slots == {5, 12, 19}


def test_combined_cbcselect_unlocked_conflict_enforced():
    timeslots = _build_base_timeslots()
    subjects = [
        {
            "id": 1,
            "name": "5G Networks",
            "weekly_hours": 3,
            "continuous_hours": 1,
            "faculty_id": 10,
            "is_elective": True,
            "is_cbcs": True,
            "manual_timeslot_ids": []
        }
    ]
    faculty = [{"id": 10, "name": "Ms. R. Abirami"}]
    locked_slots = [
        {"subject_id": 1, "timeslot_id": 5, "faculty_id": 10},
        {"subject_id": 1, "timeslot_id": 12, "faculty_id": 10},
        {"subject_id": 1, "timeslot_id": 19, "faculty_id": 10}
    ]
    constraints = {
        "random_seed": 42,
        "section_name": "A2",
        "prior_commitments": {10: [5, 12, 19]},
        "prior_commitment_entries": {
            10: [
                {"timeslot_id": 5, "subject_id": 1, "section_name": "A1"},
                {"timeslot_id": 12, "subject_id": 1, "section_name": "A1"},
                {"timeslot_id": 19, "subject_id": 1, "section_name": "A1"}
            ]
        }
    }
    with pytest.raises(ValueError):
        solver = CPSatSolver(subjects, faculty, timeslots, constraints, locked_slots)
        solver.solve()


def test_normal_subject_locked_conflict_enforced():
    timeslots = _build_base_timeslots()
    subjects = [
        {
            "id": 1,
            "name": "5G Networks",
            "weekly_hours": 3,
            "continuous_hours": 1,
            "faculty_id": 10,
            "is_elective": False,
            "is_cbcs": False,
            "manual_timeslot_ids": [5, 12, 19]
        }
    ]
    faculty = [{"id": 10, "name": "Ms. R. Abirami"}]
    locked_slots = [
        {"subject_id": 1, "timeslot_id": 5, "faculty_id": 10},
        {"subject_id": 1, "timeslot_id": 12, "faculty_id": 10},
        {"subject_id": 1, "timeslot_id": 19, "faculty_id": 10}
    ]
    constraints = {
        "random_seed": 42,
        "section_name": "A2",
        "prior_commitments": {10: [5, 12, 19]},
        "prior_commitment_entries": {
            10: [
                {"timeslot_id": 5, "subject_id": 1, "section_name": "A1"},
                {"timeslot_id": 12, "subject_id": 1, "section_name": "A1"},
                {"timeslot_id": 19, "subject_id": 1, "section_name": "A1"}
            ]
        }
    }
    with pytest.raises(ValueError):
        solver = CPSatSolver(subjects, faculty, timeslots, constraints, locked_slots)
        solver.solve()


def test_combined_cbcselect_locked_different_subjects_conflict_enforced():
    timeslots = _build_base_timeslots()
    subjects = [
        {
            "id": 1,
            "name": "5G Networks",
            "weekly_hours": 3,
            "continuous_hours": 1,
            "faculty_id": 10,
            "is_elective": True,
            "is_cbcs": True,
            "manual_timeslot_ids": [5, 12, 19]
        }
    ]
    faculty = [{"id": 10, "name": "Ms. R. Abirami"}]
    locked_slots = [
        {"subject_id": 1, "timeslot_id": 5, "faculty_id": 10},
        {"subject_id": 1, "timeslot_id": 12, "faculty_id": 10},
        {"subject_id": 1, "timeslot_id": 19, "faculty_id": 10}
    ]
    constraints = {
        "random_seed": 42,
        "section_name": "A2",
        "prior_commitments": {10: [5, 12, 19]},
        "prior_commitment_entries": {
            10: [
                {"timeslot_id": 5, "subject_id": 999, "section_name": "A1"},
                {"timeslot_id": 12, "subject_id": 999, "section_name": "A1"},
                {"timeslot_id": 19, "subject_id": 999, "section_name": "A1"}
            ]
        }
    }
    with pytest.raises(ValueError):
        solver = CPSatSolver(subjects, faculty, timeslots, constraints, locked_slots)
        solver.solve()


def test_combined_cbcselect_locked_different_timeslot_conflict_enforced():
    timeslots = _build_base_timeslots()
    subjects = [
        {
            "id": 1,
            "name": "5G Networks",
            "weekly_hours": 3,
            "continuous_hours": 1,
            "faculty_id": 10,
            "is_elective": True,
            "is_cbcs": True,
            "manual_timeslot_ids": [5, 12, 19]
        }
    ]
    faculty = [{"id": 10, "name": "Ms. R. Abirami"}]
    locked_slots = [
        {"subject_id": 1, "timeslot_id": 6, "faculty_id": 10},
        {"subject_id": 1, "timeslot_id": 13, "faculty_id": 10},
        {"subject_id": 1, "timeslot_id": 20, "faculty_id": 10}
    ]
    constraints = {
        "random_seed": 42,
        "section_name": "A2",
        "prior_commitments": {10: [5, 12, 19]},
        "prior_commitment_entries": {
            10: [
                {"timeslot_id": 5, "subject_id": 1, "section_name": "A1"},
                {"timeslot_id": 12, "subject_id": 1, "section_name": "A1"},
                {"timeslot_id": 19, "subject_id": 1, "section_name": "A1"}
            ]
        }
    }
    with pytest.raises(ValueError):
        solver = CPSatSolver(subjects, faculty, timeslots, constraints, locked_slots)
        solver.solve()


def test_combined_cbcselect_locked_same_section_conflict_enforced():
    from common.combined_class import is_shared_combined_class
    subject = {
        "id": 1,
        "is_elective": True,
        "is_cbcs": True,
        "manual_timeslot_ids": [5, 12, 19]
    }
    res = is_shared_combined_class(
        subject=subject,
        conflict_subject=subject,
        slot_id=5,
        faculty_id=10,
        conflict_faculty_id=10,
        conflict_slot_id=5,
        is_different_section=False
    )
    assert res is False


def test_combined_cbcselect_locked_different_locked_slots_conflict_enforced():
    from common.combined_class import is_shared_combined_class
    subject_a = {
        "id": 1,
        "is_elective": True,
        "is_cbcs": True,
        "manual_timeslot_ids": [5, 12, 19]
    }
    subject_b = {
        "id": 1,
        "is_elective": True,
        "is_cbcs": True,
        "manual_timeslot_ids": [5, 12, 26]
    }
    res = is_shared_combined_class(
        subject=subject_a,
        conflict_subject=subject_b,
        slot_id=5,
        faculty_id=10,
        conflict_faculty_id=10,
        conflict_slot_id=5,
        is_different_section=True
    )
    assert res is False


