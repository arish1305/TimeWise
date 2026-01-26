from typing import List, Dict, Any, Optional
import random

class CSPSolver:
    def __init__(self, subjects: List[Dict], faculty: List[Dict], rooms: List[Dict], timeslots: List[Dict]):
        self.subjects = subjects
        self.faculty = faculty
        self.rooms = rooms
        self.timeslots = timeslots
        self.assignments = []
        
    def solve(self):
        # Very basic greedy/random allocation for MVP demonstration
        # In a real CSP, we would use backtracking or constraint propagation.
        
        schedule = []
        
        # Helper maps
        faculty_availability = {f["id"]: set() for f in self.faculty} # Set of timeslot_ids
        room_availability = {r["id"]: set() for r in self.rooms}       # Set of timeslot_ids
        
        for subject in self.subjects:
            # Try to find a slot
            assigned = False
            # Shuffle timeslots to randomize
            available_slots = list(self.timeslots)
            random.shuffle(available_slots)
            
            # Simple assumption: 1 subject = 1 slot required (ignoring credits/duration for MVP simplicity if needed, or loop credits)
            sessions_needed = subject.get("credits", 3) # default 3 sessions
            
            for _ in range(sessions_needed):
                # Find a slot for one session
                session_assigned = False
                for slot in available_slots:
                    # Check constraints
                    # 1. Faculty available?
                    # 2. Room available?
                    
                    # For MVP, pick a random room that fits capacity (if we had capacity constraints data)
                    # Let's just pick first available room
                    for room in self.rooms:
                        # Check hard constraints
                        if slot["id"] in faculty_availability.get(subject.get("faculty_id", 0), set()):
                             continue # Faculty busy
                        if slot["id"] in room_availability.get(room["id"], set()):
                             continue # Room busy
                             
                        # Assign
                        schedule.append({
                            "subject_id": subject["id"],
                            "faculty_id": subject.get("faculty_id"), # Assuming subject has faculty assigned or we need to assign
                            "room_id": room["id"],
                            "timeslot_id": slot["id"]
                        })
                        
                        # Update availability
                        # Note: This simple logic doesn't handle "faculty_id" well if not in subject. 
                        # Assuming subject comes with "faculty_id" or we assign one from pool.
                        
                        fid = subject.get("faculty_id")
                        if fid:
                             faculty_availability.setdefault(fid, set()).add(slot["id"])
                        
                        room_availability[room["id"]].add(slot["id"])
                        
                        session_assigned = True
                        break
                    if session_assigned:
                        break
                
        return schedule
