from typing import List, Dict, Any, Optional
import random

class CSPSolver:
    def __init__(self, subjects: List[Dict], faculty: List[Dict], rooms: List[Dict], timeslots: List[Dict], constraints: Optional[Dict] = None, locked_slots: Optional[List[Dict]] = None):
        self.subjects = subjects
        self.faculty = faculty
        self.rooms = rooms
        self.timeslots = timeslots
        self.assignments = []
        self.constraints = constraints or {}
        self.locked_slots = locked_slots or []
        
    def solve(self):
        schedule = []
        
        # Helper maps
        faculty_availability = {f["id"]: set() for f in self.faculty}
        room_availability = {r["id"]: set() for r in self.rooms}
        faculty_hours_count = {f["id"]: 0 for f in self.faculty}
        occupied_slots = set()
        
        # Pre-populate with locked slot constraints
        for locked in self.locked_slots:
            ts_id = locked.get("timeslot_id")
            f_id = locked.get("faculty_id")
            r_id = locked.get("room_id")
            occupied_slots.add(ts_id)
            if f_id and f_id in faculty_availability:
                faculty_availability[f_id].add(ts_id)
                faculty_hours_count[f_id] = faculty_hours_count.get(f_id, 0) + 1
            if r_id and r_id in room_availability:
                room_availability[r_id].add(ts_id)
        
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
        
        # Load Preferences (Max Hours)
        faculty_prefs = self.constraints.get("faculty_preferences", {})

        # Separate subjects into Core and Elective Groups
        core_subjects = []
        elective_groups = {}
        for s in self.subjects:
            gid = s.get("elective_group_id")
            if s.get("is_elective") and gid:
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
            
            available_slots = list(self.timeslots)
            random.shuffle(available_slots)
            
            for _ in range(sessions_needed):
                group_assigned = False
                for slot in available_slots:
                    if slot["id"] in occupied_slots:
                        continue
                    
                    # Check if all faculty in group are available
                    all_faculty_available = True
                    for s in group_subjects:
                        fid = s.get("faculty_id")
                        if fid:
                            if slot["id"] in faculty_availability.get(fid, set()):
                                all_faculty_available = False
                                break
                            
                            max_h = 18
                            if str(fid) in faculty_prefs:
                                max_h = faculty_prefs[str(fid)].get("max_hours", 18)
                            elif int(fid) in faculty_prefs:
                                max_h = faculty_prefs[int(fid)].get("max_hours", 18)
                                
                            if faculty_hours_count.get(fid, 0) >= max_h:
                                all_faculty_available = False
                                break
                    
                    if not all_faculty_available:
                        continue
                        
                    # Find distinct rooms for each elective subject in the group
                    available_rooms = [r for r in self.rooms if slot["id"] not in room_availability.get(r["id"], set())]
                    if len(available_rooms) < len(group_subjects):
                        continue
                    
                    # Assign the whole group to this slot
                    for i, s in enumerate(group_subjects):
                        room = available_rooms[i]
                        fid = s.get("faculty_id")
                        
                        schedule.append({
                            "subject_id": s["id"],
                            "faculty_id": fid,
                            "room_id": room["id"],
                            "timeslot_id": slot["id"]
                        })
                        
                        if fid:
                            faculty_availability.setdefault(fid, set()).add(slot["id"])
                            faculty_hours_count[fid] = faculty_hours_count.get(fid, 0) + 1
                        
                        room_availability[room["id"]].add(slot["id"])
                    
                    occupied_slots.add(slot["id"])
                    group_assigned = True
                    break

        # 2. Schedule Core Subjects
        for subject in core_subjects:
            available_slots = list(self.timeslots)
            random.shuffle(available_slots)
            
            sessions_needed = subject.get("credits", 3) - locked_subject_hours.get(subject["id"], 0)
            if sessions_needed <= 0:
                continue
            
            # More aggressive scheduling for core subjects
            for _ in range(sessions_needed):
                session_assigned = False
                for slot in available_slots:
                    # Skip slots already occupied (including those taken by electives)
                    if slot["id"] in occupied_slots:
                        continue
                    
                    for room in self.rooms:
                        fid = subject.get("faculty_id")
                        
                        if fid:
                            if slot["id"] in faculty_availability.get(fid, set()):
                                 continue
                            
                            max_h = 18
                            if str(fid) in faculty_prefs:
                                max_h = faculty_prefs[str(fid)].get("max_hours", 18)
                            elif int(fid) in faculty_prefs:
                                max_h = faculty_prefs[int(fid)].get("max_hours", 18)
                                
                            if faculty_hours_count.get(fid, 0) >= max_h:
                                continue
                            
                        if slot["id"] in room_availability.get(room["id"], set()):
                             continue
                             
                        schedule.append({
                            "subject_id": subject["id"],
                            "faculty_id": fid,
                            "room_id": room["id"],
                            "timeslot_id": slot["id"]
                        })
                        
                        if fid:
                             faculty_availability.setdefault(fid, set()).add(slot["id"])
                             faculty_hours_count[fid] = faculty_hours_count.get(fid, 0) + 1
                        
                        room_availability[room["id"]].add(slot["id"])
                        occupied_slots.add(slot["id"])
                        
                        session_assigned = True
                        break
                    if session_assigned:
                        break
                
        return schedule
