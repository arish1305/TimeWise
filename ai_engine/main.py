from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any
from scheduler import CSPSolver

app = FastAPI(title="TimeWise AI scheduler", version="0.1.0")

class OptimizationRequest(BaseModel):
    semester: int
    # In a real flow, we'd accept full data payload: subjects, rooms, etc.
    # For MVP connected to DB, maybe we fetch or accept them.
    # Let's mock the data for generation if not provided, or accept them.
    # For this task, "Integrate with Backend via API", backend calls this.
    
@app.post("/optimize")
def optimize_schedule(request: OptimizationRequest):
    # Mock data generation for algorithm because backend might not send everything yet
    # In real integration, Backend sends all data.
    
    # Mock Data
    subjects = [
        {"id": 1, "name": "Math", "credits": 3, "faculty_id": 101},
        {"id": 2, "name": "Physics", "credits": 3, "faculty_id": 102},
        {"id": 3, "name": "Chemistry", "credits": 2, "faculty_id": 101}, # Same faculty as Math
    ]
    faculty = [{"id": 101, "name": "Dr. A"}, {"id": 102, "name": "Dr. B"}]
    rooms = [{"id": 201, "capacity": 60}, {"id": 202, "capacity": 60}]
    timeslots = [
        {"id": 1, "day": "Mon", "time": "09:00"},
        {"id": 2, "day": "Mon", "time": "10:00"},
        {"id": 3, "day": "Mon", "time": "11:00"},
        {"id": 4, "day": "Tue", "time": "09:00"},
        {"id": 5, "day": "Tue", "time": "10:00"},
    ]
    
    solver = CSPSolver(subjects, faculty, rooms, timeslots)
    schedule = solver.solve()
    
    return {"status": "success", "schedule": schedule, "semester": request.semester}
