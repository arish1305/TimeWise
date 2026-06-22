import math
from typing import List, Dict, Any
from .faculty_pool import subject_faculty_ids

def calculate_health_metrics(
    schedule: List[Dict[str, Any]], 
    subjects: List[Dict[str, Any]], 
    timeslots: List[Dict[str, Any]], 
    constraints: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculates detailed quality indicators for a timetable and outputs a health score out of 100.
    """
    if not schedule:
        return {
            "health_score": 0.0,
            "faculty_utilization": 0.0,
            "spread_index": 0.0,
            "period_entropy": 0.0,
            "student_load_index": 0.0,
            "section_uniqueness": 0.0
        }
        
    timeslots_by_id = {t["id"]: t for t in timeslots}
    subject_by_id = {s["id"]: s for s in subjects}
    
    # 1. Faculty Utilization
    # Group hours by faculty
    faculty_hours = {}
    for entry in schedule:
        faculty_ids = entry.get("faculty_ids") or subject_faculty_ids(
            subject_by_id.get(entry.get("subject_id"), {})
        )
        for fid in faculty_ids:
            faculty_hours[fid] = faculty_hours.get(fid, 0) + 1
            
    faculty_prefs = constraints.get("faculty_preferences", {}) or {}
    utilization_rates = []
    for fid, hours in faculty_hours.items():
        prefs = faculty_prefs.get(str(fid)) or faculty_prefs.get(fid) or {}
        max_h = float(prefs.get("max_hours", 18) or 18)
        utilization_rates.append(hours / max_h if max_h > 0 else 0.0)
        
    avg_faculty_utilization = sum(utilization_rates) / len(utilization_rates) if utilization_rates else 0.0
    
    # 2. Spread Index
    # Calculate subject spacing against ideal gap using weekly_hours
    days_per_week = len(set(t["day"] for t in timeslots)) or 5
    subject_entries = {}
    for entry in schedule:
        subject_entries.setdefault(entry["subject_id"], []).append(entry)
        
    spread_scores = []
    day_order = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
    
    for sid, entries in subject_entries.items():
        subj = subject_by_id.get(sid, {})
        weekly_hours = float(subj.get("weekly_hours", 3) or 3)
        ideal_gap = days_per_week / weekly_hours if weekly_hours > 0 else 5.0
        
        days_scheduled = sorted([day_order.get(timeslots_by_id[e["timeslot_id"]]["day"].lower(), 0) 
                                for e in entries if e["timeslot_id"] in timeslots_by_id])
        
        if len(days_scheduled) > 1:
            gaps = [days_scheduled[i+1] - days_scheduled[i] for i in range(len(days_scheduled) - 1)]
            avg_gap = sum(gaps) / len(gaps)
            diff = abs(avg_gap - ideal_gap)
            # Normalize to 0-1 (higher is better)
            spread_scores.append(max(0.0, 1.0 - (diff / days_per_week)))
        else:
            spread_scores.append(1.0) # single session is perfectly "spread" by default
            
    avg_spread_index = sum(spread_scores) / len(spread_scores) if spread_scores else 1.0
    
    # 3. Period Entropy
    # Variety of time slots used. Calculate Shannon entropy of timeslot start times
    start_times = [timeslots_by_id[e["timeslot_id"]]["time"] for e in schedule if e["timeslot_id"] in timeslots_by_id]
    total_slots_scheduled = len(start_times)
    
    entropy = 0.0
    if total_slots_scheduled > 0:
        counts = Counter(start_times)
        for time_str, count in counts.items():
            p = count / total_slots_scheduled
            entropy -= p * math.log2(p)
            
    # Max possible entropy is log2(num of unique start times)
    unique_all_start_times = len(set(t["time"] for t in timeslots))
    max_entropy = math.log2(unique_all_start_times) if unique_all_start_times > 1 else 1.0
    period_entropy_index = min(1.0, entropy / max_entropy) if max_entropy > 0 else 0.0
    
    # 4. Student Load Index
    # Standard deviation of student daily session count. We want balanced daily hours.
    daily_session_counts = {}
    for entry in schedule:
        ts = timeslots_by_id.get(entry["timeslot_id"])
        if ts:
            day = ts.get("day")
            daily_session_counts[day] = daily_session_counts.get(day, 0) + 1
            
    # Include days that are completely empty in the week
    all_days = set(t["day"] for t in timeslots)
    for day in all_days:
        if day not in daily_session_counts:
            daily_session_counts[day] = 0
            
    counts_list = list(daily_session_counts.values())
    avg_load = sum(counts_list) / len(counts_list) if counts_list else 0.0
    variance = sum((c - avg_load) ** 2 for c in counts_list) / len(counts_list) if counts_list else 0.0
    std_dev = math.sqrt(variance)
    # Normalize: SD of 0 is perfect load balance (1.0). SD of 3 is poor (0.0).
    student_load_index = max(0.0, 1.0 - (std_dev / 3.0))
    
    # 5. Section Uniqueness
    # Compare with peer timetables
    peer_timetables = constraints.get("peer_timetables", []) or []
    uniqueness_scores = []
    
    curr_slots = {e["timeslot_id"]: e["subject_id"] for e in schedule}
    for peer in peer_timetables:
        peer_entries = peer.get("entries", []) or []
        peer_slots = {pe["timeslot_id"]: pe["subject_id"] for pe in peer_entries}
        
        # Compare overlapping slots
        common_slots = set(curr_slots.keys()).intersection(set(peer_slots.keys()))
        matching = sum(1 for sid in common_slots if curr_slots[sid] == peer_slots[sid])
        
        sim_ratio = matching / len(curr_slots) if curr_slots else 0.0
        uniqueness_scores.append(1.0 - sim_ratio)
        
    avg_uniqueness = sum(uniqueness_scores) / len(uniqueness_scores) if uniqueness_scores else 1.0
    
    # Final Health Score calculation (Weighted average of indices)
    health_score = (
        0.25 * avg_faculty_utilization +
        0.25 * avg_spread_index +
        0.20 * period_entropy_index +
        0.15 * student_load_index +
        0.15 * avg_uniqueness
    ) * 100.0
    
    return {
        "health_score": round(health_score, 2),
        "faculty_utilization": round(avg_faculty_utilization * 100.0, 2),
        "spread_index": round(avg_spread_index * 100.0, 2),
        "period_entropy": round(period_entropy_index * 100.0, 2),
        "student_load_index": round(student_load_index * 100.0, 2),
        "section_uniqueness": round(avg_uniqueness * 100.0, 2)
    }

class Counter(dict):
    """Simple Counter implementation for Python standard library without imports."""
    def __init__(self, iterable):
        super().__init__()
        for item in iterable:
            self[item] = self.get(item, 0) + 1
