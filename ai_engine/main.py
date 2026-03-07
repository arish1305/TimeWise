from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from scheduler import CSPSolver

app = FastAPI(title="TimeWise AI scheduler", version="0.1.0")

class OptimizationRequest(BaseModel):
    semester: int
    subjects: List[Dict[str, Any]]
    faculty: List[Dict[str, Any]]
    rooms: List[Dict[str, Any]]
    timeslots: List[Dict[str, Any]]
    # Optional constraints
    constraints: Optional[Dict[str, Any]] = None

@app.post("/optimize")
def optimize_schedule(request: OptimizationRequest):
    try:
        # Use real data from request
        solver = CSPSolver(
            subjects=request.subjects,
            faculty=request.faculty,
            rooms=request.rooms,
            timeslots=request.timeslots,
            constraints=request.constraints
        )
        schedule = solver.solve()
        
        return {"status": "success", "schedule": schedule, "semester": request.semester}
    except Exception as e:
        print(f"AI Engine Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
