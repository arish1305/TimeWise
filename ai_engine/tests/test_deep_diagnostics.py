import copy
import logging

import scheduler_core.cp_sat_solver as cp_sat_solver_module
from scheduler_core.deep_diagnostics import DeepDiagnosticAnalyzer


def _timeslots():
    return [
        {"id": 1, "day": "Monday", "time": "09:00:00", "is_break": False},
        {"id": 2, "day": "Monday", "time": "10:00:00", "is_break": True},
        {"id": 3, "day": "Tuesday", "time": "09:00:00", "is_break": False},
        {"id": 4, "day": "Tuesday", "time": "10:00:00", "is_break": False},
    ]


def test_deep_diagnostics_is_read_only_and_traces_constraint_elimination():
    subjects = [
        {
            "id": 1,
            "name": "Programming in Java",
            "weekly_hours": 2,
            "continuous_hours": 1,
            "faculty_ids": [10, 11],
        },
        {
            "id": 2,
            "name": "Locked Subject",
            "weekly_hours": 1,
            "continuous_hours": 1,
            "faculty_id": 12,
        },
    ]
    faculty = [
        {"id": 10, "name": "Dr. One"},
        {"id": 11, "name": "Dr. Two"},
        {"id": 12, "name": "Dr. Three"},
    ]
    constraints = {
        "faculty_availability": {
            10: {"unavailable_slots": [3]},
        },
        "prior_commitments": {
            11: [4],
        },
        "coverage_mode": "strict",
    }
    locked_slots = [
        {"subject_id": 2, "timeslot_id": 1, "lock_source": "Manual Lock"},
    ]
    original = copy.deepcopy((subjects, faculty, constraints, locked_slots))

    analyzer = DeepDiagnosticAnalyzer(
        subjects,
        faculty,
        _timeslots(),
        constraints,
        locked_slots,
    )

    java = next(row for row in analyzer.analysis["subjects"] if row["subject_id"] == 1)
    assert [stage["remaining"] for stage in java["stages"][:5]] == [4, 3, 2, 1, 0]
    assert java["blocking_reasons"] == ["Faculty Commitments"]
    multi = analyzer.analysis["multi_faculty"][0]
    assert multi["common_available_slots"] == []
    assert (subjects, faculty, constraints, locked_slots) == original


def test_deep_diagnostics_detects_locked_variable_contradiction():
    analyzer = DeepDiagnosticAnalyzer(
        subjects=[
            {
                "id": 1,
                "name": "Java Lab",
                "weekly_hours": 2,
                "continuous_hours": 2,
                "faculty_id": 10,
            }
        ],
        faculty=[{"id": 10, "name": "Dr. One"}],
        timeslots=_timeslots(),
        constraints={
            "faculty_availability": {
                10: {"unavailable_slots": [2]},
            }
        },
        locked_slots=[
            {
                "subject_id": 1,
                "timeslot_id": 2,
                "lock_source": "Section Override",
            }
        ],
    )

    contradiction = analyzer.analysis["contradictions"][0]
    assert contradiction["subject_id"] == 1
    assert contradiction["timeslot_id"] == 2
    assert contradiction["forced_true_by"] == "Section Override"
    assert any("Break slot" in reason for reason in contradiction["forced_false_by"])
    assert any("Faculty unavailable" in reason for reason in contradiction["forced_false_by"])


def test_failure_summary_names_subject_faculty_timeslot_and_constraint(caplog):
    analyzer = DeepDiagnosticAnalyzer(
        subjects=[
            {
                "id": 1,
                "name": "Programming in Java",
                "weekly_hours": 1,
                "continuous_hours": 1,
                "faculty_id": 10,
            }
        ],
        faculty=[{"id": 10, "name": "Dr. One"}],
        timeslots=[{"id": 1, "day": "Monday", "time": "09:00:00", "is_break": False}],
        constraints={"prior_commitments": {10: [1]}},
        locked_slots=[],
    )

    with caplog.at_level(logging.ERROR, logger="timewise.ai_engine.deep_diagnostics"):
        analyzer.log_failure_summary(
            core_reasons=["Faculty Prior Commitment"],
            seed=42,
        )

    text = caplog.text
    assert "CP-SAT FAILURE SUMMARY" in text
    assert "Programming in Java" in text
    assert "Faculty Prior Commitment" in text
    assert "10" in text
    assert "42" in text


def test_diagnostic_failure_cannot_change_solver_behavior(monkeypatch):
    def fail_diagnostics(*args, **kwargs):
        raise RuntimeError("diagnostic-only failure")

    monkeypatch.setattr(
        cp_sat_solver_module,
        "DeepDiagnosticAnalyzer",
        fail_diagnostics,
    )
    solver = cp_sat_solver_module.CPSatSolver(
        subjects=[
            {
                "id": 1,
                "name": "Maths",
                "weekly_hours": 1,
                "continuous_hours": 1,
                "faculty_id": 10,
            }
        ],
        faculty=[{"id": 10, "name": "Dr. One"}],
        timeslots=[
            {"id": 1, "day": "Monday", "time": "09:00:00", "is_break": False},
        ],
        constraints={"random_seed": 7},
        locked_slots=[],
    )

    result = solver.solve_single(seed=7, time_limit_seconds=1)
    assert result is not None
    assert result["schedule"] == [
        {"subject_id": 1, "faculty_id": 10, "timeslot_id": 1}
    ]
