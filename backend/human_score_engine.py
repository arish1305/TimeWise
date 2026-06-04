import logging
from sqlalchemy.orm import Session
from datetime import time, datetime, timedelta
import models

logger = logging.getLogger(__name__)

HEAVY_SUBJECT_KEYWORDS = [
    "ai", "artificial", "blockchain", "cyber", "security", "cryptography", 
    "machine learning", "deep learning", "compiler", "data structures", 
    "algorithms", "theory of computation", "networks", "dbms", "database"
]

DAY_ORDER = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}

def is_heavy_subject(subject_name: str) -> bool:
    if not subject_name:
        return False
    name_lower = subject_name.lower()
    return any(keyword in name_lower for keyword in HEAVY_SUBJECT_KEYWORDS)

def get_time_difference_minutes(t1: time, t2: time) -> int:
    # Helper to calculate absolute difference in minutes between two time objects
    dt1 = datetime.combine(datetime.today(), t1)
    dt2 = datetime.combine(datetime.today(), t2)
    return abs((dt1 - dt2).total_seconds()) // 60

def score_timetable(timetable: models.Timetable, db: Session, rules: dict = None) -> dict:
    """
    Evaluates a timetable's quality against 'human coordinator' preferences.
    Returns:
        {
            "total_score": float,  # 0 to 100
            "subscores": {
                "subject_spread": float,      # 0 to 25
                "faculty_comfort": float,     # 0 to 20
                "period_diversity": float,    # 0 to 15
                "section_uniqueness": float,  # 0 to 20
                "student_comfort": float      # 0 to 20
            },
            "issues": list[str],
            "repair_candidates": list[dict]
        }
    """
    if rules is None:
        rules = {}

    issues = []
    repair_candidates = []

    # Get all active entries of this timetable
    entries = [e for e in timetable.entries if e.timeslot and not e.timeslot.is_break]
    if not entries:
        return {
            "total_score": 0.0,
            "subscores": {
                "subject_spread": 0.0,
                "faculty_comfort": 0.0,
                "period_diversity": 0.0,
                "section_uniqueness": 0.0,
                "student_comfort": 0.0
            },
            "issues": ["Timetable has no scheduled entries."],
            "repair_candidates": []
        }

    # Retrieve all timeslots for the department to know order/breaks
    dept_id = None
    if timetable.section and timetable.section.academic_year:
        dept_id = timetable.section.academic_year.department_id

    # -------------------------------------------------------------
    # 1. Subject Spread (Max 25 pts)
    # -------------------------------------------------------------
    subject_spread_score = 25.0
    subject_entries = {}
    for entry in entries:
        if entry.subject_id:
            subject_entries.setdefault(entry.subject_id, []).append(entry)

    for subj_id, e_list in subject_entries.items():
        subj = e_list[0].subject
        subj_name = subj.name if subj else f"Subject {subj_id}"
        
        # Group by day
        day_entries = {}
        for entry in e_list:
            day_entries.setdefault(entry.timeslot.day, []).append(entry)

        # Check for clustering on the same day
        for day, d_entries in day_entries.items():
            if len(d_entries) > 1:
                # Sort entries by start_time
                d_entries.sort(key=lambda x: x.timeslot.start_time)
                # Check if they are consecutive (like a lab block or back-to-back theory block)
                # If they are not consecutive, it is a clustering penalty.
                non_consecutive_count = 0
                for i in range(len(d_entries) - 1):
                    t1_end = d_entries[i].timeslot.end_time
                    t2_start = d_entries[i+1].timeslot.start_time
                    if t1_end != t2_start:
                        non_consecutive_count += 1
                
                # Apply penalty if non-consecutive occurrences exist or if total exceeds continuous_hours
                max_continuous = int(subj.continuous_hours or 1) if subj else 1
                if len(d_entries) > max_continuous and non_consecutive_count > 0:
                    subject_spread_score -= 10.0
                    issues.append(f"Subject '{subj_name}' has clustered sessions on {day}.")
                    for entry in d_entries:
                        repair_candidates.append({
                            "entry_id": entry.id,
                            "timeslot_id": entry.timeslot_id,
                            "issue_type": "subject_spread",
                            "subject_id": subj_id
                        })

        # Prefer different days / Check spacing
        unique_days = list(day_entries.keys())
        day_indices = sorted([DAY_ORDER.get(d, 0) for d in unique_days])
        
        # If the subject has multiple classes but they are scheduled on few days
        expected_days = min(len(e_list), 3) # typically spread across up to 3 days
        if len(unique_days) < expected_days and len(e_list) > 1:
            penalty = 5.0 * (expected_days - len(unique_days))
            subject_spread_score -= penalty
            issues.append(f"Subject '{subj_name}' is taught on only {len(unique_days)} days, should spread more.")
            for entry in e_list:
                repair_candidates.append({
                    "entry_id": entry.id,
                    "timeslot_id": entry.timeslot_id,
                    "issue_type": "subject_spread",
                    "subject_id": subj_id
                })

        # Check equal spacing (e.g. gaps of 1 or 2 days are ideal)
        if len(day_indices) > 1:
            gaps = []
            for i in range(len(day_indices) - 1):
                gaps.append(day_indices[i+1] - day_indices[i])
            
            # If standard deviation of gaps is high, or gap is 1 (consecutive days) when we want spacing
            if 1 in gaps and len(e_list) > 2:
                subject_spread_score -= 3.0
                issues.append(f"Subject '{subj_name}' has consecutive day sessions (e.g. Mon & Tue), prefer spacing.")
                for entry in e_list:
                    repair_candidates.append({
                        "entry_id": entry.id,
                        "timeslot_id": entry.timeslot_id,
                        "issue_type": "subject_spread",
                        "subject_id": subj_id
                    })

    subject_spread_score = max(0.0, subject_spread_score)

    # -------------------------------------------------------------
    # 2. Faculty Comfort (Max 20 pts)
    # -------------------------------------------------------------
    faculty_comfort_score = 20.0
    
    # Faculty comfort needs to look at ALL active entries for the faculty in the system
    # but we will focus heavily on current timetable entries, plus query others.
    faculty_ids = set(e.faculty_id for e in entries if e.faculty_id)
    
    # Query all active timetable entries in the DB for these faculty members
    all_faculty_entries = []
    if faculty_ids:
        all_faculty_entries = db.query(models.TimetableEntry).join(models.Timetable).filter(
            models.TimetableEntry.faculty_id.in_(list(faculty_ids)),
            models.Timetable.status != "ARCHIVED"
        ).all()
        
    # Group global entries by faculty and day
    faculty_daily_entries = {}
    for entry in all_faculty_entries:
        if entry.faculty_id and entry.timeslot:
            faculty_daily_entries.setdefault(entry.faculty_id, {}).setdefault(entry.timeslot.day, []).append(entry)

    for fid in faculty_ids:
        fac_entries_by_day = faculty_daily_entries.get(fid, {})
        fac = db.query(models.Faculty).get(fid)
        fac_name = fac.name if fac else f"Faculty {fid}"
        
        daily_loads = []
        for day, f_entries in fac_entries_by_day.items():
            daily_loads.append(len(f_entries))
            # Sort by start time
            f_entries.sort(key=lambda x: x.timeslot.start_time)
            
            # Avoid full day teaching (> 4 periods)
            if len(f_entries) > 4:
                faculty_comfort_score -= 4.0
                issues.append(f"Faculty '{fac_name}' is overloaded with {len(f_entries)} periods on {day}.")
                # Only add candidates that belong to the current timetable to avoid modifying others
                for entry in f_entries:
                    if entry.timetable_id == timetable.id:
                        repair_candidates.append({
                            "entry_id": entry.id,
                            "timeslot_id": entry.timeslot_id,
                            "issue_type": "faculty_comfort",
                            "faculty_id": fid
                        })

            # Check consecutive teaching blocks without break
            consec_count = 1
            for i in range(len(f_entries) - 1):
                t1_end = f_entries[i].timeslot.end_time
                t2_start = f_entries[i+1].timeslot.start_time
                if t1_end == t2_start:
                    consec_count += 1
                else:
                    if consec_count > 2:
                        faculty_comfort_score -= 3.0
                        issues.append(f"Faculty '{fac_name}' has a long back-to-back teaching block of {consec_count} hours on {day}.")
                        for entry in f_entries[i - consec_count + 1 : i + 1]:
                            if entry.timetable_id == timetable.id:
                                repair_candidates.append({
                                    "entry_id": entry.id,
                                    "timeslot_id": entry.timeslot_id,
                                    "issue_type": "faculty_comfort",
                                    "faculty_id": fid
                                })
                    consec_count = 1
            if consec_count > 2:
                faculty_comfort_score -= 3.0
                issues.append(f"Faculty '{fac_name}' has a long back-to-back teaching block of {consec_count} hours on {day}.")
                for entry in f_entries[-consec_count:]:
                    if entry.timetable_id == timetable.id:
                        repair_candidates.append({
                            "entry_id": entry.id,
                            "timeslot_id": entry.timeslot_id,
                            "issue_type": "faculty_comfort",
                            "faculty_id": fid
                        })

            # Avoid isolated single periods / long gaps
            # If there's a gap of > 2 hours between classes
            for i in range(len(f_entries) - 1):
                t1_end = f_entries[i].timeslot.end_time
                t2_start = f_entries[i+1].timeslot.start_time
                gap_minutes = get_time_difference_minutes(t1_end, t2_start)
                # A gap of > 120 minutes is a long wait
                if gap_minutes > 120:
                    faculty_comfort_score -= 3.0
                    issues.append(f"Faculty '{fac_name}' has a long gap of {gap_minutes} minutes between classes on {day}.")
                    for entry in [f_entries[i], f_entries[i+1]]:
                        if entry.timetable_id == timetable.id:
                            repair_candidates.append({
                                "entry_id": entry.id,
                                "timeslot_id": entry.timeslot_id,
                                "issue_type": "faculty_comfort",
                                "faculty_id": fid
                            })

        # Balance week (std deviation of daily loads)
        if len(daily_loads) > 1:
            mean_load = sum(daily_loads) / len(daily_loads)
            variance = sum((x - mean_load) ** 2 for x in daily_loads) / len(daily_loads)
            std_dev = variance ** 0.5
            if std_dev > 1.5:
                faculty_comfort_score -= 2.0
                issues.append(f"Faculty '{fac_name}' has an unbalanced weekly load (teaching concentrated in few days).")

    faculty_comfort_score = max(0.0, faculty_comfort_score)

    # -------------------------------------------------------------
    # 3. Period Diversity (Max 15 pts)
    # -------------------------------------------------------------
    period_diversity_score = 15.0
    
    for subj_id, e_list in subject_entries.items():
        subj = e_list[0].subject
        subj_name = subj.name if subj else f"Subject {subj_id}"
        
        if len(e_list) <= 1:
            continue
            
        start_times = [entry.timeslot.start_time for entry in e_list if entry.timeslot]
        unique_start_times = set(start_times)
        
        # Discourage fixed slots (e.g. DBMS is always at 9:00 AM)
        if len(unique_start_times) == 1:
            period_diversity_score -= 5.0
            issues.append(f"Subject '{subj_name}' is scheduled at the exact same time ({start_times[0]}) on all days.")
            for entry in e_list:
                repair_candidates.append({
                    "entry_id": entry.id,
                    "timeslot_id": entry.timeslot_id,
                    "issue_type": "period_diversity",
                    "subject_id": subj_id
                })
        elif len(unique_start_times) < len(e_list) - 1:
            period_diversity_score -= 2.0
            issues.append(f"Subject '{subj_name}' has repetitive time slots, maximize period diversity.")

    period_diversity_score = max(0.0, period_diversity_score)

    # -------------------------------------------------------------
    # 4. Section Uniqueness (Max 20 pts)
    # -------------------------------------------------------------
    section_uniqueness_score = 20.0
    
    # Query peer timetables in the same semester and academic year
    if timetable.section and timetable.section.academic_year_id:
        peer_timetables = db.query(models.Timetable).join(models.Section).filter(
            models.Timetable.id != timetable.id,
            models.Timetable.semester == timetable.semester,
            models.Timetable.status != "ARCHIVED",
            models.Section.academic_year_id == timetable.section.academic_year_id
        ).all()
        
        if peer_timetables:
            # Build current timetable slot-subject mapping
            curr_slots = {e.timeslot_id: e.subject_id for e in entries if e.subject_id}
            
            for peer in peer_timetables:
                peer_entries = [pe for pe in peer.entries if pe.timeslot and not pe.timeslot.is_break]
                peer_slots = {pe.timeslot_id: pe.subject_id for pe in peer_entries if pe.subject_id}
                
                # Check for copy timetable
                if curr_slots == peer_slots and curr_slots:
                    section_uniqueness_score -= 20.0
                    issues.append(f"Timetable is an identical copy of Section '{peer.section.name if peer.section else peer.section_id}'.")
                    # All current non-locked entries are candidates
                    for entry in entries:
                        if not entry.is_locked:
                            repair_candidates.append({
                                "entry_id": entry.id,
                                "timeslot_id": entry.timeslot_id,
                                "issue_type": "section_uniqueness"
                            })
                    break
                
                # Check for same slot pattern
                total_common_slots = 0
                matching_slots = 0
                for ts_id, s_id in curr_slots.items():
                    if ts_id in peer_slots:
                        total_common_slots += 1
                        if peer_slots[ts_id] == s_id:
                            matching_slots += 1
                            
                if total_common_slots > 0:
                    similarity_ratio = matching_slots / total_common_slots
                    if similarity_ratio > 0.5:
                        deduction = 15.0 * similarity_ratio
                        section_uniqueness_score -= deduction
                        issues.append(f"Timetable has {similarity_ratio:.1%} identical slot pattern with Section '{peer.section.name if peer.section else peer.section_id}'.")
                        for entry in entries:
                            if not entry.is_locked and curr_slots.get(entry.timeslot_id) == peer_slots.get(entry.timeslot_id):
                                repair_candidates.append({
                                    "entry_id": entry.id,
                                    "timeslot_id": entry.timeslot_id,
                                    "issue_type": "section_uniqueness"
                                })

    section_uniqueness_score = max(0.0, section_uniqueness_score)

    # -------------------------------------------------------------
    # 5. Student Comfort (Max 20 pts)
    # -------------------------------------------------------------
    student_comfort_score = 20.0
    
    # Avoid theory blocks (e.g. > 3 hours theory back-to-back without break/lab)
    day_slots = {}
    for entry in entries:
        day_slots.setdefault(entry.timeslot.day, []).append(entry)
        
    for day, d_entries in day_slots.items():
        d_entries.sort(key=lambda x: x.timeslot.start_time)
        
        consec_theory = 0
        for i, entry in enumerate(d_entries):
            # Check if theory
            is_theory = True
            if entry.subject and entry.subject.subject_type == models.SubjectType.LAB:
                is_theory = False
                
            if is_theory:
                consec_theory += 1
                if consec_theory > 3:
                    student_comfort_score -= 4.0
                    issues.append(f"Students have too many consecutive theory classes (> 3 hours) on {day}.")
                    for e in d_entries[i-consec_theory+1 : i+1]:
                        repair_candidates.append({
                            "entry_id": e.id,
                            "timeslot_id": e.timeslot_id,
                            "issue_type": "student_comfort"
                        })
            else:
                consec_theory = 0

        # Avoid difficult subjects together / heavy subjects clustering
        heavy_count = sum(1 for e in d_entries if e.subject and is_heavy_subject(e.subject.name))
        if heavy_count >= 3:
            student_comfort_score -= 5.0
            issues.append(f"Too many difficult subjects clustered on {day} ({heavy_count} heavy courses).")
            for e in d_entries:
                if e.subject and is_heavy_subject(e.subject.name):
                    repair_candidates.append({
                        "entry_id": e.id,
                        "timeslot_id": e.timeslot_id,
                        "issue_type": "student_comfort",
                        "subject_id": e.subject_id
                    })

    student_comfort_score = max(0.0, student_comfort_score)

    # Calculate Total Score
    total_score = (
        subject_spread_score +
        faculty_comfort_score +
        period_diversity_score +
        section_uniqueness_score +
        student_comfort_score
    )

    # Deduplicate repair candidates
    unique_candidates = []
    seen_entry_ids = set()
    for rc in repair_candidates:
        if rc["entry_id"] not in seen_entry_ids:
            seen_entry_ids.add(rc["entry_id"])
            unique_candidates.append(rc)

    return {
        "total_score": round(total_score, 2),
        "subscores": {
            "subject_spread": round(subject_spread_score, 2),
            "faculty_comfort": round(faculty_comfort_score, 2),
            "period_diversity": round(period_diversity_score, 2),
            "section_uniqueness": round(section_uniqueness_score, 2),
            "student_comfort": round(student_comfort_score, 2)
        },
        "issues": issues,
        "repair_candidates": unique_candidates
    }
