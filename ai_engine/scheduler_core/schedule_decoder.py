from typing import List, Dict, Any
from ortools.sat.python import cp_model
from .faculty_pool import subject_faculty_ids

def decode_schedule(
    solver: cp_model.CpSolver,
    x: Dict[int, Dict[int, cp_model.IntVar]],
    subjects: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Decodes CP-SAT solver binary decision variables back into the standard list of 
    timetable entries expected by the backend and database.
    """
    schedule = []
    
    for s in subjects:
        sid = s["id"]
        faculty_ids = subject_faculty_ids(s)
        fid = faculty_ids[0] if faculty_ids else None
        
        for t in timeslots:
            tid = t["id"]
            if solver.Value(x[sid][tid]) == 1:
                entry = {
                    "subject_id": sid,
                    "faculty_id": fid,
                    "timeslot_id": tid
                }
                if len(faculty_ids) > 1:
                    entry["faculty_ids"] = faculty_ids
                schedule.append(entry)
                
    return schedule
