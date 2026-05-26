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
        
        # Initialize timeslots lookup
        self.timeslots_by_id = {t["id"]: t for t in self.timeslots}
        
        # Seeded deterministic random number generator
        seed = self.constraints.get("random_seed")
        if seed is None:
            # Generate a stable seed from subject/faculty IDs if none provided
            combo = "".join(str(s.get("id")) for s in self.subjects) + "".join(str(f.get("id")) for f in self.faculty)
            seed = hash(combo) & 0xffffffff
        else:
            try:
                seed = int(seed)
            except Exception:
                seed = hash(str(seed)) & 0xffffffff
        self.rng = random.Random(seed)

    def _are_consecutive(self, slot1: Dict[str, Any], slot2: Dict[str, Any]) -> bool:
        if slot1.get("day") != slot2.get("day"):
            return False
        t1_start = slot1.get("time") or ""
        t1_end = slot1.get("end_time") or ""
        t2_start = slot2.get("time") or ""
        t2_end = slot2.get("end_time") or ""
        return (t1_end == t2_start) or (t2_end == t1_start)

    def _score_slot(self, subject: Dict[str, Any], slot: Dict[str, Any], current_schedule: List[Dict[str, Any]]) -> float:
        score = 0.0
        
        subject_id = subject["id"]
        faculty_id = subject.get("faculty_id")
        slot_day = slot.get("day")
        slot_time = slot.get("time")
        
        # Get slots assigned to this subject in the current run
        subject_assigned_slots = []
        for entry in current_schedule:
            if entry["subject_id"] == subject_id:
                s_slot = self.timeslots_by_id.get(entry["timeslot_id"])
                if s_slot:
                    subject_assigned_slots.append(s_slot)
                    
        # Get slots assigned to this faculty (prior + current run)
        faculty_assigned_slots = []
        if faculty_id:
            prior_commits = self.constraints.get("prior_commitments", {}).get(faculty_id, [])
            if not prior_commits and str(faculty_id) in self.constraints.get("prior_commitments", {}):
                prior_commits = self.constraints.get("prior_commitments", {}).get(str(faculty_id), [])
            for cid in prior_commits:
                s_slot = self.timeslots_by_id.get(cid)
                if s_slot:
                    faculty_assigned_slots.append(s_slot)
            
            for entry in current_schedule:
                if entry.get("faculty_id") == faculty_id:
                    s_slot = self.timeslots_by_id.get(entry["timeslot_id"])
                    if s_slot:
                        faculty_assigned_slots.append(s_slot)
                        
        # Get all assigned slots in this section (student comfort)
        section_assigned_slots = []
        for entry in current_schedule:
            s_slot = self.timeslots_by_id.get(entry["timeslot_id"])
            if s_slot:
                section_assigned_slots.append(s_slot)
                
        # 1. Subject Spread (Weight: 40)
        # Avoid same subject on the same day if possible
        same_day_count = sum(1 for s in subject_assigned_slots if s.get("day") == slot_day)
        if same_day_count > 0:
            score -= 50.0 * same_day_count
            
        # Avoid consecutive same subject
        for s in subject_assigned_slots:
            if self._are_consecutive(slot, s):
                score -= 100.0
                
        # 2. Period Diversity / Variation (Weight: 20)
        # Avoid same hour pattern across the week
        same_time_count = sum(1 for s in subject_assigned_slots if s.get("time") == slot_time and s.get("day") != slot_day)
        score -= 30.0 * same_time_count
        
        # 3. Faculty Comfort (Weight: 10)
        # Avoid continuous teaching (more than 2 consecutive hours)
        faculty_day_slots = [s for s in faculty_assigned_slots if s.get("day") == slot_day]
        consec_before = 0
        consec_after = 0
        
        current = slot
        while True:
            prev = None
            for fs in faculty_day_slots:
                if fs.get("end_time") == current.get("time"):
                    prev = fs
                    break
            if prev:
                consec_before += 1
                current = prev
            else:
                break
                
        current = slot
        while True:
            nxt = None
            for fs in faculty_day_slots:
                if fs.get("time") == current.get("end_time"):
                    nxt = fs
                    break
            if nxt:
                consec_after += 1
                current = nxt
            else:
                break
                
        total_consec = consec_before + consec_after
        if total_consec >= 2: # means teaching 3 or more periods consecutively (since current adds +1)
            score -= 40.0 * (total_consec - 1)
            
        # Avoid day overload for faculty
        faculty_day_load = len(faculty_day_slots)
        if faculty_day_load > 3:
            score -= 20.0 * (faculty_day_load - 3)
            
        # 4. Student Comfort (Weight: 10)
        # Avoid heavy theory blocks (more than 3 consecutive classes)
        section_day_slots = [s for s in section_assigned_slots if s.get("day") == slot_day]
        consec_student_before = 0
        consec_student_after = 0
        
        current = slot
        while True:
            prev = None
            for ss in section_day_slots:
                if ss.get("end_time") == current.get("time"):
                    prev = ss
                    break
            if prev:
                consec_student_before += 1
                current = prev
            else:
                break
                
        current = slot
        while True:
            nxt = None
            for ss in section_day_slots:
                if ss.get("time") == current.get("end_time"):
                    nxt = ss
                    break
            if nxt:
                consec_student_after += 1
                current = nxt
            else:
                break
                
        total_student_consec = consec_student_before + consec_student_after
        if total_student_consec >= 3:
            score -= 30.0 * (total_student_consec - 2)
            
        # 5. Section Uniqueness (Weight: 20)
        # Add deterministic random tie-breaker perturbation
        score += self.rng.uniform(0.0, 10.0)
        
        return score
        
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
            elif str(fid) in faculty_availability:
                # Support string faculty IDs
                for slot_id in slots:
                    faculty_availability[str(fid)].add(slot_id)
 
        prior_commitment_entries = self.constraints.get("prior_commitment_entries", {})
        faculty_commitment_subjects = {}
        for fid, entries in prior_commitment_entries.items():
            try:
                faculty_id = int(fid)
            except Exception:
                try:
                    faculty_id = str(fid)
                except Exception:
                    continue
            for entry in entries or []:
                ts_id = entry.get("timeslot_id")
                sid = entry.get("subject_id")
                if ts_id is None:
                    continue
                faculty_commitment_subjects.setdefault(faculty_id, {}).setdefault(ts_id, []).append(sid)

        def can_share_faculty_slot(subject: Dict[str, Any], faculty_id: Any, slot_id: int) -> bool:
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
            
            # Shuffle slots deterministically
            for day in slots_by_day:
                self.rng.shuffle(slots_by_day[day])
                
            days = list(slots_by_day.keys())
            self.rng.shuffle(days)
            assigned_days_count = {day: 0 for day in days}
            max_per_day = 1 if sessions_needed <= len(days) else 2
            
            for _ in range(sessions_needed):
                group_assigned = False
                available_days_sorted = sorted(days, key=lambda d: assigned_days_count[d])
                
                for pass_num in range(3):
                    current_max = max_per_day if pass_num == 0 else 5
                    enforce_max_hours = pass_num < 2
                    
                    candidate_slots_with_scores = []
                    
                    for day in available_days_sorted:
                        if assigned_days_count[day] >= current_max:
                            continue
                            
                        for slot in slots_by_day[day]:
                            if slot["id"] in occupied_slots:
                                continue
                            
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
                                
                            slot_score = sum(self._score_slot(s, slot, schedule) for s in group_subjects)
                            candidate_slots_with_scores.append((slot, day, slot_score))
                    
                    if candidate_slots_with_scores:
                        candidate_slots_with_scores.sort(key=lambda x: x[2], reverse=True)
                        best_slot, best_day, best_score = candidate_slots_with_scores[0]
                        
                        for s in group_subjects:
                            fid = s.get("faculty_id")
                            
                            schedule.append({
                                "subject_id": s["id"],
                                "faculty_id": fid,
                                "timeslot_id": best_slot["id"]
                            })
                            
                            if fid:
                                faculty_availability.setdefault(fid, set()).add(best_slot["id"])
                                faculty_hours_count[fid] = faculty_hours_count.get(fid, 0) + 1
                        
                        occupied_slots.add(best_slot["id"])
                        assigned_days_count[best_day] += 1
                        group_assigned = True
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
            
            # Shuffle slots deterministically
            for day in slots_by_day:
                self.rng.shuffle(slots_by_day[day])
                
            days = list(slots_by_day.keys())
            self.rng.shuffle(days)
            assigned_days_count = {day: 0 for day in days}
            max_per_day = 1 if sessions_needed <= len(days) else 2
            
            for _ in range(sessions_needed):
                session_assigned = False
                available_days_sorted = sorted(days, key=lambda d: assigned_days_count[d])
                
                for pass_num in range(3):
                    current_max = max_per_day if pass_num == 0 else 5
                    enforce_max_hours = pass_num < 2
                    
                    candidate_slots_with_scores = []
                    
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
                                 
                            slot_score = self._score_slot(subject, slot, schedule)
                            candidate_slots_with_scores.append((slot, day, slot_score))
                    
                    if candidate_slots_with_scores:
                        candidate_slots_with_scores.sort(key=lambda x: x[2], reverse=True)
                        best_slot, best_day, best_score = candidate_slots_with_scores[0]
                        
                        fid = subject.get("faculty_id")
                        schedule.append({
                            "subject_id": subject["id"],
                            "faculty_id": fid,
                            "timeslot_id": best_slot["id"]
                        })
                        
                        if fid:
                            faculty_availability.setdefault(fid, set()).add(best_slot["id"])
                            faculty_hours_count[fid] = faculty_hours_count.get(fid, 0) + 1
                        
                        occupied_slots.add(best_slot["id"])
                        assigned_days_count[best_day] += 1
                        session_assigned = True
                        break
                
                if not session_assigned:
                    sub_name = subject.get("name", "Unknown")
                    fac_id = subject.get("faculty_id")
                    
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
