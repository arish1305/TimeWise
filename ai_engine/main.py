import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from scheduler import CSPSolver

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="TimeWise AI scheduler", version="0.1.0")

class OptimizationRequest(BaseModel):
    semester: int
    subjects: List[Dict[str, Any]]
    faculty: List[Dict[str, Any]]
    timeslots: List[Dict[str, Any]]
    constraints: Optional[Dict[str, Any]] = None
    locked_slots: Optional[List[Dict[str, Any]]] = None

@app.post("/optimize")
def optimize_schedule(request: OptimizationRequest):
    max_attempts = 100
    last_error = None
    
    for attempt in range(max_attempts):
        try:
            solver = CSPSolver(
                subjects=request.subjects,
                faculty=request.faculty,
                timeslots=request.timeslots,
                constraints=request.constraints,
                locked_slots=request.locked_slots
            )
            schedule = solver.solve()
            
            if attempt > 0:
                logger.info(f"Successfully generated schedule on attempt {attempt + 1}")
                
            return {"status": "success", "schedule": schedule, "semester": request.semester}
        except ValueError as e:
            last_error = e
            continue
        except Exception as e:
            logger.error(f"AI Engine Error: {e}")
            raise HTTPException(status_code=500, detail="Internal AI Engine Error")
            
    logger.error(f"AI Engine Validation Error after {max_attempts} attempts: {last_error}")
    raise HTTPException(status_code=400, detail=str(last_error))
