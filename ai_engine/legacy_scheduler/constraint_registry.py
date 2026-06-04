from typing import Dict, Any, List, Set
from ortools.sat.python import cp_model
import logging

logger = logging.getLogger(__name__)

def register_hard_constraints(
    model: cp_model.CpModel,
    x: Dict[int, Dict[int, cp_model.IntVar]],
    subjects: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]],
    constraints: Dict[str, Any],
    locked_slots: List[Dict[str, Any]],
    elective_groups: Dict[str, List[int]]
):
    """
    Registers all hard scheduling constraints (weekly hours, non-overlap, faculty availability,
    locked slots, CBCS parallel placement, and continuous lab blocks).
    """
    timeslots_by_id = {t["id"]: t for t in timeslots}
    subjects_by_id = {s["id"]: s for s in subjects}
    
    # Sort timeslots by day and start time to group them by day
    # Normalize day to lowercase for consistent grouping
    slots_by_day = {}
    for t in timeslots:
        day = t.get("day", "Unknown").lower()
        slots_by_day.setdefault(day, []).append(t)
    for day in slots_by_day:
        slots_by_day[day].sort(key=lambda t: t.get("time") or "")

    num_days = len(slots_by_day)
    all_slot_ids = [t["id"] for t in timeslots]

    # Group subjects by faculty
    faculty_subjects = {}
    for s in subjects:
        fid = s.get("faculty_id")
        if fid:
            faculty_subjects.setdefault(fid, []).append(s["id"])

    # 1. Locked Slots Constraints
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

    # Enforce locked slots
    for tid, locked_sids in locked_slots_by_tid.items():
        if tid in timeslots_by_id:
            for sid in locked_sids:
                if sid in subjects_by_id:
                    model.Add(x[sid][tid] == 1)
            for other_sid in subjects_by_id:
                if other_sid not in locked_sids:
                    model.Add(x[other_sid][tid] == 0)

    # 1b. Break Timeslots Constraints (Teaching not allowed in break slots)
    for t in timeslots:
        if t.get("is_break", False):
            tid = t["id"]
            for sid in subjects_by_id:
                model.Add(x[sid][tid] == 0)

    non_locked_slot_ids = [t["id"] for t in timeslots if t["id"] not in locked_slots_by_tid]
    available_capacity = len(non_locked_slot_ids)

    # 2. Weekly Hours Complete Constraint
    subject_sessions = {}
    total_demand = 0
    for s in subjects:
        sid = s["id"]
        # Use weekly_hours as primary scheduling demand, falling back to credits
        weekly_hours = s.get("weekly_hours")
        if weekly_hours is None:
            weekly_hours = s.get("credits", 3) or 3
        weekly_hours = int(weekly_hours)
        locked_hours = locked_subject_hours.get(sid, 0)
        needed = max(0, weekly_hours - locked_hours)
        subject_sessions[sid] = needed
        total_demand += needed

    for s in subjects:
        sid = s["id"]
        sessions_needed = subject_sessions[sid]
        
        if non_locked_slot_ids:
            non_locked_sum = sum(x[sid][tid] for tid in non_locked_slot_ids)
            if sessions_needed > 0:
                # Exact matching is enforced. Relaxed/fallback modes are removed completely.
                model.Add(non_locked_sum == sessions_needed)
            else:
                model.Add(non_locked_sum == 0)


    # 3. Section Non-Overlap Constraint
    elective_representatives = {}
    for group_id, sids in elective_groups.items():
        if sids:
            elective_representatives[group_id] = sids[0]

    for t in timeslots:
        tid = t["id"]
        overlap_terms = []
        for s in subjects:
            sid = s["id"]
            is_group_elective = any(sid in sids for sids in elective_groups.values())
            if not is_group_elective:
                overlap_terms.append(x[sid][tid])
                
        for group_rep in elective_representatives.values():
            overlap_terms.append(x[group_rep][tid])
            
        if overlap_terms:
            model.Add(sum(overlap_terms) <= 1)

    # 4. Faculty Non-Overlap & Prior Commitments Constraints
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

    for f in faculty:
        fid = f["id"]
        pfid = parse_fid(fid)
        sids = faculty_subjects.get(fid, [])
        if not sids:
            continue
            
        prefs = faculty_prefs.get(str(fid)) or faculty_prefs.get(fid) or {}
        max_hours = int(prefs.get("max_hours", 18) or 18)
        model.Add(sum(x[sid][tid] for sid in sids for tid in all_slot_ids) <= max_hours)

        for t in timeslots:
            tid = t["id"]
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
                    model.Add(x[cbcs_sid][tid] == 1)
                    for sid in sids:
                        if sid != cbcs_sid:
                            model.Add(x[sid][tid] == 0)
                else:
                    for sid in sids:
                        model.Add(x[sid][tid] == 0)
            else:
                model.Add(sum(x[sid][tid] for sid in sids) <= 1)

    # 5. Continuous Blocks & Daily Limits
    # Use continuous_hours as the primary signal for block scheduling,
    # since users often don't set subject_type correctly.
    for s in subjects:
        sid = s["id"]
        continuous_hours = int(s.get("continuous_hours", 1) or 1)
        credits = int(s.get("credits", 3) or 3)
        
        if continuous_hours > 1:
            # --- Continuous Block Subject (Lab / Project Work / etc.) ---
            locked_hours = locked_subject_hours.get(sid, 0)
            sessions_needed = max(0, credits - locked_hours)
            
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
                            b_var = model.NewBoolVar(f"lab_start_{sid}_d{day_index}_j{j}")
                            day_block_starts.append(b_var)
                            all_block_starts.append(b_var)
                            
                            for offset in range(k):
                                slot_id = day_slots[j + offset]["id"]
                                model.Add(x[sid][slot_id] >= b_var)
                                
                    if day_block_starts:
                        model.Add(sum(day_block_starts) <= 1)
                    
                    day_index += 1
                        
                if all_block_starts:
                    model.Add(sum(all_block_starts) == blocks_needed)
                    
                    total_needed = blocks_needed * continuous_hours + remainder
                    if non_locked_slot_ids:
                        model.Add(sum(x[sid][tid] for tid in non_locked_slot_ids) == total_needed)
            
            # Daily limit for block subjects: allow up to continuous_hours per day
            for day, day_slots in slots_by_day.items():
                model.Add(sum(x[sid][t["id"]] for t in day_slots) <= continuous_hours)
        else:
            # --- Theory / single-hour subject ---
            # NOTE: The daily limit of 2 is a SOFT preference, not a hard constraint.
            # It's handled in objective_registry via penalties. We only add a hard
            # upper bound of slots_per_day to prevent trivial infeasibility.
            for day, day_slots in slots_by_day.items():
                model.Add(sum(x[sid][t["id"]] for t in day_slots) <= len(day_slots))
