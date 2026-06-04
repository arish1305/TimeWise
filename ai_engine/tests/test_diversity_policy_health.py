import pytest
import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
if str(AI_ROOT) in sys.path:
    sys.path.remove(str(AI_ROOT))
sys.path.insert(0, str(AI_ROOT))

from scheduler_core.cp_sat_solver import CPSatSolver
from scheduler_core import candidate_diversity
from scheduler_core import health_metrics
from scheduler_core import explainability

def _build_simple_test_data():
    subjects = [
        {"id": 1, "name": "DBMS", "weekly_hours": 3, "credits": 3, "faculty_id": 10, "subject_type": "THEORY"},
        {"id": 2, "name": "OS", "weekly_hours": 3, "credits": 3, "faculty_id": 11, "subject_type": "THEORY"},
        {"id": 3, "name": "LAB_CS", "weekly_hours": 2, "credits": 2, "faculty_id": 10, "subject_type": "LAB", "continuous_hours": 2}
    ]
    faculty = [
        {"id": 10, "name": "Dr. Alan Turing"},
        {"id": 11, "name": "Dr. Grace Hopper"}
    ]
    # 2 days, 4 slots per day
    days = ["Monday", "Tuesday"]
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
                "end_time": t_end
            })
            slot_id += 1
            
    return subjects, faculty, timeslots

def test_cp_sat_solver_simple():
    subjects, faculty, timeslots = _build_simple_test_data()
    constraints = {
        "random_seed": 42,
        "candidate_limit": 3,
        "time_budget_seconds": 5.0
    }
    
    solver = CPSatSolver(subjects, faculty, timeslots, constraints)
    schedule = solver.solve()
    
    assert isinstance(schedule, list)
    assert len(schedule) > 0
    for entry in schedule:
        assert "subject_id" in entry
        assert "faculty_id" in entry
        assert "timeslot_id" in entry

def test_cp_sat_solver_locked_slots():
    subjects, faculty, timeslots = _build_simple_test_data()
    # Lock DBMS (id 1) at slot 2
    locked_slots = [
        {"subject_id": 1, "timeslot_id": 2, "faculty_id": 10}
    ]
    constraints = {
        "random_seed": 42
    }
    
    solver = CPSatSolver(subjects, faculty, timeslots, constraints, locked_slots)
    schedule = solver.solve()
    
    # Verify that DBMS is scheduled in slot 2
    dbms_in_slot_2 = False
    for entry in schedule:
        if entry["subject_id"] == 1 and entry["timeslot_id"] == 2:
            dbms_in_slot_2 = True
            break
    assert dbms_in_slot_2 is True

def test_cp_sat_solver_continuous_labs():
    subjects, faculty, timeslots = _build_simple_test_data()
    # Subject 3 is LAB_CS with 2 continuous hours
    constraints = {
        "random_seed": 42
    }
    
    solver = CPSatSolver(subjects, faculty, timeslots, constraints)
    schedule = solver.solve()
    
    # Find all slots assigned to LAB_CS
    lab_slots = sorted([e["timeslot_id"] for e in schedule if e["subject_id"] == 3])
    assert len(lab_slots) == 2
    # Verify that they are consecutive (e.g. 1 and 2, or 2 and 3, or 5 and 6, etc.)
    # Note: they must also be on the same day. Mon has slots 1, 2, 3, 4. Tue has slots 5, 6, 7, 8.
    s1, s2 = lab_slots[0], lab_slots[1]
    assert s2 == s1 + 1
    # Check that they belong to the same day
    t1 = next(t for t in timeslots if t["id"] == s1)
    t2 = next(t for t in timeslots if t["id"] == s2)
    assert t1["day"] == t2["day"]

def test_cp_sat_solver_relaxed_coverage_fallback_with_blocked_faculty():
    subjects = [
        {"id": 1, "name": "DBMS", "weekly_hours": 3, "credits": 3, "faculty_id": 10, "subject_type": "THEORY"}
    ]
    faculty = [{"id": 10, "name": "Dr. Alan Turing"}]
    timeslots = [
        {"id": 1, "day": "Monday", "time": "09:00:00", "end_time": "10:00:00"},
        {"id": 2, "day": "Monday", "time": "10:00:00", "end_time": "11:00:00"},
        {"id": 3, "day": "Tuesday", "time": "09:00:00", "end_time": "10:00:00"},
    ]
    constraints = {
        "random_seed": 7,
        # Faculty 10 is already committed in two of three slots, so strict
        # exact-hour matching is infeasible for 3 credits.
        "prior_commitments": {10: [1, 2]},
    }

    with pytest.raises(ValueError) as excinfo:
        CPSatSolver(subjects, faculty, timeslots, constraints)
    assert "Faculty Overload" in str(excinfo.value)

