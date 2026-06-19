from typing import Dict, Any, List, Set
from ortools.sat.python import cp_model
import math

def parse_time(time_str: str):
    if not time_str:
        return 0, 0
    try:
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])
    except Exception:
        return 0, 0

def is_morning(time_str: str) -> bool:
    h, m = parse_time(time_str)
    return h < 11

def is_after_lunch(time_str: str) -> bool:
    h, m = parse_time(time_str)
    return h >= 12

def register_objectives(
    model: cp_model.CpModel,
    x: Dict[int, Dict[int, cp_model.IntVar]],
    subjects: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]],
    constraints: Dict[str, Any],
    elective_groups: Dict[str, List[int]]
):
    """
    Formulates and registers the global objective function to maximize timetable quality.
    Weights: spread (35%), faculty comfort (25%), student comfort (15%), period diversity (15%), uniqueness (10%).
    """
    timeslots_by_id = {t["id"]: t for t in timeslots}
    subjects_by_id = {s["id"]: s for s in subjects}
    
    # Group timeslots by day
    slots_by_day = {}
    for t in timeslots:
        day = t.get("day", "Unknown").lower()
        slots_by_day.setdefault(day, []).append(t)
    for day in slots_by_day:
        slots_by_day[day].sort(key=lambda t: t.get("time") or "")

    # Group timeslots by period index (time string)
    unique_start_times = sorted(list(set(t.get("time") or "" for t in timeslots)))
    period_indices = {time_str: idx for idx, time_str in enumerate(unique_start_times)}

    # Group subjects by faculty
    faculty_subjects = {}
    for s in subjects:
        fid = s.get("faculty_id")
        if fid:
            faculty_subjects.setdefault(fid, []).append(s["id"])

    # Extract rules/overrides
    rules = constraints.get("rules", {}) or {}
    custom_weights = rules.get("custom_weights", {}) or {}
    
    # Default weights scaled
    w_spread = int(custom_weights.get("spread", 35) * 100)
    w_faculty = int(custom_weights.get("faculty", 25) * 100)
    w_student = int(custom_weights.get("student", 15) * 100)
    w_period = int(custom_weights.get("period", 15) * 100)
    w_uniqueness = int(custom_weights.get("uniqueness", 10) * 100)
    w_preferred_slot = int(custom_weights.get("preferred_slot", 5) * 100)

    objective_terms = []

    def parse_fid(f_id):
        try:
            return int(f_id)
        except (ValueError, TypeError):
            return f_id

    def parse_slot_id(slot_id):
        try:
            return int(slot_id)
        except (ValueError, TypeError):
            return slot_id

    def collect_preferred_slots(fid):
        preferred_slots = set()
        faculty_availability = constraints.get("faculty_availability", {}) or {}
        faculty_preferences = constraints.get("faculty_preferences", {}) or {}

        for source in (faculty_availability, faculty_preferences):
            config = None
            if isinstance(source, dict):
                config = source.get(fid) or source.get(str(fid))
            elif isinstance(source, list):
                config = next(
                    (item for item in source if isinstance(item, dict) and parse_fid(item.get("faculty_id")) == fid),
                    None,
                )

            if not isinstance(config, dict):
                continue
            raw_slots = config.get("preferred_slots") or []
            if isinstance(raw_slots, list):
                preferred_slots.update(parse_slot_id(slot_id) for slot_id in raw_slots)

        return preferred_slots

    # 1. Subject Spread (35% weight)
    for s in subjects:
        sid = s["id"]
        continuous_hours = int(s.get("continuous_hours", 1) or 1)
        
        for day, day_slots in slots_by_day.items():
            day_active = model.NewBoolVar(f"day_active_{sid}_{day}")
            # day_active is 1 if subject is scheduled on this day
            for t in day_slots:
                model.Add(day_active >= x[sid][t["id"]])
            # Upper bound: day_active can only be 1 if at least one slot on this day is active
            model.Add(day_active <= sum(x[sid][t["id"]] for t in day_slots))
                
            mult = 2 if continuous_hours == 1 else 1
            objective_terms.append(day_active * w_spread * mult)

    # 1b. Soft daily limit penalty for single-hour subjects
    # Penalise scheduling more than 2 hours of the same theory subject on one day.
    for s in subjects:
        sid = s["id"]
        continuous_hours = int(s.get("continuous_hours", 1) or 1)
        if continuous_hours > 1:
            continue  # block subjects handle their own daily limit as hard constraint
        
        for day, day_slots in slots_by_day.items():
            day_sum = sum(x[sid][t["id"]] for t in day_slots)
            # Penalise if scheduled > 2 times on this day
            excess = model.NewIntVar(0, len(day_slots), f"excess_{sid}_{day}")
            model.Add(excess >= day_sum - 2)
            model.Add(excess >= 0)
            objective_terms.append(excess * (-w_spread * 5))  # strong penalty

    # 2. Faculty Comfort (25% weight)
    faculty_prefs = constraints.get("faculty_preferences", {}) or {}
    for f in faculty:
        fid = f["id"]
        sids = faculty_subjects.get(fid, [])
        if not sids:
            continue
            
        prefs = faculty_prefs.get(str(fid)) or faculty_prefs.get(fid) or {}
        avoid_morning = prefs.get("avoid_morning", False)
        avoid_last_hour = prefs.get("avoid_last_hour", False)
        compact_schedule = prefs.get("compact_schedule", True)

        for day, day_slots in slots_by_day.items():
            m = len(day_slots)
            
            # Faculty daily active variables
            active_vars = []
            for t in day_slots:
                tid = t["id"]
                t_active = model.NewBoolVar(f"fac_active_{fid}_{tid}")
                model.Add(t_active == sum(x[sid][tid] for sid in sids))
                active_vars.append(t_active)

            # Avoid Morning Penalty
            if avoid_morning:
                for idx, t in enumerate(day_slots):
                    if is_morning(t.get("time")):
                        objective_terms.append(active_vars[idx] * (-w_faculty))

            # Avoid Last Hour Penalty
            if avoid_last_hour and m > 0:
                objective_terms.append(active_vars[-1] * (-w_faculty))

            # Compactness / Consecutive Teaching Bonus
            if compact_schedule and m > 1:
                for idx in range(m - 1):
                    consec = model.NewBoolVar(f"fac_consec_{fid}_{day}_{idx}")
                    model.Add(consec <= active_vars[idx])
                    model.Add(consec <= active_vars[idx + 1])
                    objective_terms.append(consec * w_faculty)

        for tid in collect_preferred_slots(parse_fid(fid)):
            for sid in sids:
                if tid in x[sid]:
                    objective_terms.append(x[sid][tid] * w_preferred_slot)

    # 3. Student Comfort (15% weight)
    max_load = model.NewIntVar(0, len(timeslots), "max_load")
    min_load = model.NewIntVar(0, len(timeslots), "min_load")

    for day, day_slots in slots_by_day.items():
        daily_load = sum(x[sid][t["id"]] for s in subjects for sid in [s["id"]] for t in day_slots)
        model.Add(max_load >= daily_load)
        model.Add(min_load <= daily_load)

    objective_terms.append((min_load - max_load) * w_student * 2)

    theory_sids = [s["id"] for s in subjects if s.get("subject_type", "THEORY").upper() == "THEORY"]
    if theory_sids:
        for day, day_slots in slots_by_day.items():
            m = len(day_slots)
            if m >= 3:
                for idx in range(m - 2):
                    overload = model.NewBoolVar(f"theory_overload_{day}_{idx}")
                    slots_to_check = [day_slots[idx]["id"], day_slots[idx+1]["id"], day_slots[idx+2]["id"]]
                    model.Add(sum(x[sid][tid] for sid in theory_sids for tid in slots_to_check) <= 2 + overload)
                    objective_terms.append(overload * (-w_student * 3))

    # 4. Period Diversity (15% weight)
    for s in subjects:
        sid = s["id"]
        sub_type = s.get("subject_type", "THEORY").upper()
        if sub_type != "THEORY":
            continue
            
        for time_str, p_idx in period_indices.items():
            period_active = model.NewBoolVar(f"period_active_{sid}_{p_idx}")
            p_slots = [t["id"] for t in timeslots if t.get("time") == time_str]
            for tid in p_slots:
                model.Add(period_active >= x[sid][tid])
            # Upper bound: period_active can only be 1 if scheduled in this period on at least one day
            model.Add(period_active <= sum(x[sid][tid] for tid in p_slots))
                
            objective_terms.append(period_active * w_period)

    # 5. Section Uniqueness (10% weight)
    peer_timetables = constraints.get("peer_timetables", []) or []
    for peer in peer_timetables:
        peer_entries = peer.get("entries", []) or []
        seen_pairs = set()
        for pe in peer_entries:
            tid = pe.get("timeslot_id")
            sid = pe.get("subject_id")
            pair = (sid, tid)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            if tid in timeslots_by_id and sid in x:
                objective_terms.append(x[sid][tid] * (-w_uniqueness * 4))

                peer_slot = timeslots_by_id.get(tid, {})
                peer_day = pe.get("day") or peer_slot.get("day")
                peer_time = pe.get("time") or peer_slot.get("time")

                if peer_day:
                    same_day_slots = [
                        slot["id"]
                        for slot in timeslots
                        if slot.get("day") == peer_day and slot["id"] != tid
                    ]
                    for same_day_tid in same_day_slots:
                        if same_day_tid in x[sid]:
                            objective_terms.append(x[sid][same_day_tid] * (-w_uniqueness))

                if peer_time:
                    same_period_slots = [
                        slot["id"]
                        for slot in timeslots
                        if slot.get("time") == peer_time and slot["id"] != tid
                    ]
                    for same_period_tid in same_period_slots:
                        if same_period_tid in x[sid]:
                            objective_terms.append(x[sid][same_period_tid] * (-w_uniqueness * 2))

    # 6. Fill bonus — reward each scheduled session to maximize coverage
    w_fill = int(custom_weights.get("fill", 10000) * 100)
    for s in subjects:
        sid = s["id"]
        for t in timeslots:
            tid = t["id"]
            objective_terms.append(x[sid][tid] * w_fill)

    model.Maximize(sum(objective_terms))

