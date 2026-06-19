import logging
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any, Dict

try:
    from scheduler_core.cp_sat_solver import CPSatSolver
    from scheduler_core import candidate_diversity, health_metrics, explainability
except (ImportError, ValueError):
    try:
        from .scheduler_core.cp_sat_solver import CPSatSolver
        from .scheduler_core import candidate_diversity, health_metrics, explainability
    except (ImportError, ValueError):
        from ai_engine.scheduler_core.cp_sat_solver import CPSatSolver
        from ai_engine.scheduler_core import candidate_diversity, health_metrics, explainability

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="TimeWise AI scheduler", version="0.2.0")

class OptimizationRequest(BaseModel):
    semester: int
    subjects: List[Dict[str, Any]]
    faculty: List[Dict[str, Any]]
    timeslots: List[Dict[str, Any]]
    constraints: Optional[Dict[str, Any]] = None
    locked_slots: Optional[List[Dict[str, Any]]] = None

@app.post("/optimize")
def optimize_schedule(request: OptimizationRequest):
    start_time = time.time()
    constraints = request.constraints or {}
    locked_slots = request.locked_slots or []

    def _parse_fid(fid):
        try:
            return int(fid)
        except (TypeError, ValueError):
            return fid

    def _parse_slot_id(slot_id):
        try:
            return int(slot_id)
        except (TypeError, ValueError):
            return slot_id

    def _slot_set_for(mapping, fid, slot_key):
        normalized_fid = _parse_fid(fid)
        if isinstance(mapping, dict):
            config = mapping.get(normalized_fid) or mapping.get(str(normalized_fid))
            if isinstance(config, dict):
                return {_parse_slot_id(slot_id) for slot_id in (config.get(slot_key, []) or config.get("occupied_slots", []) or [])}
            return {_parse_slot_id(slot_id) for slot_id in (config or [])}
        if isinstance(mapping, list):
            slots = set()
            for item in mapping:
                if not isinstance(item, dict) or _parse_fid(item.get("faculty_id")) != normalized_fid:
                    continue
                if "timeslot_id" in item:
                    slots.add(_parse_slot_id(item.get("timeslot_id")))
                else:
                    slots.update(_parse_slot_id(slot_id) for slot_id in (item.get(slot_key, []) or item.get("occupied_slots", []) or []))
            return slots
        return set()

    logger.info(
        "Optimize request received: semester=%s, subjects=%s, faculty=%s, timeslots=%s, locked_entries=%s, coverage_mode=%s, partial=%s",
        request.semester,
        len(request.subjects),
        len(request.faculty),
        len(request.timeslots),
        len(locked_slots),
        constraints.get("coverage_mode"),
        constraints.get("allow_partial_schedule", False),
    )
    faculty_availability = constraints.get("faculty_availability", {}) or {}
    prior_commitments = constraints.get("prior_commitments", {}) or {}
    for faculty in request.faculty:
        fid = faculty.get("id")
        logger.info(
            "Faculty Availability Summary: faculty_id=%s, preferred=%s, unavailable=%s, commitments=%s",
            fid,
            len(_slot_set_for(faculty_availability, fid, "preferred_slots")),
            len(_slot_set_for(faculty_availability, fid, "unavailable_slots")),
            len(_slot_set_for(prior_commitments, fid, "occupied_slots")),
        )
    
    # Strict validation of weekly_hours
    for s in request.subjects:
        weekly_hours = s.get("weekly_hours")
        if weekly_hours is None:
            raise HTTPException(
                status_code=400,
                detail=f"Subject Demand Validation: Subject '{s.get('name', s.get('id'))}' (ID={s.get('id')}) is missing weekly_hours."
            )
        try:
            weekly_hours_val = int(weekly_hours)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail=f"Subject Demand Validation: Subject '{s.get('name', s.get('id'))}' (ID={s.get('id')}) has non-integer weekly_hours value: '{weekly_hours}'."
            )
        if weekly_hours_val <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"Subject Demand Validation: Subject '{s.get('name', s.get('id'))}' (ID={s.get('id')}) has invalid weekly_hours <= 0: {weekly_hours_val}."
            )
            
    # Base random seed from payload or fallback
    base_seed = constraints.get("random_seed")
    if base_seed is None:
        combo = "".join(str(s.get("id")) for s in request.subjects) + "".join(str(f.get("id")) for f in request.faculty)
        base_seed = hash(combo) & 0x7fffffff
    else:
        try:
            base_seed = int(base_seed) & 0x7fffffff
        except Exception:
            base_seed = hash(str(base_seed)) & 0x7fffffff
            
    # Generate several diverse candidates so peer-timetable penalties have room to work.
    default_candidate_count = 15 if constraints.get("peer_timetables") else 1
    target_candidate_count = int(constraints.get("candidate_limit", default_candidate_count) or default_candidate_count)
    target_candidate_count = max(1, min(30, target_candidate_count))
    candidates = []
    rejected_info = []
    
    # Time budget configuration
    time_budget = constraints.get("time_budget_seconds", 20.0)
    solve_time_limit = max(1.0, min(5.0, time_budget / target_candidate_count))
    
    # Build solver instance
    try:
        solver = CPSatSolver(
            subjects=request.subjects,
            faculty=request.faculty,
            timeslots=request.timeslots,
            constraints=constraints,
            locked_slots=locked_slots
        )
    except ValueError as e:
        logger.error(f"Validation/Capacity error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    max_attempts = target_candidate_count * 3
    attempt = 0
    
    while len(candidates) < target_candidate_count and attempt < max_attempts:
        if time.time() - start_time >= time_budget:
            break
            
        current_seed = (base_seed + attempt) & 0x7fffffff
        attempt += 1
        
        try:
            res = solver.solve_single(current_seed, time_limit_seconds=solve_time_limit)
            if not res:
                logger.warning("Candidate rejected: seed=%s, reason=infeasible", current_seed)
                rejected_info.append({
                    "seed": current_seed,
                    "reason": "Solver could not find a feasible solution under the constraints.",
                    "score": 0.0
                })
                continue
                
            schedule = res["schedule"]
            
            # Check Candidate Diversity against existing candidates
            existing_schedules = [c["schedule"] for c in candidates]
            if not candidate_diversity.is_diverse_enough(schedule, existing_schedules, request.timeslots, threshold=80.0):
                logger.info(
                    "Candidate rejected: seed=%s, reason=not_diverse, score=%s",
                    current_seed,
                    res["objective_value"],
                )
                rejected_info.append({
                    "seed": current_seed,
                    "reason": "Rejected due to similarity (>80%) with a previously accepted candidate.",
                    "score": res["objective_value"]
                })
                continue
                
            coverage = res.get("coverage_report") or {}
            logger.info(
                "Candidate accepted: seed=%s, score=%s, entries=%s, unmet_hours=%s",
                current_seed,
                res["objective_value"],
                len(schedule),
                coverage.get("unmet_hours"),
            )
            candidates.append(res)
            
        except Exception as e:
            logger.error(f"Error during candidate generation: {e}")
            rejected_info.append({
                "seed": current_seed,
                "reason": f"Solver error: {str(e)}",
                "score": 0.0
            })
            continue

    if not candidates and constraints.get("allow_partial_schedule_fallback", True) and not constraints.get("allow_partial_schedule"):
        logger.warning(
            "No strict candidates found in /optimize. Retrying once with allow_partial_schedule=True."
        )
        relaxed_constraints = dict(constraints)
        relaxed_constraints["allow_partial_schedule"] = True
        relaxed_constraints["coverage_mode"] = "fill_remaining"
        try:
            relaxed_solver = CPSatSolver(
                subjects=request.subjects,
                faculty=request.faculty,
                timeslots=request.timeslots,
                constraints=relaxed_constraints,
                locked_slots=locked_slots,
            )
            relaxed_result = relaxed_solver.solve_single(base_seed, time_limit_seconds=max(10.0, solve_time_limit))
            if relaxed_result:
                candidates.append(relaxed_result)
        except Exception as e:
            logger.error("Relaxed /optimize fallback failed: %s", e)

    if not candidates:
        reasons_summary = "; ".join(set(r["reason"] for r in rejected_info))
        raise HTTPException(status_code=400, detail=f"Failed to generate any valid schedules: {reasons_summary}")
        
    # Rank candidates by objective value descending
    candidates.sort(key=lambda x: x["objective_value"], reverse=True)
    best_candidate = candidates[0]
    best_coverage = best_candidate.get("coverage_report") or {}
    for faculty in request.faculty:
        fid = faculty.get("id")
        scheduled_slots = {
            _parse_slot_id(entry.get("timeslot_id"))
            for entry in best_candidate["schedule"]
            if entry.get("faculty_id") == fid
        }
        preferred_slots = _slot_set_for(faculty_availability, fid, "preferred_slots")
        unavailable_slots = _slot_set_for(faculty_availability, fid, "unavailable_slots")
        commitment_slots = _slot_set_for(prior_commitments, fid, "occupied_slots")
        logger.info(
            "Faculty Utilization Report: faculty_id=%s, preferred_used=%s/%s, unavailable_violations=%s, commitment_violations=%s",
            fid,
            len(scheduled_slots & preferred_slots),
            len(preferred_slots),
            len(scheduled_slots & unavailable_slots),
            len(scheduled_slots & commitment_slots),
        )
    
    # Calculate health metrics for the best candidate
    best_health = health_metrics.calculate_health_metrics(
        best_candidate["schedule"], request.subjects, request.timeslots, constraints
    )
    
    # Generate explainability details
    selection_reason = explainability.generate_selection_reason(
        best_candidate["objective_value"], best_candidate["subscores"], best_health
    )
    
    # Populate explainability for rejected/other candidates
    rejected_candidates_explainability = []
    for idx, c in enumerate(candidates[1:], start=1):
        rejected_candidates_explainability.append(
            explainability.get_rejection_reason(c["objective_value"], c["subscores"], idx)
        )
    for r in rejected_info:
        rejected_candidates_explainability.append(
            f"Candidate seed {r['seed']} rejected: {r['reason']}"
        )
        
    generation_time_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "Optimize result selected: status=%s, score=%s, entries=%s, unmet_hours=%s, empty_teaching_slots=%s, generation_ms=%s",
        best_candidate.get("solver_status"),
        best_candidate["objective_value"],
        len(best_candidate["schedule"]),
        best_coverage.get("unmet_hours"),
        best_coverage.get("empty_teaching_slots"),
        generation_time_ms,
    )
    
    # Build constraint summary from best candidate's stats
    constraint_summary = f"CP-SAT Solver status: {best_candidate.get('solver_status', 'UNKNOWN')}. Model stats:\n{best_candidate.get('model_stats', '')}"
    
    return {
        "status": "success",
        "schedule": best_candidate["schedule"],
        "score_breakdown": best_candidate["subscores"],
        "health_metrics": best_health,
        "coverage_report": best_coverage,
        "selection_reason": selection_reason,
        "rejected_candidates": rejected_candidates_explainability,
        "generation_time_ms": generation_time_ms,
        "candidate_scores": [c["objective_value"] for c in candidates],
        "constraint_summary": constraint_summary
    }

@app.get("/")
def root():
    return {
        "status": "healthy",
        "service": "TimeWise AI Engine"
    }
