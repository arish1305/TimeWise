import logging
import time
import os
import json
from typing import List, Dict, Any, Optional
from ortools.sat.python import cp_model

from . import constraint_registry
from . import objective_registry
from . import schedule_decoder
from . import constraint_diagnostics
from . import capacity_analyzer
from . import constraint_statistics
from . import feasibility_explainer
from . import slot_utilization_analyzer

logger = logging.getLogger(__name__)

class CPSatSolver:
    def __init__(
        self,
        subjects: List[Dict[str, Any]],
        faculty: List[Dict[str, Any]],
        timeslots: List[Dict[str, Any]],
        constraints: Optional[Dict[str, Any]] = None,
        locked_slots: Optional[List[Dict[str, Any]]] = None
    ):
        self.subjects = subjects
        self.faculty = faculty
        self.timeslots = timeslots
        self.constraints = constraints or {}
        self.locked_slots = locked_slots or []
        
        # Setup diagnostics folder (at workspace root level or relative path)
        self.diagnostics_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "diagnostics"))
        os.makedirs(self.diagnostics_dir, exist_ok=True)
        
        # 1. Dump Debug Schedule Input before capacity analysis
        self._dump_debug_input()
        
        # 2. Perform Capacity Analyzer
        try:
            self.capacity_report = capacity_analyzer.analyze_capacity(
                self.subjects, self.faculty, self.timeslots, self.constraints, self.locked_slots
            )
        except ValueError as e:
            # Write IMPOSSIBLE report to diagnostics
            feasibility_path = os.path.join(self.diagnostics_dir, "feasibility_report.json")
            with open(feasibility_path, "w") as f:
                json.dump({
                    "status": "IMPOSSIBLE",
                    "reason": str(e)
                }, f, indent=2)
            raise e

    def get_cbcs_groups(self) -> List[List[int]]:
        groups = {}
        for s in self.subjects:
            if s.get("is_elective"):
                group_id = str(s.get("elective_group_id") or "").strip()
                if group_id:
                    groups.setdefault(group_id, []).append(s["id"])
        return list(groups.values())

    def _coverage_mode(self) -> str:
        coverage_mode = str(self.constraints.get("coverage_mode") or "").lower()
        if self.constraints.get("allow_partial_schedule") or coverage_mode in {"partial", "relaxed", "fill_remaining", "repair"}:
            return "partial"
        return "strict"

    def _locked_hours_by_subject(self) -> Dict[int, int]:
        locked_hours = {}
        for locked in self.locked_slots:
            sid = locked.get("subject_id")
            if sid is not None:
                locked_hours[sid] = locked_hours.get(sid, 0) + 1
        return locked_hours

    def _build_coverage_report(self, schedule: List[Dict[str, Any]]) -> Dict[str, Any]:
        scheduled_by_subject = {}
        for entry in schedule:
            sid = entry.get("subject_id")
            if sid is not None:
                scheduled_by_subject[sid] = scheduled_by_subject.get(sid, 0) + 1

        locked_hours = self._locked_hours_by_subject()
        subject_rows = []
        total_required = 0
        total_scheduled = 0
        total_unmet = 0
        total_over = 0

        for subject in self.subjects:
            sid = subject["id"]
            required = int(subject.get("weekly_hours") or subject.get("credits") or 0)
            scheduled = scheduled_by_subject.get(sid, 0)
            unmet = max(0, required - scheduled)
            over = max(0, scheduled - required)
            total_required += required
            total_scheduled += scheduled
            total_unmet += unmet
            total_over += over
            subject_rows.append({
                "subject_id": sid,
                "name": subject.get("name"),
                "required_hours": required,
                "scheduled_hours": scheduled,
                "locked_hours": locked_hours.get(sid, 0),
                "unmet_hours": unmet,
                "over_scheduled_hours": over,
            })

        break_slot_ids = {t["id"] for t in self.timeslots if t.get("is_break", False)}
        teaching_slot_ids = {t["id"] for t in self.timeslots if not t.get("is_break", False)}
        occupied_teaching_slots = {
            entry["timeslot_id"]
            for entry in schedule
            if entry.get("timeslot_id") in teaching_slot_ids
        }

        return {
            "mode": self._coverage_mode(),
            "required_hours": total_required,
            "scheduled_entries": total_scheduled,
            "unmet_hours": total_unmet,
            "over_scheduled_hours": total_over,
            "teaching_slots": len(teaching_slot_ids),
            "occupied_teaching_slots": len(occupied_teaching_slots),
            "empty_teaching_slots": max(0, len(teaching_slot_ids) - len(occupied_teaching_slots)),
            "break_slots": len(break_slot_ids),
            "locked_entries": len(self.locked_slots),
            "unique_locked_slots": len({ls.get("timeslot_id") for ls in self.locked_slots if ls.get("timeslot_id") is not None}),
            "subjects": subject_rows,
        }

    def _log_input_summary(self) -> None:
        locked_hours = self._locked_hours_by_subject()
        teaching_slots = [t for t in self.timeslots if not t.get("is_break", False)]
        locked_slot_ids = {ls.get("timeslot_id") for ls in self.locked_slots if ls.get("timeslot_id") is not None}
        net_demand = 0
        gross_demand = 0

        logger.info(
            "CP-SAT input summary: subjects=%s, faculty=%s, timeslots=%s, teaching_slots=%s, locked_entries=%s, unique_locked_slots=%s, coverage_mode=%s",
            len(self.subjects),
            len(self.faculty),
            len(self.timeslots),
            len(teaching_slots),
            len(self.locked_slots),
            len(locked_slot_ids),
            self._coverage_mode(),
        )
        for subject in self.subjects:
            sid = subject["id"]
            required = int(subject.get("weekly_hours") or subject.get("credits") or 0)
            locked = locked_hours.get(sid, 0)
            needed = max(0, required - locked)
            gross_demand += required
            net_demand += needed
            logger.info(
                "CP-SAT subject demand: id=%s, name=%s, required=%s, locked=%s, remaining=%s, continuous=%s, faculty=%s, elective=%s, group=%s",
                sid,
                subject.get("name"),
                required,
                locked,
                needed,
                subject.get("continuous_hours", 1),
                subject.get("faculty_id"),
                subject.get("is_elective", False),
                subject.get("elective_group_id"),
            )

        logger.info(
            "CP-SAT capacity summary: gross_demand=%s, net_demand=%s, non_locked_teaching_slots=%s",
            gross_demand,
            net_demand,
            max(0, len(teaching_slots) - len(locked_slot_ids)),
        )

    def _dump_debug_input(self):
        debug_input_path = os.path.join(self.diagnostics_dir, "debug_schedule_input.json")
        try:
            with open(debug_input_path, "w") as f:
                json.dump({
                    "subjects": self.subjects,
                    "timeslots": self.timeslots,
                    "faculty": self.faculty,
                    "cbcs_groups": self.get_cbcs_groups(),
                    "locked_slots": self.locked_slots,
                    "constraints": self.constraints
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to dump debug schedule input: {e}")

    def solve_single(self, seed: int, time_limit_seconds: float = 20.0) -> Optional[Dict[str, Any]]:
        """
        Builds and solves a single CP-SAT model using the given random seed.
        """
        model = cp_model.CpModel()
        
        # 1. Create variables
        # Map: subject_id -> timeslot_id -> IntVar (0 or 1)
        x = {}
        
        # Identify elective groups to link their variables
        elective_groups = {}
        for s in self.subjects:
            group_id = str(s.get("elective_group_id") or "").strip()
            if s.get("is_elective") and group_id:
                elective_groups.setdefault(group_id, []).append(s["id"])

        # Create binary variables for each subject and slot
        for s in self.subjects:
            sid = s["id"]
            x[sid] = {}
            for t in self.timeslots:
                tid = t["id"]
                x[sid][tid] = model.NewBoolVar(f"x_{sid}_{tid}")
                
        # Link elective group variables to be identical
        for group_id, sids in elective_groups.items():
            if len(sids) > 1:
                first_sid = sids[0]
                for other_sid in sids[1:]:
                    for t in self.timeslots:
                        tid = t["id"]
                        model.Add(x[first_sid][tid] == x[other_sid][tid])

        # 2. Add Hard Constraints
        logger.info(
            "Building CP-SAT model: seed=%s, time_limit=%.2fs, coverage_mode=%s",
            seed,
            time_limit_seconds,
            self._coverage_mode(),
        )
        constraint_registry.register_hard_constraints(
            model=model,
            x=x,
            subjects=self.subjects,
            faculty=self.faculty,
            timeslots=self.timeslots,
            constraints=self.constraints,
            locked_slots=self.locked_slots,
            elective_groups=elective_groups
        )

        # 3. Add Soft Objectives
        objective_registry.register_objectives(
            model=model,
            x=x,
            subjects=self.subjects,
            faculty=self.faculty,
            timeslots=self.timeslots,
            constraints=self.constraints,
            elective_groups=elective_groups
        )

        # 4. Generate Constraint Statistics and Report
        try:
            stats = constraint_statistics.calculate_complexity(
                self.subjects, self.faculty, self.timeslots, self.constraints, self.locked_slots
            )
            with open(os.path.join(self.diagnostics_dir, "solver_statistics.json"), "w") as f:
                json.dump(stats, f, indent=2)
            with open(os.path.join(self.diagnostics_dir, "constraint_report.json"), "w") as f:
                json.dump({
                    "hard_constraints": [
                        "Locked slots",
                        "Break timeslots",
                        "Weekly hours exact fulfillment" if self._coverage_mode() == "strict" else "Weekly hours upper bounds with fill maximization",
                        "Section non-overlap",
                        "Faculty non-overlap & prior commitments",
                        "Continuous lab blocks & daily limits"
                    ],
                    "soft_objectives": [
                        "Subject spread",
                        "Period diversity",
                        "Faculty load balance"
                    ],
                    "complexity": stats
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to generate complexity statistics: {e}")

        # 5. Configure Solver
        solver = cp_model.CpSolver()
        solver.parameters.random_seed = seed
        solver.parameters.max_time_in_seconds = time_limit_seconds
        
        # Enforce 1 worker for deterministic search
        solver.parameters.num_search_workers = 1

        # Solve
        start_solve = time.time()
        status = solver.Solve(model)
        solve_duration = time.time() - start_solve
        
        status_name = solver.StatusName(status)
        logger.info(f"CP-SAT solve (seed={seed}): status={status_name}, time={solve_duration:.2f}s")
        
        if status == cp_model.INFEASIBLE:
            logger.warning(f"CP-SAT model is INFEASIBLE (seed={seed}).")
            try:
                report = feasibility_explainer.explain_feasibility(
                    self.subjects, self.faculty, self.timeslots, self.constraints, self.locked_slots, is_feasible=False
                )
                with open(os.path.join(self.diagnostics_dir, "feasibility_report.json"), "w") as f:
                    json.dump(report, f, indent=2)
            except Exception as ex:
                logger.error(f"Failed to generate feasibility report: {ex}")
            return None
        
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # Decode the schedule
            schedule = schedule_decoder.decode_schedule(solver, x, self.subjects, self.timeslots)
            coverage_report = self._build_coverage_report(schedule)
            logger.info(
                "CP-SAT coverage result: mode=%s, scheduled_entries=%s/%s, unmet_hours=%s, occupied_teaching_slots=%s/%s, empty_teaching_slots=%s",
                coverage_report["mode"],
                coverage_report["scheduled_entries"],
                coverage_report["required_hours"],
                coverage_report["unmet_hours"],
                coverage_report["occupied_teaching_slots"],
                coverage_report["teaching_slots"],
                coverage_report["empty_teaching_slots"],
            )
            for row in coverage_report["subjects"]:
                if row["unmet_hours"] or row["over_scheduled_hours"]:
                    logger.warning(
                        "CP-SAT subject coverage: id=%s, name=%s, required=%s, scheduled=%s, locked=%s, unmet=%s, over=%s",
                        row["subject_id"],
                        row["name"],
                        row["required_hours"],
                        row["scheduled_hours"],
                        row["locked_hours"],
                        row["unmet_hours"],
                        row["over_scheduled_hours"],
                    )
            
            # Extract metrics
            obj_val = solver.ObjectiveValue()
            model_stats = model.ModelStats()
            subscores = objective_registry.evaluate_solution_subscores(
                solver, x, self.subjects, self.faculty, self.timeslots, self.constraints
            )
            
            # Write slot utilization and feasibility success reports
            try:
                utilization = slot_utilization_analyzer.analyze_slot_utilization(
                    schedule, self.subjects, self.faculty, self.timeslots, self.constraints
                )
                with open(os.path.join(self.diagnostics_dir, "slot_utilization_report.json"), "w") as f:
                    json.dump(utilization, f, indent=2)
                    
                with open(os.path.join(self.diagnostics_dir, "feasibility_report.json"), "w") as f:
                    json.dump({"status": "FEASIBLE", "reasons": [], "coverage": coverage_report}, f, indent=2)
            except Exception as ex:
                logger.error(f"Failed to generate solution reports: {ex}")
                
            return {
                "schedule": schedule,
                "objective_value": obj_val,
                "subscores": subscores,
                "solve_duration_ms": int(solve_duration * 1000),
                "model_stats": model_stats,
                "solver_status": status_name,
                "coverage_report": coverage_report
            }
            
        return None

    def solve(self) -> List[Dict[str, Any]]:
        """
        Coordinates candidate generation. Solves multiple times with different seeds,
        ranks the candidates, and returns the best schedule.
        """
        self._log_input_summary()
        base_seed = self.constraints.get("random_seed")
        if base_seed is None:
            combo = "".join(str(s.get("id")) for s in self.subjects) + "".join(str(f.get("id")) for f in self.faculty)
            base_seed = hash(combo) & 0x7fffffff
        else:
            try:
                base_seed = int(base_seed) & 0x7fffffff
            except Exception:
                base_seed = hash(str(base_seed)) & 0x7fffffff
                
        candidate_limit = self.constraints.get("candidate_limit", 2)
        time_budget = self.constraints.get("time_budget_seconds", 6.0)
        solve_time_limit = max(1.5, min(5.0, time_budget / max(1, candidate_limit)))
        
        candidates = []
        seen_schedules = []
        infeasible_count = 0
        
        start_time = time.time()
        attempt = 0
        max_attempts = candidate_limit * 3
        
        while len(candidates) < candidate_limit and attempt < max_attempts:
            if time.time() - start_time >= time_budget:
                break
                
            current_seed = (base_seed + attempt) & 0x7fffffff
            attempt += 1
            
            try:
                res = self.solve_single(current_seed, time_limit_seconds=solve_time_limit)
                if res:
                    sched_slots = {(e["subject_id"], e["timeslot_id"]) for e in res["schedule"]}
                    if sched_slots not in seen_schedules:
                        seen_schedules.append(sched_slots)
                        candidates.append(res)
                else:
                    infeasible_count += 1
                    if infeasible_count >= 3:
                        logger.warning(
                            "Got %s infeasible results. Stopping candidate generation early.",
                            infeasible_count,
                        )
                        break
            except Exception as e:
                logger.error(f"CP-SAT solver error: {e}")

        if not candidates and self.constraints.get("allow_partial_schedule_fallback", True) and self._coverage_mode() != "partial":
            logger.warning(
                "Strict model produced no feasible schedule. Retrying with relaxed coverage "
                "(allow_partial_schedule=True) while keeping hard clash/lock constraints."
            )
            relaxed_constraints = dict(self.constraints)
            relaxed_constraints["allow_partial_schedule"] = True
            relaxed_constraints["coverage_mode"] = "fill_remaining"
            relaxed_solver = CPSatSolver(
                subjects=self.subjects,
                faculty=self.faculty,
                timeslots=self.timeslots,
                constraints=relaxed_constraints,
                locked_slots=self.locked_slots,
            )
            relaxed_result = relaxed_solver.solve_single(base_seed, time_limit_seconds=max(10.0, solve_time_limit))
            if relaxed_result:
                candidates.append(relaxed_result)

        if not candidates:
            # Diagnose and raise error
            report = feasibility_explainer.explain_feasibility(
                self.subjects, self.faculty, self.timeslots, self.constraints, self.locked_slots, is_feasible=False
            )
            diag_message = "\n".join(f" - {d}" for d in report.get("reasons", []))
            raise ValueError(
                "CP-SAT solver failed to find any feasible schedule within the constraints.\n"
                "Unsatisfiable Core Constraints:\n"
                f"{diag_message}"
            )

        candidates.sort(key=lambda c: c["objective_value"], reverse=True)
        best = candidates[0]
        coverage = best.get("coverage_report") or {}
        if coverage:
            logger.info(
                "Selected CP-SAT candidate: score=%s, scheduled_entries=%s, unmet_hours=%s, empty_teaching_slots=%s",
                best.get("objective_value"),
                coverage.get("scheduled_entries"),
                coverage.get("unmet_hours"),
                coverage.get("empty_teaching_slots"),
            )
        return best["schedule"]
