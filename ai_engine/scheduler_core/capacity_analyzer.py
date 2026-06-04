import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def analyze_capacity(
    subjects: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]],
    constraints: Dict[str, Any],
    locked_slots: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Performs comprehensive pre-solve capacity checking.
    Raises ValueError if any capacity check fails.
    """
    logger.info("Starting pre-solver capacity analysis...")
    allow_partial_schedule = bool(constraints.get("allow_partial_schedule", False))
    warnings = []
    
    timeslots_by_id = {t["id"]: t for t in timeslots}
    subjects_by_id = {s["id"]: s for s in subjects}
    
    # 1. Break Timeslots
    break_slots = {t["id"] for t in timeslots if t.get("is_break", False)}
    available_slots = len(timeslots) - len(break_slots)
    
    # 2. Locked Slots Feasibility
    locked_hours_by_subject = {}
    locked_slots_used = set()
    locked_slots_by_tid = {}
    locked_slots_for_fac = {} # fid -> set of tids
    
    for ls in locked_slots:
        sid = ls.get("subject_id")
        tid = ls.get("timeslot_id")
        fid = ls.get("faculty_id")
        
        if tid is not None:
            if tid in break_slots:
                raise ValueError(f"Locked Slot Feasibility: Cannot schedule subject {sid} to break slot {tid}")
            if sid is not None:
                locked_hours_by_subject[sid] = locked_hours_by_subject.get(sid, 0) + 1
                locked_slots_used.add(tid)
                locked_slots_by_tid.setdefault(tid, []).append(sid)
            if fid is not None and sid is not None:
                locked_slots_for_fac.setdefault(fid, set()).add(tid)

    # 3. Required Hours & Demand Validation
    non_elective_subjects = []
    elective_groups = {} # group_id -> list of subjects
    
    for s in subjects:
        sid = s["id"]
        weekly_hours = s.get("weekly_hours")
        if weekly_hours is None or int(weekly_hours) <= 0:
            raise ValueError(f"Subject Demand Validation: Subject '{s.get('name', sid)}' (ID={sid}) is missing weekly_hours or has invalid hours <= 0.")
        weekly_hours = int(weekly_hours)
        s["_resolved_weekly_hours"] = weekly_hours
        
        locked_hours = locked_hours_by_subject.get(sid, 0)
        net_hours = max(0, weekly_hours - locked_hours)
        s["_net_hours"] = net_hours
        
        if s.get("is_elective"):
            group_id = str(s.get("elective_group_id") or "").strip()
            if group_id:
                elective_groups.setdefault(group_id, []).append(s)
            else:
                non_elective_subjects.append(s)
        else:
            non_elective_subjects.append(s)

    gross_required_hours = sum(s["_resolved_weekly_hours"] for s in non_elective_subjects)
    for group_id, group_subs in elective_groups.items():
        gross_required_hours += max(s["_resolved_weekly_hours"] for s in group_subs)
        
    net_required_hours = sum(s["_net_hours"] for s in non_elective_subjects)
    for group_id, group_subs in elective_groups.items():
        net_required_hours += max(s["_net_hours"] for s in group_subs)
        
    unique_locked_slots_count = len(locked_slots_used)
    usable_slots = available_slots - unique_locked_slots_count
    
    if net_required_hours > usable_slots:
        message = (
            f"Insufficient timeslots: Net required teaching hours ({net_required_hours}) "
            f"exceed usable slots ({usable_slots}). Total available slots: {available_slots}, "
            f"unique locked slots: {unique_locked_slots_count}."
        )
        if allow_partial_schedule:
            warnings.append(message)
            logger.warning("%s Proceeding because allow_partial_schedule=True.", message)
        else:
            raise ValueError(
                "Insufficient timeslots: Required hours exceed available capacity. "
                f"Net required teaching hours ({net_required_hours}) exceed usable slots ({usable_slots}). "
                f"Total available slots: {available_slots}, unique locked slots: {unique_locked_slots_count}."
            )

    # 4. Faculty Capacity Check
    faculty_prefs = constraints.get("faculty_preferences", {}) or {}
    prior_commitments = constraints.get("prior_commitments", {}) or {}
    
    def parse_fid(f_id):
        try:
            return int(f_id)
        except (ValueError, TypeError):
            return f_id

    fac_prior_slots = {}
    for fid, slots in prior_commitments.items():
        pfid = parse_fid(fid)
        fac_prior_slots.setdefault(pfid, set()).update(slots or [])

    total_fac_capacity = 0
    if faculty:
        for f in faculty:
            fid = f["id"]
            pfid = parse_fid(fid)
            f_name = f.get("name") or f"Faculty {fid}"
            
            prefs = faculty_prefs.get(str(fid)) or faculty_prefs.get(fid) or {}
            max_hours = f.get("max_hours_per_week")
            if max_hours is None:
                max_hours = prefs.get("max_hours", 18)
            max_hours = int(max_hours or 18)
            
            assigned_subjects = [s for s in subjects if s.get("faculty_id") == fid]
            total_assigned_demand = sum(s["_resolved_weekly_hours"] for s in assigned_subjects)
            net_demand_for_fac = sum(s["_net_hours"] for s in assigned_subjects)
            
            prior_slots = fac_prior_slots.get(pfid, set())
            locked_slots_for_fac_ids = locked_slots_for_fac.get(fid, set())
            
            remaining_capacity = max_hours - len(prior_slots) - len(locked_slots_for_fac_ids)
            total_fac_capacity += max(0, remaining_capacity)
            
            slots_allowed_for_fac = {t["id"] for t in timeslots if not t.get("is_break", False)} - prior_slots - (locked_slots_used - locked_slots_for_fac_ids)
            
            if total_assigned_demand > max_hours:
                message = (
                    f"Faculty Overload: Faculty '{f_name}' (ID={fid}) is assigned {total_assigned_demand} hours, "
                    f"which exceeds their maximum workload of {max_hours} hours."
                )
                if allow_partial_schedule and len(locked_slots_for_fac_ids) <= max_hours:
                    warnings.append(message)
                    logger.warning("%s Proceeding with partial fill.", message)
                else:
                    raise ValueError(message)
            if net_demand_for_fac > remaining_capacity:
                message = (
                    f"Faculty Overload: Faculty '{f_name}' (ID={fid}) needs {net_demand_for_fac} more hours, "
                    f"but has a remaining workload capacity of only {remaining_capacity} hours."
                )
                if allow_partial_schedule:
                    warnings.append(message)
                    logger.warning("%s Proceeding with partial fill.", message)
                else:
                    raise ValueError(message)
            if net_demand_for_fac > len(slots_allowed_for_fac):
                message = (
                    f"Faculty Overload: Faculty '{f_name}' (ID={fid}) needs {net_demand_for_fac} hours, "
                    f"but has only {len(slots_allowed_for_fac)} physically available slots."
                )
                if allow_partial_schedule:
                    warnings.append(message)
                    logger.warning("%s Proceeding with partial fill.", message)
                else:
                    raise ValueError(message)

    effective_capacity = min(usable_slots, total_fac_capacity) if faculty else usable_slots

    # 5. Lab Continuity Feasibility
    # Group timeslots by day and check lab block availability
    slots_by_day = {}
    for t in timeslots:
        if not t.get("is_break", False):
            day = t.get("day", "Unknown").lower()
            slots_by_day.setdefault(day, []).append(t)
    for day in slots_by_day:
        slots_by_day[day].sort(key=lambda t: t.get("time") or "")

    for s in subjects:
        continuous_hours = int(s.get("continuous_hours", 1) or 1)
        if continuous_hours > 1:
            s_name = s.get("name") or f"Subject {s['id']}"
            has_valid_day = False
            for day, day_slots in slots_by_day.items():
                full_day_slots = sorted(
                    [t for t in timeslots if t.get("day", "").lower() == day],
                    key=lambda t: t.get("time") or ""
                )
                m = len(full_day_slots)
                k = continuous_hours
                for idx in range(m - k + 1):
                    window = full_day_slots[idx : idx + k]
                    if not any(w.get("is_break", False) for w in window):
                        has_valid_day = True
                        break
                if has_valid_day:
                    break
            if not has_valid_day:
                message = (
                    f"Lab Continuity Feasibility: Subject '{s_name}' requires {continuous_hours} continuous hours, "
                    "but no day has a consecutive block of this size without breaks."
                )
                if allow_partial_schedule:
                    warnings.append(message)
                    logger.warning("%s Proceeding with partial fill; this subject may remain unmet.", message)
                else:
                    raise ValueError(message)

    logger.info(
        "Pre-solver capacity analysis complete: gross_required=%s, net_required=%s, "
        "available_slots=%s, usable_slots=%s, locked_slots=%s, faculty_capacity=%s, "
        "effective_capacity=%s, partial=%s, warnings=%s",
        gross_required_hours,
        net_required_hours,
        available_slots,
        usable_slots,
        unique_locked_slots_count,
        total_fac_capacity,
        effective_capacity,
        allow_partial_schedule,
        len(warnings),
    )
    
    return {
        "status": "PARTIAL_CAPACITY" if warnings else "FEASIBLE",
        "gross_required_hours": gross_required_hours,
        "net_required_hours": net_required_hours,
        "available_slots": available_slots,
        "usable_slots": usable_slots,
        "locked_slot_capacity": unique_locked_slots_count,
        "total_faculty_capacity": total_fac_capacity,
        "effective_capacity": effective_capacity,
        "warnings": warnings
    }
