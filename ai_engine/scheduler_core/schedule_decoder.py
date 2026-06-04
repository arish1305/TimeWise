from typing import List, Dict, Any
from ortools.sat.python import cp_model

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
        fid = s.get("faculty_id")
        
        for t in timeslots:
            tid = t["id"]
            if solver.Value(x[sid][tid]) == 1:
                schedule.append({
                    "subject_id": sid,
                    "faculty_id": fid,
                    "timeslot_id": tid
                })
                
    return schedule
