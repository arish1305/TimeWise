import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def calculate_complexity(
    subjects: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]],
    constraints: Dict[str, Any],
    locked_slots: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Exposes CP-SAT model complexity statistics by counting variables and constraints.
    """
    num_subjects = len(subjects)
    num_timeslots = len(timeslots)
    
    # Variable Count: subject_id -> timeslot_id -> IntVar
    variable_count = num_subjects * num_timeslots
    
    # 1. Locked & Break Constraints
    break_slots = {t["id"] for t in timeslots if t.get("is_break", False)}
    locked_slots_by_tid = {}
    for ls in locked_slots:
        tid = ls.get("timeslot_id")
        sid = ls.get("subject_id")
        if tid is not None:
            locked_slots_by_tid.setdefault(tid, set())
            if sid:
                locked_slots_by_tid[tid].add(sid)
                
    locked_constraints = 0
    for tid, locked_sids in locked_slots_by_tid.items():
        # Enforce locked slot for locked subjects
        locked_constraints += len(locked_sids)
        # Prevent other subjects from scheduling in this locked slot
        locked_constraints += (num_subjects - len(locked_sids))
        
    # Break timeslots constraints
    locked_constraints += len(break_slots) * num_subjects
    
    # 2. CBCS/Elective Constraints
    elective_groups = {}
    for s in subjects:
        group_id = str(s.get("elective_group_id") or "").strip()
        if s.get("is_elective") and group_id:
            elective_groups.setdefault(group_id, []).append(s["id"])
            
    cbcs_constraints = 0
    for group_id, sids in elective_groups.items():
        if len(sids) > 1:
            # Enforce that all subjects in the group share the same timeslot
            cbcs_constraints += (len(sids) - 1) * num_timeslots
            
    # 3. Faculty Constraints
    faculty_subjects = {}
    for s in subjects:
        fid = s.get("faculty_id")
        if fid:
            faculty_subjects.setdefault(fid, []).append(s["id"])
            
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

    faculty_constraints = 0
    for f in faculty:
        fid = f["id"]
        pfid = parse_fid(fid)
        sids = faculty_subjects.get(fid, [])
        if not sids:
            continue
        # Max hours per faculty
        faculty_constraints += 1
        
        # Non-overlap or prior commitment per slot
        faculty_constraints += num_timeslots
        
        # Additional CBCS/Prior constraints
        for t in timeslots:
            tid = t["id"]
            has_prior = tid in fac_prior_slots.get(pfid, set())
            if has_prior:
                prior_sids = fac_prior_subjects.get(pfid, {}).get(tid, [])
                cbcs_sid = any(s in prior_sids for s in sids)
                if cbcs_sid:
                    # x[cbcs_sid][tid] == 1, plus x[other][tid] == 0 for all other subjects
                    faculty_constraints += len(sids)
                else:
                    # x[sid][tid] == 0 for all subjects
                    faculty_constraints += len(sids)
                    
    # 4. Lab/Continuity Constraints
    slots_by_day = {}
    for t in timeslots:
        day = t.get("day", "Unknown").lower()
        slots_by_day.setdefault(day, []).append(t)
    num_days = len(slots_by_day)
    
    lab_constraints = 0
    for s in subjects:
        sid = s["id"]
        continuous_hours = int(s.get("continuous_hours", 1) or 1)
        weekly_hours = int(s.get("weekly_hours"))
        locked_hours = len([ls for ls in locked_slots if ls.get("subject_id") == sid])
        sessions_needed = max(0, weekly_hours - locked_hours)
        blocks_needed = 1 if sessions_needed >= continuous_hours else 0
        
        if continuous_hours > 1:
            if blocks_needed > 0:
                for day, day_slots in slots_by_day.items():
                    m = len(day_slots)
                    k = continuous_hours
                    if m >= k:
                        # For each possible block window, we add x[sid][slot] >= b_var constraints
                        lab_constraints += (m - k + 1) * k
                    # sum(day_block_starts) <= 1
                    lab_constraints += 1
                # sum(all_block_starts) == blocks_needed
                lab_constraints += 1
                # sum(x) == total_needed
                lab_constraints += 1
            # Daily limit
            lab_constraints += num_days
        else:
            # Daily upper bound limit
            lab_constraints += num_days
            
    # 5. Weekly hours (1 per subject)
    weekly_hours_constraints = num_subjects
    
    # 6. Section Non-Overlap (1 per timeslot)
    section_non_overlap_constraints = num_timeslots
    
    total_constraint_count = (
        locked_constraints +
        cbcs_constraints +
        faculty_constraints +
        lab_constraints +
        weekly_hours_constraints +
        section_non_overlap_constraints
    )
    
    return {
        "variable_count": variable_count,
        "constraint_count": total_constraint_count,
        "faculty_constraints": faculty_constraints,
        "cbcs_constraints": cbcs_constraints,
        "lab_constraints": lab_constraints,
        "spread_constraints": 0, # Evaluated in objective registry as soft penalty
        "locked_constraints": locked_constraints,
        "weekly_hours_constraints": weekly_hours_constraints,
        "section_non_overlap_constraints": section_non_overlap_constraints
    }
