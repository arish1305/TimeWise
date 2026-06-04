from typing import List, Dict, Any

def calculate_similarity(sched1: List[Dict[str, Any]], sched2: List[Dict[str, Any]], timeslots: List[Dict[str, Any]]) -> float:
    """
    Computes a similarity percentage between two schedules based on:
    - Same subject in the same timeslot (40% weight)
    - Same day pattern per subject (30% weight)
    - Same period distribution per subject (30% weight)
    """
    if not sched1 or not sched2:
        return 0.0
        
    timeslots_by_id = {t["id"]: t for t in timeslots}
    
    # 1. Subject Placement Similarity (40% weight)
    # Map slot_id -> subject_id
    slots1 = {e["timeslot_id"]: e["subject_id"] for e in sched1}
    slots2 = {e["timeslot_id"]: e["subject_id"] for e in sched2}
    
    total_slots = set(timeslots_by_id.keys())
    matching_slots = 0
    for sid in total_slots:
        sub1 = slots1.get(sid)
        sub2 = slots2.get(sid)
        if sub1 == sub2:
            matching_slots += 1
            
    subject_placement_sim = (matching_slots / len(total_slots)) if total_slots else 0.0
    
    # Extract unique subjects in both schedules
    all_subjects = set(e["subject_id"] for e in sched1).union(set(e["subject_id"] for e in sched2))
    if not all_subjects:
        return 0.0
        
    # 2. Day Pattern Similarity (30% weight)
    matching_days = 0
    for sub_id in all_subjects:
        days1 = set(timeslots_by_id[e["timeslot_id"]]["day"] for e in sched1 if e["subject_id"] == sub_id and e["timeslot_id"] in timeslots_by_id)
        days2 = set(timeslots_by_id[e["timeslot_id"]]["day"] for e in sched2 if e["subject_id"] == sub_id and e["timeslot_id"] in timeslots_by_id)
        if days1 == days2:
            matching_days += 1
            
    day_pattern_sim = matching_days / len(all_subjects)
    
    # 3. Period Distribution Similarity (30% weight)
    matching_periods = 0
    for sub_id in all_subjects:
        times1 = set(timeslots_by_id[e["timeslot_id"]]["time"] for e in sched1 if e["subject_id"] == sub_id and e["timeslot_id"] in timeslots_by_id)
        times2 = set(timeslots_by_id[e["timeslot_id"]]["time"] for e in sched2 if e["subject_id"] == sub_id and e["timeslot_id"] in timeslots_by_id)
        if times1 == times2:
            matching_periods += 1
            
    period_distribution_sim = matching_periods / len(all_subjects)
    
    # Combine weighted parts
    total_sim_percent = (
        0.40 * subject_placement_sim + 
        0.30 * day_pattern_sim + 
        0.30 * period_distribution_sim
    ) * 100.0
    
    return total_sim_percent

def is_diverse_enough(new_schedule: List[Dict[str, Any]], existing_schedules: List[List[Dict[str, Any]]], timeslots: List[Dict[str, Any]], threshold: float = 80.0) -> bool:
    """
    Returns True if the new schedule is sufficiently diverse from all existing schedules,
    meaning its similarity to any existing schedule is <= threshold.
    """
    for peer in existing_schedules:
        sim = calculate_similarity(new_schedule, peer, timeslots)
        if sim > threshold:
            return False
    return True
