from typing import List, Dict, Any, Optional
import random

class CSPSolver:
    def __init__(self, subjects: List[Dict], faculty: List[Dict], timeslots: List[Dict], constraints: Optional[Dict] = None, locked_slots: Optional[List[Dict]] = None):
        self.subjects = subjects
        self.faculty = faculty
        self.timeslots = timeslots
        self.assignments = []
        self.constraints = constraints or {}
        self.locked_slots = locked_slots or []
        
    def solve(self):
        schedule = []
        
        # Helper maps
        faculty_availability = {f["id"]: set() for f in self.faculty}
        faculty_hours_count = {f["id"]: 0 for f in self.faculty}
        occupied_slots = set()
        
        # Pre-populate with locked slot constraints
        for locked in self.locked_slots:
            ts_id = locked.get("timeslot_id")
            f_id = locked.get("faculty_id")
            occupied_slots.add(ts_id)
            if f_id and f_id in faculty_availability:
                faculty_availability[f_id].add(ts_id)
                faculty_hours_count[f_id] = faculty_hours_count.get(f_id, 0) + 1
        
        # Track locked subject hours
        locked_subject_hours = {}
        for locked in self.locked_slots:
            sid = locked.get("subject_id")
            if sid:
                locked_subject_hours[sid] = locked_subject_hours.get(sid, 0) + 1
        
        # Load Prior Commitments (Global Constraints)
        prior_commitments = self.constraints.get("prior_commitments", {})
        for fid, slots in prior_commitments.items():
            if int(fid) in faculty_availability:
                for slot_id in slots:
                    faculty_availability[int(fid)].add(slot_id)

        prior_commitment_entries = self.constraints.get("prior_commitment_entries", {})
        faculty_commitment_subjects = {}
        for fid, entries in prior_commitment_entries.items():
            try:
                faculty_id = int(fid)
            except Exception:
                continue
            for entry in entries or []:
                ts_id = entry.get("timeslot_id")
                sid = entry.get("subject_id")
                if ts_id is None:
                    continue
                faculty_commitment_subjects.setdefault(faculty_id, {}).setdefault(ts_id, []).append(sid)

        def can_share_faculty_slot(subject: Dict[str, Any], faculty_id: int, slot_id: int) -> bool:
            if not subject.get("is_cbcs_shared"):
                return False
            subject_id = subject.get("id")
            committed_subject_ids = faculty_commitment_subjects.get(faculty_id, {}).get(slot_id, [])
            if not committed_subject_ids:
                return False
            for committed_subject_id in committed_subject_ids:
                if committed_subject_id != subject_id:
                    return False
            return True


        # Load Preferences (Max Hours)
        faculty_prefs = self.constraints.get("faculty_preferences", {})

        # Separate subjects into Core and Elective Groups
        core_subjects = []
        elective_groups = {}
        for s in self.subjects:
            if s.get("is_elective") and s.get("elective_group_id") is not None:
                gid = s["elective_group_id"]
                if gid not in elective_groups:
                    elective_groups[gid] = []
                elective_groups[gid].append(s)
            else:
                core_subjects.append(s)
        
        # Sort core subjects by remaining sessions needed (High Priority First)
        core_subjects.sort(key=lambda s: s.get("credits", 3) - locked_subject_hours.get(s["id"], 0), reverse=True)

        # 1. Schedule Elective Groups (High Constraint)
        for gid, group_subjects in elective_groups.items():
            # Find max sessions needed in this group
            sessions_needed = max([s.get("credits", 3) - locked_subject_hours.get(s["id"], 0) for s in group_subjects])
            if sessions_needed <= 0:
                continue
            
            slots_by_day = {}
            for slot in self.timeslots:
                if slot["id"] not in occupied_slots:
                    day = slot.get("day", "UnknownDay")
                    if day not in slots_by_day:
                        slots_by_day[day] = []
                    slots_by_day[day].append(slot)
            
            for day in slots_by_day:
                random.shuffle(slots_by_day[day])
                
            days = list(slots_by_day.keys())
            random.shuffle(days)
            assigned_days_count = {day: 0 for day in days}
            max_per_day = 1 if sessions_needed <= len(days) else 2
            
            for _ in range(sessions_needed):
                group_assigned = False
                available_days_sorted = sorted(days, key=lambda d: assigned_days_count[d])
                
                for pass_num in range(3):
                    current_max = max_per_day if pass_num == 0 else 5
                    enforce_max_hours = pass_num < 2
                    
                    for day in available_days_sorted:
                        if assigned_days_count[day] >= current_max:
                            continue
                            
                        for slot in slots_by_day[day]:
                            if slot["id"] in occupied_slots:
                                continue
                            
                            # Check if all faculty in group are available
                            all_faculty_available = True
                            for s in group_subjects:
                                fid = s.get("faculty_id")
                                if fid:
                                    if (
                                        slot["id"] in faculty_availability.get(fid, set())
                                        and not can_share_faculty_slot(s, fid, slot["id"])
                                    ):
                                        all_faculty_available = False
                                        break
                                    
                                    max_h = 18
                                    if str(fid) in faculty_prefs:
                                        max_h = faculty_prefs[str(fid)].get("max_hours", 18)
                                    elif int(fid) in faculty_prefs:
                                        max_h = faculty_prefs[int(fid)].get("max_hours", 18)
                                        
                                    if enforce_max_hours and faculty_hours_count.get(fid, 0) >= max_h:
                                        all_faculty_available = False
                                        break
                            
                            if not all_faculty_available:
                                continue
                                
                            # Assign the whole group to this slot
                            for i, s in enumerate(group_subjects):
                                fid = s.get("faculty_id")
                                
                                schedule.append({
                                    "subject_id": s["id"],
                                    "faculty_id": fid,
                                    "timeslot_id": slot["id"]
                                })
                                
                                if fid:
                                    faculty_availability.setdefault(fid, set()).add(slot["id"])
                                    faculty_hours_count[fid] = faculty_hours_count.get(fid, 0) + 1
                            
                            occupied_slots.add(slot["id"])
                            assigned_days_count[day] += 1
                            group_assigned = True
                            break
                        
                        if group_assigned:
                            break
                    if group_assigned:
                        break
                
                if not group_assigned:
                    sub_names = ", ".join([s.get("name", "Unknown") for s in group_subjects])
                    fac_names = ", ".join([str(s.get("faculty_id")) for s in group_subjects if s.get("faculty_id")])
                    raise ValueError(f"Clash Error: Could not schedule elective group '{gid}' ({sub_names}). Faculty ({fac_names}) are completely booked or clashing at all available slots.")

        # 2. Schedule Core Subjects
        for subject in core_subjects:
            sessions_needed = subject.get("credits", 3) - locked_subject_hours.get(subject["id"], 0)
            if sessions_needed <= 0:
                continue
                
            slots_by_day = {}
            for slot in self.timeslots:
                if slot["id"] not in occupied_slots:
                    day = slot.get("day", "UnknownDay")
                    if day not in slots_by_day:
                        slots_by_day[day] = []
                    slots_by_day[day].append(slot)
            
            for day in slots_by_day:
                random.shuffle(slots_by_day[day])
                
            days = list(slots_by_day.keys())
            random.shuffle(days)
            assigned_days_count = {day: 0 for day in days}
            max_per_day = 1 if sessions_needed <= len(days) else 2
            
            # More aggressive scheduling for core subjects
            for _ in range(sessions_needed):
                session_assigned = False
                available_days_sorted = sorted(days, key=lambda d: assigned_days_count[d])
                
                for pass_num in range(3):
                    current_max = max_per_day if pass_num == 0 else 5
                    enforce_max_hours = pass_num < 2
                    
                    for day in available_days_sorted:
                        if assigned_days_count[day] >= current_max:
                            continue
                            
                        for slot in slots_by_day[day]:
                            if slot["id"] in occupied_slots:
                                continue
                            
                            fid = subject.get("faculty_id")
                            
                            if fid:
                                if (
                                    slot["id"] in faculty_availability.get(fid, set())
                                    and not can_share_faculty_slot(subject, fid, slot["id"])
                                ):
                                     continue
                                
                                max_h = 18
                                if str(fid) in faculty_prefs:
                                    max_h = faculty_prefs[str(fid)].get("max_hours", 18)
                                elif int(fid) in faculty_prefs:
                                    max_h = faculty_prefs[int(fid)].get("max_hours", 18)
                                    
                                if enforce_max_hours and faculty_hours_count.get(fid, 0) >= max_h:
                                    continue
                                 
                            schedule.append({
                                "subject_id": subject["id"],
                                "faculty_id": fid,
                                "timeslot_id": slot["id"]
                            })
                            
                            if fid:
                                 faculty_availability.setdefault(fid, set()).add(slot["id"])
                                 faculty_hours_count[fid] = faculty_hours_count.get(fid, 0) + 1
                            
                            occupied_slots.add(slot["id"])
                            
                            assigned_days_count[day] += 1
                            session_assigned = True
                            
                            if session_assigned:
                                break
                        if session_assigned:
                            break
                    if session_assigned:
                        break
                
                if not session_assigned:
                    sub_name = subject.get("name", "Unknown")
                    fac_id = subject.get("faculty_id")
                    
                    # Try to find faculty name if possible
                    fac_name = str(fac_id)
                    for f in self.faculty:
                        if f["id"] == fac_id:
                            fac_name = f["name"]
                            break
                            
                    sub_names = {s["id"]: s.get("name", "Unknown") for s in self.subjects}
                    counts = {}
                    for entry in schedule:
                        n = sub_names.get(entry["subject_id"], "?")
                        counts[n] = counts.get(n, 0) + 1
                    print("Scheduled counts:", counts)
                    
                    raise ValueError(f"Clash Error: Could not schedule core subject '{sub_name}'. Faculty '{fac_name}' is overbooked or clashing at all available slots.")
                
        return schedule