def test_candidate_diversity():
    # Verify candidate diversity function behaves correctly
    timeslots = [
        {"id": 1, "day": "Monday", "time": "09:00:00", "end_time": "10:00:00"},
        {"id": 2, "day": "Monday", "time": "10:00:00", "end_time": "11:00:00"},
        {"id": 3, "day": "Tuesday", "time": "09:00:00", "end_time": "10:00:00"},
    ]
    sched1 = [
        {"subject_id": 1, "timeslot_id": 1, "faculty_id": 10}
    ]
    sched2 = [
        {"subject_id": 1, "timeslot_id": 3, "faculty_id": 10}
    ]
    assert candidate_diversity.is_diverse_enough(sched2, [sched1], timeslots, threshold=80.0) is True

def test_health_metrics():
    subjects, faculty, timeslots = _build_simple_test_data()
    schedule = [
        {"subject_id": 1, "timeslot_id": 1, "faculty_id": 10},
        {"subject_id": 2, "timeslot_id": 2, "faculty_id": 11}
    ]
    metrics = health_metrics.calculate_health_metrics(schedule, subjects, timeslots, {})
    assert "health_score" in metrics
    assert "faculty_utilization" in metrics

def test_explainability():
    subscores = {
        "spread": 90.0,
        "faculty": 85.0,
        "student": 80.0,
        "uniqueness": 95.0
    }
    health = {"health_score": 88.0}
    reason = explainability.generate_selection_reason(88.0, subscores, health)
    assert "Selected candidate" in reason

def test_cp_sat_solver_locked_slot_on_break():
    subjects, faculty, timeslots = _build_simple_test_data()
    # Mark slot 2 as break
    for t in timeslots:
        if t["id"] == 2:
            t["is_break"] = True
    
    locked_slots = [
        {"subject_id": 1, "timeslot_id": 2, "faculty_id": 10}
    ]
    constraints = {}
    
    with pytest.raises(ValueError) as excinfo:
        CPSatSolver(subjects, faculty, timeslots, constraints, locked_slots)
    assert "Cannot schedule subject" in str(excinfo.value)

def test_cp_sat_solver_capacity_exceeded():
    subjects, faculty, timeslots = _build_simple_test_data()
    # DBMS needs 10 hours
    for s in subjects:
        if s["id"] == 1:
            s["weekly_hours"] = 10
            
    constraints = {}
    with pytest.raises(ValueError) as excinfo:
        CPSatSolver(subjects, faculty, timeslots, constraints)
    assert "Insufficient timeslots" in str(excinfo.value)

def test_cp_sat_solver_faculty_overload():
    subjects, faculty, timeslots = _build_simple_test_data()
    # Set Grace Hopper (11) max hours to 1
    constraints = {
        "faculty_preferences": {
            "11": {"max_hours": 1}
        }
    }
    # Subject 2 is taught by Grace Hopper (11), needs 3 credits
    with pytest.raises(ValueError) as excinfo:
        CPSatSolver(subjects, faculty, timeslots, constraints)
    assert "Faculty Overload" in str(excinfo.value)

def test_cp_sat_solver_infeasibility_diagnostics():
    subjects, faculty, timeslots = _build_simple_test_data()
    # Lock Subject 1 in slot 1 AND Subject 2 in slot 1
    locked_slots = [
        {"subject_id": 1, "timeslot_id": 1, "faculty_id": 10},
        {"subject_id": 2, "timeslot_id": 1, "faculty_id": 11}
    ]
    constraints = {}
    
    # Instantiate solver (succeeds capacity checks because hours fit)
    solver = CPSatSolver(subjects, faculty, timeslots, constraints, locked_slots)
    # Solving will fail and raise ValueError with diagnostics
    with pytest.raises(ValueError) as excinfo:
        solver.solve()
    assert "Unsatisfiable Core Constraints" in str(excinfo.value)
    # The diagnostics core should report section non-overlap or locked slot clash
    assert "Section Non-Overlap" in str(excinfo.value)
