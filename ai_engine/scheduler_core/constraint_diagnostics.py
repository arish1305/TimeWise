import logging
from typing import List, Dict, Any, Optional
from ortools.sat.python import cp_model

logger = logging.getLogger(__name__)

def diagnose_infeasibility(
    subjects: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]],
    constraints: Dict[str, Any],
    locked_slots: List[Dict[str, Any]]
) -> List[str]:
    """
    Builds a diagnostic CP-SAT model where every hard constraint is guarded by an 
    enforcement literal. Uses CP-SAT assumptions to find the minimal unsatisfiable core.
    Returns a list of human-readable constraint violation descriptions.
    """
    model = cp_model.CpModel()
    
    # 1. Create variables
    x = {}
    elective_groups = {}
    for s in subjects:
        group_id = str(s.get("elective_group_id") or "").strip()
        if s.get("is_elective") and group_id:
            elective_groups.setdefault(group_id, []).append(s["id"])

    for s in subjects:
        sid = s["id"]
        x[sid] = {}
        for t in timeslots:
            tid = t["id"]
            x[sid][tid] = model.NewBoolVar(f"diag_x_{sid}_{tid}")
            
    # Link elective groups structurally (these are definition constraints, not relaxed)
    for group_id, sids in elective_groups.items():
        if len(sids) > 1:
            first_sid = sids[0]
            for other_sid in sids[1:]:
                for t in timeslots:
                    tid = t["id"]
                    model.Add(x[first_sid][tid] == x[other_sid][tid])

    # 2. Setup mappings for assumptions
    assumptions = []
    mapping = {}

    def add_diagnostic_constraint(constraint, description):
        lit = model.NewBoolVar(f"lit_{len(assumptions)}")
        model.Add(constraint).OnlyEnforceIf(lit)
        assumptions.append(lit)
        mapping[lit.Index()] = description

    timeslots_by_id = {t["id"]: t for t in timeslots}
    subjects_by_id = {s["id"]: s for s in subjects}
    
    # Group timeslots by day
    slots_by_day = {}
    for t in timeslots:
        day = t.get("day", "Unknown").lower()
        slots_by_day.setdefault(day, []).append(t)
    for day in slots_by_day:
        slots_by_day[day].sort(key=lambda t: t.get("time") or "")

    # Group subjects by faculty
    faculty_subjects = {}
    for s in subjects:
        fid = s.get("faculty_id")
        if fid:
            faculty_subjects.setdefault(fid, []).append(s["id"])

    # 3. Locked Slots
    locked_slots_by_tid = {}
    locked_subject_hours = {}
    for locked in locked_slots:
        tid = locked.get("timeslot_id")
        sid = locked.get("subject_id")
        if tid is not None:
            locked_slots_by_tid.setdefault(tid, set())
            if sid:
                locked_slots_by_tid[tid].add(sid)
                locked_subject_hours[sid] = locked_subject_hours.get(sid, 0) + 1

    for tid, locked_sids in locked_slots_by_tid.items():
        if tid in timeslots_by_id:
            t_label = timeslots_by_id[tid].get("label") or f"Slot {tid}"
            for sid in locked_sids:
                if sid in subjects_by_id:
                    s_name = subjects_by_id[sid].get("name") or f"Subject {sid}"
                    add_diagnostic_constraint(
                        x[sid][tid] == 1,
                        f"Locked Slot: Subject '{s_name}' (ID={sid}) must be scheduled in {t_label}"
                    )
            for other_sid in subjects_by_id:
                if other_sid not in locked_sids:
                    s_name = subjects_by_id[other_sid].get("name") or f"Subject {other_sid}"
                    add_diagnostic_constraint(
                        x[other_sid][tid] == 0,
                        f"Locked Slot: Subject '{s_name}' (ID={other_sid}) cannot be scheduled in {t_label} (slot is locked for others)"
                    )

    non_locked_slot_ids = [t["id"] for t in timeslots if t["id"] not in locked_slots_by_tid]

    # 4. Break Timeslots
    for t in timeslots:
        tid = t["id"]
        if t.get("is_break", False):
            t_label = t.get("label") or f"Break Slot {tid}"
            for sid in subjects_by_id:
                s_name = subjects_by_id[sid].get("name") or f"Subject {sid}"
                add_diagnostic_constraint(
                    x[sid][tid] == 0,
                    f"Break Slot: Teaching is not allowed for '{s_name}' in break slot {t_label}"
                )

    # 5. Weekly Hours
    subject_sessions = {}
    for s in subjects:
        sid = s["id"]
        # Enforce weekly_hours only
        weekly_hours = int(s.get("weekly_hours"))
        locked_hours = locked_subject_hours.get(sid, 0)
        needed = max(0, weekly_hours - locked_hours)
        subject_sessions[sid] = needed

    for s in subjects:
        sid = s["id"]
        sessions_needed = subject_sessions[sid]
        s_name = s.get("name") or f"Subject {sid}"
        if non_locked_slot_ids:
            non_locked_sum = sum(x[sid][tid] for tid in non_locked_slot_ids)
            if sessions_needed > 0:
                add_diagnostic_constraint(
                    non_locked_sum == sessions_needed,
                    f"Weekly Hours: Subject '{s_name}' (ID={sid}) needs exactly {sessions_needed} more scheduled hours"
                )
            else:
                add_diagnostic_constraint(
                    non_locked_sum == 0,
                    f"Weekly Hours: Subject '{s_name}' (ID={sid}) is fully satisfied by locked slots"
                )

    # 6. Section Non-Overlap
    elective_representatives = {}
    for group_id, sids in elective_groups.items():
        if sids:
            elective_representatives[group_id] = sids[0]

    for t in timeslots:
        tid = t["id"]
        t_label = t.get("label") or f"Slot {tid}"
        overlap_terms = []
        for s in subjects:
            sid = s["id"]
            is_group_elective = any(sid in sids for sids in elective_groups.values())
            if not is_group_elective:
                overlap_terms.append(x[sid][tid])
        for group_rep in elective_representatives.values():
            overlap_terms.append(x[group_rep][tid])
            
        if overlap_terms:
            add_diagnostic_constraint(
                sum(overlap_terms) <= 1,
                f"Section Non-Overlap: Section cannot have multiple lessons in {t_label}"
            )

    # 7. Faculty Max Hours, Non-Overlap & Prior Commitments
    prior_commitments = constraints.get("prior_commitments", {}) or {}
    prior_commitment_entries = constraints.get("prior_commitment_entries", {}) or {}
    
    def parse_fid(f_id):
        try:
            return int(f_id)
        except (ValueError, TypeError):
            return f_id

    fac_prior_slots = {}
    for fid, slots in prior_commitments.items():
        pfid = parse_fid(fid)
        fac_prior_slots.setdefault(pfid, set()).update(slots or [])

    fac_prior_subjects = {}
    for fid, entries in prior_commitment_entries.items():
        pfid = parse_fid(fid)
        for entry in entries or []:
            ts_id = entry.get("timeslot_id")
            sub_id = entry.get("subject_id")
            if ts_id is not None and sub_id is not None:
                fac_prior_subjects.setdefault(pfid, {}).setdefault(ts_id, []).append(sub_id)

    faculty_prefs = constraints.get("faculty_preferences", {}) or {}
    all_slot_ids = [t["id"] for t in timeslots]

    for f in faculty:
        fid = f["id"]
        pfid = parse_fid(fid)
        f_name = f.get("name") or f"Faculty {fid}"
        sids = faculty_subjects.get(fid, [])
        if not sids:
            continue
            
        prefs = faculty_prefs.get(str(fid)) or faculty_prefs.get(fid) or {}
        max_hours = int(prefs.get("max_hours", 18) or 18)
        
        add_diagnostic_constraint(
            sum(x[sid][tid] for sid in sids for tid in all_slot_ids) <= max_hours,
            f"Faculty Max Hours: Faculty '{f_name}' (ID={fid}) is limited to at most {max_hours} teaching hours per week"
        )

        for t in timeslots:
            tid = t["id"]
            t_label = t.get("label") or f"Slot {tid}"
            has_prior = tid in fac_prior_slots.get(pfid, set())
            
            if has_prior:
                prior_sids = fac_prior_subjects.get(pfid, {}).get(tid, [])
                cbcs_sid = None
                for sid in sids:
                    subj = subjects_by_id[sid]
                    if subj.get("is_cbcs_shared") and subj["id"] in prior_sids:
                        cbcs_sid = sid
                        break
                        
                if cbcs_sid is not None:
                    add_diagnostic_constraint(
                        x[cbcs_sid][tid] == 1,
                        f"Faculty Prior Commitment / CBCS: Faculty '{f_name}' must teach shared CBCS subject {cbcs_sid} in {t_label}"
                    )
                    for sid in sids:
                        if sid != cbcs_sid:
                            s_name = subjects_by_id[sid].get("name") or f"Subject {sid}"
                            add_diagnostic_constraint(
                                x[sid][tid] == 0,
                                f"Faculty Clash: Faculty '{f_name}' cannot teach '{s_name}' in {t_label} (busy teaching CBCS)"
                            )
                else:
                    for sid in sids:
                        s_name = subjects_by_id[sid].get("name") or f"Subject {sid}"
                        add_diagnostic_constraint(
                            x[sid][tid] == 0,
                            f"Faculty Prior Commitment: Faculty '{f_name}' is committed elsewhere in {t_label}"
                        )
            else:
                add_diagnostic_constraint(
                    sum(x[sid][tid] for sid in sids) <= 1,
                    f"Faculty Non-Overlap: Faculty '{f_name}' cannot teach multiple subjects in {t_label}"
                )

    # 8. Continuous Blocks & Daily Limits
    for s in subjects:
        sid = s["id"]
        s_name = s.get("name") or f"Subject {sid}"
        continuous_hours = int(s.get("continuous_hours", 1) or 1)
        weekly_hours = int(s.get("weekly_hours"))
        
        if continuous_hours > 1:
            locked_hours = locked_subject_hours.get(sid, 0)
            sessions_needed = max(0, weekly_hours - locked_hours)
            blocks_needed = sessions_needed // continuous_hours if continuous_hours > 0 else 0
            remainder = sessions_needed % continuous_hours if continuous_hours > 0 else 0
            
            if blocks_needed > 0:
                all_block_starts = []
                day_index = 0
                for day, day_slots in slots_by_day.items():
                    m = len(day_slots)
                    k = continuous_hours
                    
                    day_block_starts = []
                    if m >= k:
                        for j in range(m - k + 1):
                            b_var = model.NewBoolVar(f"diag_lab_start_{sid}_d{day_index}_j{j}")
                            day_block_starts.append(b_var)
                            all_block_starts.append(b_var)
                            
                            for offset in range(k):
                                slot_id = day_slots[j + offset]["id"]
                                add_diagnostic_constraint(
                                    x[sid][slot_id] >= b_var,
                                    f"Continuous Lab Block Link: If lab block for '{s_name}' starts at index {j} on {day}, slot {slot_id} must be scheduled"
                                )
                                
                    if day_block_starts:
                        add_diagnostic_constraint(
                            sum(day_block_starts) <= 1,
                            f"Continuous Lab Block: At most one lab block for '{s_name}' can start on {day}"
                        )
                    day_index += 1
                        
                if all_block_starts:
                    add_diagnostic_constraint(
                        sum(all_block_starts) == blocks_needed,
                        f"Continuous Lab Block count: Subject '{s_name}' needs exactly {blocks_needed} consecutive block(s) of size {continuous_hours}"
                    )
                    total_needed = blocks_needed * continuous_hours + remainder
                    if non_locked_slot_ids:
                        add_diagnostic_constraint(
                            sum(x[sid][tid] for tid in non_locked_slot_ids) == total_needed,
                            f"Continuous Lab Hours: Total lab hours for '{s_name}' in non-locked slots must be exactly {total_needed}"
                        )
            
            for day, day_slots in slots_by_day.items():
                add_diagnostic_constraint(
                    sum(x[sid][t["id"]] for t in day_slots) <= continuous_hours,
                    f"Lab Daily Limit: '{s_name}' cannot exceed {continuous_hours} hours on {day}"
                )
        else:
            for day, day_slots in slots_by_day.items():
                add_diagnostic_constraint(
                    sum(x[sid][t["id"]] for t in day_slots) <= len(day_slots),
                    f"Daily upper bound: '{s_name}' on {day}"
                )

    # 9. Solve
    model.AddAssumptions(assumptions)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)
    
    violations = []
    if status == cp_model.INFEASIBLE:
        core = solver.SufficientAssumptionsForInfeasibility()
        for idx in core:
            desc = mapping.get(idx)
            if desc:
                violations.append(desc)
    else:
        violations.append("CP-SAT solver returned INFEASIBLE under strict constraints, but no single constraint subset was identified as the unsat core. Please check for elective group parallel slot constraints or total class capacity.")
        
    return violations
