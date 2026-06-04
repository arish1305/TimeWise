import logging
import time
from typing import List, Dict, Any, Optional
from ortools.sat.python import cp_model

import constraint_registry
import objective_registry
import schedule_decoder

try:
    import constraint_diagnostics
except ImportError:
    from . import constraint_diagnostics

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
        self.perform_audits_and_capacity_check()

    def perform_audits_and_capacity_check(self):
        """
        Performs pre-solver capacity verification and logs detailed timeslot,
        subject, and capacity attributes. Raises ValueError if infeasible.
        """
        # 1. Log and verify timeslots
        logger.info("--- TIMESLOT AUDIT ---")
        break_slots = set()
        for t in self.timeslots:
            tid = t.get("id")
            label = t.get("label") or "No Label"
            is_break = bool(t.get("is_break", False))
            is_teaching_slot = not is_break
            logger.info(f"Timeslot: id={tid}, label={label}, is_break={is_break}, is_teaching_slot={is_teaching_slot}")
            if is_break:
                break_slots.add(tid)

        # 2. Check if locked slot is on a break timeslot
        logger.info("--- LOCKED SLOTS AUDIT ---")
        locked_hours_by_subject = {}
        locked_slots_used = set()
        locked_slots_for_fac = {} # fid -> set of tids
        
        for ls in self.locked_slots:
            sid = ls.get("subject_id")
            tid = ls.get("timeslot_id")
            fid = ls.get("faculty_id")
            if tid is not None:
                if tid in break_slots:
                    raise ValueError(f"Cannot schedule subject {sid} to break slot {tid}")
                if sid is not None:
                    locked_hours_by_subject[sid] = locked_hours_by_subject.get(sid, 0) + 1
                    locked_slots_used.add(tid)
                if fid is not None and sid is not None:
                    locked_slots_for_fac.setdefault(fid, set()).add(tid)

        # 3. Log and verify subjects
        logger.info("--- SUBJECT AUDIT & DEMAND ---")
        subjects_with_faculty = []
        subjects_without_faculty = []
        non_elective_subjects = []
        elective_groups = {} # group_id -> list of subjects

        for s in self.subjects:
            sid = s["id"]
            credits = s.get("credits")
            weekly_hours = s.get("weekly_hours")
            if weekly_hours is None:
                weekly_hours = credits or 3
            weekly_hours = int(weekly_hours)
            continuous_hours = int(s.get("continuous_hours", 1) or 1)
            subject_type = s.get("subject_type", "THEORY")
            fid = s.get("faculty_id")
            
            s_name = s.get("name") or f"Subject {sid}"
            
            # Cache resolved weekly hours on the subject dict for solver use
            s["_resolved_weekly_hours"] = weekly_hours
            
            locked_hours = locked_hours_by_subject.get(sid, 0)
            net_hours = max(0, weekly_hours - locked_hours)
            s["_net_hours"] = net_hours

            logger.info(
                f"Subject: id={sid}, name='{s_name}', credits={credits}, "
                f"weekly_hours={weekly_hours}, continuous_hours={continuous_hours}, "
                f"subject_type={subject_type}, faculty_id={fid}, locked_hours={locked_hours}, net_hours={net_hours}"
            )

            if fid is not None:
                subjects_with_faculty.append(sid)
            else:
                subjects_without_faculty.append(sid)

            if s.get("is_elective"):
                group_id = str(s.get("elective_group_id") or "").strip()
                if group_id:
                    elective_groups.setdefault(group_id, []).append(s)
                else:
                    non_elective_subjects.append(s)
            else:
                non_elective_subjects.append(s)

        logger.info(f"Subjects with assigned faculty: {subjects_with_faculty}")
        logger.info(f"Subjects without assigned faculty: {subjects_without_faculty}")

        # 4. Net required hours vs usable timeslots
        net_required_hours = sum(s["_net_hours"] for s in non_elective_subjects)
        for group_id, group_subs in elective_groups.items():
            net_required_hours += max(s["_net_hours"] for s in group_subs)

        available_slots = len(self.timeslots) - len(break_slots)
        unique_locked_slots = len(locked_slots_used.difference(break_slots))
        usable_slots = available_slots - unique_locked_slots

        logger.info(
            f"Capacity status: net_required_hours={net_required_hours}, "
            f"available_slots={available_slots}, unique_locked_slots={unique_locked_slots}, usable_slots={usable_slots}"
        )

        if net_required_hours > usable_slots:
            raise ValueError(
                f"Insufficient timeslots: Net required teaching hours ({net_required_hours}) "
                f"exceeds usable slots ({usable_slots}). Total available slots: {available_slots}, "
                f"unique locked slots: {unique_locked_slots}."
            )

        # 5. Faculty Capacity Check
        if self.faculty:
            logger.info("--- FACULTY CAPACITY AUDIT ---")
            faculty_prefs = self.constraints.get("faculty_preferences", {}) or {}
            prior_commitments = self.constraints.get("prior_commitments", {}) or {}
            
            def parse_fid(f_id):
                try:
                    return int(f_id)
                except (ValueError, TypeError):
                    return f_id

            fac_prior_slots = {}
            for fid, slots in prior_commitments.items():
                pfid = parse_fid(fid)
                fac_prior_slots.setdefault(pfid, set()).update(slots or [])

            for f in self.faculty:
                fid = f["id"]
                pfid = parse_fid(fid)
                f_name = f.get("name") or f"Faculty {fid}"
                
                prefs = faculty_prefs.get(str(fid)) or faculty_prefs.get(fid) or {}
                max_hours = f.get("max_hours_per_week")
                if max_hours is None:
                    max_hours = prefs.get("max_hours", 18)
                max_hours = int(max_hours or 18)

                assigned_subjects = [s for s in self.subjects if s.get("faculty_id") == fid]
                total_assigned_demand = sum(s["_resolved_weekly_hours"] for s in assigned_subjects)
                net_demand_for_fac = sum(s["_net_hours"] for s in assigned_subjects)

                # Prior commitments
                prior_slots = fac_prior_slots.get(pfid, set())
                locked_slots_for_fac_ids = locked_slots_for_fac.get(fid, set())
                
                # Remaining hours capacity under max_hours limit
                remaining_capacity = max_hours - len(prior_slots) - len(locked_slots_for_fac_ids)
                
                # Physical availability: slots that are not break, not prior commitments, and not locked for other subjects
                slots_allowed_for_fac = {t["id"] for t in self.timeslots if not t.get("is_break", False)} - prior_slots - (locked_slots_used - locked_slots_for_fac_ids)

                logger.info(
                    f"Faculty '{f_name}' (ID={fid}): max_hours={max_hours}, "
                    f"assigned_demand={total_assigned_demand}, net_demand={net_demand_for_fac}, "
                    f"prior_commitments={len(prior_slots)}, locked_slots={len(locked_slots_for_fac_ids)}, "
                    f"remaining_capacity={remaining_capacity}, physical_slots_available={len(slots_allowed_for_fac)}"
                )

                if total_assigned_demand > max_hours:
                    raise ValueError(
                        f"Faculty Overload: Faculty '{f_name}' (ID={fid}) is assigned {total_assigned_demand} hours, "
                        f"which exceeds their maximum capacity of {max_hours} hours."
                    )

                if net_demand_for_fac > remaining_capacity:
                    raise ValueError(
                        f"Faculty Overload: Faculty '{f_name}' (ID={fid}) needs {net_demand_for_fac} more hours, "
                        f"but has a remaining capacity of only {remaining_capacity} hours (max_hours={max_hours}, prior={len(prior_slots)}, locked={len(locked_slots_for_fac_ids)})."
                    )

                if net_demand_for_fac > len(slots_allowed_for_fac):
                    raise ValueError(
                        f"Faculty Overload: Faculty '{f_name}' (ID={fid}) needs {net_demand_for_fac} hours, "
                        f"but has only {len(slots_allowed_for_fac)} physically available slots."
                    )

    def _log_input_summary(self):
        """Log a summary of inputs to help diagnose infeasibility."""
        logger.info(
            f"CP-SAT Solver input: {len(self.subjects)} subjects, "
            f"{len(self.faculty)} faculty, {len(self.timeslots)} timeslots, "
            f"{len(self.locked_slots)} locked slots"
        )
        
        # Count locked hours per subject
        locked_per_subject = {}
        for ls in self.locked_slots:
            sid = ls.get("subject_id")
            if sid:
                locked_per_subject[sid] = locked_per_subject.get(sid, 0) + 1
        
        total_credits = 0
        net_sessions = 0
        for s in self.subjects:
            sid = s["id"]
            credits = int(s.get("credits", 3) or 3)
            locked = locked_per_subject.get(sid, 0)
            needed = max(0, credits - locked)
            total_credits += credits
            net_sessions += needed
            logger.info(
                f"  Subject '{s.get('name', sid)}' (id={sid}): "
                f"type={s.get('subject_type', 'THEORY')}, credits={credits}, "
                f"locked={locked}, needs={needed}, "
                f"continuous={s.get('continuous_hours', 1)}, "
                f"faculty={s.get('faculty_id')}"
            )
        
        locked_count = len(self.locked_slots)
        unique_locked_timeslots = {
            ls.get("timeslot_id") for ls in self.locked_slots if ls.get("timeslot_id") is not None
        }
        unique_locked_count = len(unique_locked_timeslots)
        available_slots = len(self.timeslots) - unique_locked_count
        shared_locked_entries = max(0, locked_count - unique_locked_count)
        logger.info(
            f"Summary: gross_credits={total_credits}, net_sessions_needed={net_sessions}, "
            f"available_non_locked_slots={available_slots}, "
            f"locked_entries={locked_count}, unique_locked_slots={unique_locked_count}, "
            f"shared_locked_entries={shared_locked_entries}"
        )
        if net_sessions > available_slots:
            logger.warning(
                f"INFEASIBILITY RISK: Need {net_sessions} sessions but only "
                f"{available_slots} non-locked slots available!"
            )

    def solve_single(self, seed: int, time_limit_seconds: float = 20.0) -> Optional[Dict[str, Any]]:
        """
        Builds and solves a single CP-SAT model using the given random seed.
        """
        model = cp_model.CpModel()
        
        # 1. Create variables
        # Map: subject_id -> timeslot_id -> IntVar (0 or 1)
        x = {}
        
        # We also identify elective groups to link their variables
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

        # 4. Configure Solver
        solver = cp_model.CpSolver()
        solver.parameters.random_seed = seed
        solver.parameters.max_time_in_seconds = time_limit_seconds
        
        # Default to 1 search worker to guarantee 100% deterministic search results
        num_workers = self.constraints.get("rules", {}).get("num_search_workers", 1)
        solver.parameters.num_search_workers = num_workers

        # Solve
        start_solve = time.time()
        status = solver.Solve(model)
        solve_duration = time.time() - start_solve
        
        status_name = solver.StatusName(status)
        logger.info(f"CP-SAT solve (seed={seed}): status={status_name}, time={solve_duration:.2f}s")
        
        if status == cp_model.INFEASIBLE:
            logger.warning(
                f"CP-SAT model is INFEASIBLE (seed={seed}). "
                f"The hard constraints are contradictory for this data."
            )
            return None
        
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # Decode the schedule
            schedule = schedule_decoder.decode_schedule(solver, x, self.subjects, self.timeslots)
            
            # Extract objective details
            obj_val = solver.ObjectiveValue()
            
            model_stats = model.ModelStats()
            
            # Compute subscores from the solution
            subscores = objective_registry.evaluate_solution_subscores(
                solver, x, self.subjects, self.faculty, self.timeslots, self.constraints
            )
            
            return {
                "schedule": schedule,
                "objective_value": obj_val,
                "subscores": subscores,
                "solve_duration_ms": int(solve_duration * 1000),
                "model_stats": model_stats,
                "solver_status": status_name
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
        
        # Allocate time budget per candidate solve
        solve_time_limit = max(1.5, min(5.0, time_budget / max(1, candidate_limit)))
        
        candidates = []
        seen_schedules = []
        infeasible_count = 0
        
        start_time = time.time()
        attempt = 0
        max_attempts = candidate_limit * 3
        
        while len(candidates) < candidate_limit and attempt < max_attempts:
            # Check total time budget
            if time.time() - start_time >= time_budget:
                break
                
            current_seed = (base_seed + attempt) & 0x7fffffff
            attempt += 1
            
            try:
                res = self.solve_single(current_seed, time_limit_seconds=solve_time_limit)
                if res:
                    # Simple duplicate schedule check (by slot assignment equality)
                    sched_slots = {(e["subject_id"], e["timeslot_id"]) for e in res["schedule"]}
                    if sched_slots not in seen_schedules:
                        seen_schedules.append(sched_slots)
                        candidates.append(res)
                else:
                    infeasible_count += 1
                    # If we've seen multiple infeasible results, the model itself
                    # is likely infeasible — stop early rather than burning time
                    if infeasible_count >= 3:
                        logger.warning(
                            f"Got {infeasible_count} infeasible results. "
                            "Stopping candidate generation early."
                        )
                        break
            except Exception as e:
                logger.error(f"CP-SAT solver thread error: {e}")
                
        if not candidates:
            # Run diagnostics
            try:
                diagnostics = constraint_diagnostics.diagnose_infeasibility(
                    subjects=self.subjects,
                    faculty=self.faculty,
                    timeslots=self.timeslots,
                    constraints=self.constraints,
                    locked_slots=self.locked_slots
                )
            except Exception as e:
                diagnostics = [f"Failed to run diagnostic debugger: {str(e)}"]
                
            diag_message = "\n".join(f" - {d}" for d in diagnostics)
            
            raise ValueError(
                "CP-SAT solver failed to find any feasible schedule within the constraints.\n"
                "Unsatisfiable Core Constraints:\n"
                f"{diag_message}"
            )

        # Rank candidates by objective score descending
        candidates.sort(key=lambda c: c["objective_value"], reverse=True)
        
        # Return the best schedule entries
        return candidates[0]["schedule"]
