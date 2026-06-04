from typing import List, Dict, Any

def analyze_slot_utilization(
    schedule: List[Dict[str, Any]],
    subjects: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]],
    constraints: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Diagnoses unused slots in the timetable and lists reasons.
    """
    report = []
    
    # 1. Map timeslots used in schedule
    used_slots = {e["timeslot_id"] for e in schedule}
    
    # 2. Get faculty commitments
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

    # 3. Analyze each slot
    for t in timeslots:
        tid = t["id"]
        t_label = t.get("label") or f"{t.get('day')} {t.get('time')}-{t.get('end_time')}"
        is_break = bool(t.get("is_break", False))
        
        reasons = []
        if is_break:
            reasons.append("Marked as Break slot")
            usage_percent = 0
        elif tid in used_slots:
            usage_percent = 100
        else:
            usage_percent = 0
            
            # Faculty unavailability
            busy_faculty = []
            available_faculty = []
            for f in faculty:
                fid = f["id"]
                pfid = parse_fid(fid)
                if tid in fac_prior_slots.get(pfid, set()):
                    busy_faculty.append(f.get("name") or str(fid))
                else:
                    available_faculty.append(f.get("name") or str(fid))
                    
            if busy_faculty and not available_faculty:
                reasons.append("All faculty unavailable due to prior commitments")
            elif busy_faculty:
                reasons.append(f"Faculty unavailable: {', '.join(busy_faculty)}")
                
            # Check total demand vs slots
            total_scheduled_hours = len(schedule)
            # For elective groups, count only the maximum hours in each group
            elective_groups = {}
            for s in subjects:
                if s.get("is_elective"):
                    g_id = str(s.get("elective_group_id") or "").strip()
                    if g_id:
                        elective_groups.setdefault(g_id, []).append(s)
            
            total_required_hours = sum(int(s.get("weekly_hours", 0)) for s in subjects if not s.get("is_elective") or not str(s.get("elective_group_id") or "").strip())
            for g_id, g_subs in elective_groups.items():
                total_required_hours += max(int(s.get("weekly_hours", 0)) for s in g_subs)
                
            if total_scheduled_hours >= total_required_hours:
                reasons.append("All required weekly hours already scheduled")
            else:
                reasons.append("Not scheduled (solver selected other slots due to objective/constraint optimization)")
                
        report.append({
            "slot_id": tid,
            "slot": t_label,
            "usage_percent": usage_percent,
            "unused_reason": reasons
        })
        
    return report
