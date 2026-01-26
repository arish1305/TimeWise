from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Any
import httpx
import os
import database, models, schemas, auth

router = APIRouter(
    prefix="/timetable",
    tags=["timetable"],
    dependencies=[Depends(auth.get_current_user)]
)

AI_ENGINE_URL = os.getenv("AI_ENGINE_URL", "http://localhost:8001")

@router.post("/generate", response_model=Any)
async def generate_timetable(request: schemas.GenerateTimetableRequest, db: Session = Depends(database.get_db)):
    # 1. Fetch current data state from DB to send to AI (optional, or AI fetches it)
    # For MVP, let's assume we trigger AI and AI might callback or we wait.
    # OR better: We send the constraints and data to AI.
    # Simplest for now: Just hit the AI /generate endpoint.
    
    async with httpx.AsyncClient() as client:
        try:
            # Pass data or just trigger
            response = await client.post(f"{AI_ENGINE_URL}/optimize", json={"semester": request.semester})
            if response.status_code != 200:
                 raise HTTPException(status_code=500, detail=f"AI Engine Error: {response.text}")
            ai_data = response.json()
            return ai_data
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Could not connect to AI Engine: {exc}")

@router.get("/", response_model=List[schemas.Timetable])
def get_timetables(db: Session = Depends(database.get_db)):
    return db.query(models.Timetable).all()