def evaluate_solution_subscores(
    solver: cp_model.CpSolver,
    x: Dict[int, Dict[int, cp_model.IntVar]],
    subjects: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]],
    constraints: Dict[str, Any]
) -> Dict[str, float]:
    timeslots_by_id = {t["id"]: t for t in timeslots}
    
    slots_by_day = {}
    for t in timeslots:
        day = t.get("day", "Unknown").lower()
        slots_by_day.setdefault(day, []).append(t)
    for day in slots_by_day:
        slots_by_day[day].sort(key=lambda t: t.get("time") or "")

    unique_start_times = sorted(list(set(t.get("time") or "" for t in timeslots)))
    period_indices = {time_str: idx for idx, time_str in enumerate(unique_start_times)}

    faculty_subjects = {}
    for s in subjects:
        fid = s.get("faculty_id")
        if fid:
            faculty_subjects.setdefault(fid, []).append(s["id"])

    spread_points = 0
    max_spread_points = 0
    for s in subjects:
        sid = s["id"]
        sub_type = s.get("subject_type", "THEORY").upper()
        mult = 2 if sub_type == "THEORY" else 1
        
        for day, day_slots in slots_by_day.items():
            max_spread_points += mult
            day_active = any(solver.Value(x[sid][t["id"]]) == 1 for t in day_slots)
            if day_active:
                spread_points += mult
    spread_subscore = (spread_points / max_spread_points * 100) if max_spread_points > 0 else 100.0

    faculty_prefs = constraints.get("faculty_preferences", {}) or {}
    fac_violations = 0
    fac_opportunities = 0
    
    for f in faculty:
        fid = f["id"]
        sids = faculty_subjects.get(fid, [])
        if not sids:
            continue
            
        prefs = faculty_prefs.get(str(fid)) or faculty_prefs.get(fid) or {}
        avoid_morning = prefs.get("avoid_morning", False)
        avoid_last_hour = prefs.get("avoid_last_hour", False)
        compact_schedule = prefs.get("compact_schedule", True)

        for day, day_slots in slots_by_day.items():
            m = len(day_slots)
            day_active = [any(solver.Value(x[sid][t["id"]]) == 1 for sid in sids) for t in day_slots]
            
            if avoid_morning:
                for idx, t in enumerate(day_slots):
                    if is_morning(t.get("time")):
                        fac_opportunities += 1
                        if day_active[idx]:
                            fac_violations += 1
                            
            if avoid_last_hour and m > 0:
                fac_opportunities += 1
                if day_active[-1]:
                    fac_violations += 1
                    
            if compact_schedule and m > 1:
                active_indices = [idx for idx, active in enumerate(day_active) if active]
                if len(active_indices) > 1:
                    first = active_indices[0]
                    last = active_indices[-1]
                    fac_opportunities += (last - first - 1)
                    for idx in range(first + 1, last):
                        if not day_active[idx]:
                            fac_violations += 1

    fac_subscore = max(0.0, 100.0 - (fac_violations / fac_opportunities * 100)) if fac_opportunities > 0 else 100.0

    daily_loads = []
    overload_count = 0
    theory_sids = [s["id"] for s in subjects if s.get("subject_type", "THEORY").upper() == "THEORY"]
    
    for day, day_slots in slots_by_day.items():
        daily_load = sum(solver.Value(x[sid][t["id"]]) for s in subjects for sid in [s["id"]] for t in day_slots)
        daily_loads.append(daily_load)
        
        m = len(day_slots)
        if m >= 3 and theory_sids:
            day_active = [any(solver.Value(x[sid][t["id"]]) == 1 for sid in theory_sids) for t in day_slots]
            for idx in range(m - 2):
                if day_active[idx] and day_active[idx+1] and day_active[idx+2]:
                    overload_count += 1

    if daily_loads:
        max_load_val = max(daily_loads)
        min_load_val = min(daily_loads)
        load_diff = max_load_val - min_load_val
    else:
        load_diff = 0
        
    student_score_base = 100.0 - (load_diff * 10) - (overload_count * 15)
    student_subscore = max(0.0, min(100.0, student_score_base))

    period_points = 0
    max_period_points = 0
    for s in subjects:
        sid = s["id"]
        sub_type = s.get("subject_type", "THEORY").upper()
        if sub_type != "THEORY":
            continue
            
        for time_str, p_idx in period_indices.items():
            max_period_points += 1
            p_slots = [t["id"] for t in timeslots if t.get("time") == time_str]
            is_active = any(solver.Value(x[sid][tid]) == 1 for tid in p_slots)
            if is_active:
                period_points += 1
    period_subscore = (period_points / max_period_points * 100) if max_period_points > 0 else 100.0

    peer_timetables = constraints.get("peer_timetables", []) or []
    matches = 0
    total_slots_peer = 0
    for peer in peer_timetables:
        peer_entries = peer.get("entries", []) or []
        for pe in peer_entries:
            tid = pe.get("timeslot_id")
            sid = pe.get("subject_id")
            if tid in timeslots_by_id and sid in x:
                total_slots_peer += 1
                if solver.Value(x[sid][tid]) == 1:
                    matches += 1
                    
    uniqueness_subscore = max(0.0, 100.0 - (matches / total_slots_peer * 100)) if total_slots_peer > 0 else 100.0

    return {
        "spread": round(spread_subscore, 2),
        "faculty": round(fac_subscore, 2),
        "student": round(student_subscore, 2),
        "period": round(period_subscore, 2),
        "uniqueness": round(uniqueness_subscore, 2)
    }
