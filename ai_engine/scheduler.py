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
        
        # Track locked subject hours to reduce remaining credits
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
        
        for subject in self.subjects:
            available_slots = list(self.timeslots)
            random.shuffle(available_slots)
            
            sessions_needed = subject.get("credits", 3) - locked_subject_hours.get(subject["id"], 0)
            if sessions_needed <= 0:
                continue
            
            for _ in range(sessions_needed):
                session_assigned = False
                for slot in available_slots:
                    # Skip slots already occupied (including locked)
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
