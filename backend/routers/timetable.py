from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import random

from database import get_db
import models
import schemas
import auth

router = APIRouter(
    prefix="/timetables",
    tags=["timetables"],
    dependencies=[Depends(auth.get_current_user)]
)

@router.post("/generate", response_model=schemas.Timetable)
def generate_timetable(request: schemas.GenerateTimetableRequest, db: Session = Depends(get_db)):
    """
    Generates a timetable for a specific Section and Semester.
    1. Fetches Section to confirm existence.
    2. Fetches Subjects for the Department & Semester.
    3. Fetches Faculty assigned to these subjects.
    4. Fetches available TimeSlots (non-break).
    5. Allocates slots ensuring:
       - No double booking of Faculty (in other Active/Draft timetables).
       - No double booking of Section (handled by local constraint).
    """
    
    # 1. Fetch Section
    section = db.query(models.Section).get(request.section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
        
    # Get Department via AcademicYear
    academic_year = section.academic_year
    department_id = academic_year.department_id
    
    # 2. Fetch Subjects
    subjects = db.query(models.Subject).filter(
        models.Subject.department_id == department_id,
        models.Subject.semester == request.semester
    ).all()
    
    if not subjects:
        # Fallback: check if subjects exist at all?
        raise HTTPException(status_code=400, detail="No subjects found for this Department and Semester")

    # 3. Fetch TimeSlots
    timeslots = db.query(models.TimeSlot).filter(models.TimeSlot.is_break == False).all()
    if not timeslots:
        raise HTTPException(status_code=400, detail="No time slots defined")

    # 4. Create new Timetable Record
    new_timetable = models.Timetable(
        section_id=request.section_id,
        semester=request.semester,
        status="DRAFT",
        is_active=False
    )
    db.add(new_timetable)
    db.commit()
    db.refresh(new_timetable)
    
    # 5. Allocation Algorithm
    
    # Helper: Check if faculty is busy
    def is_faculty_busy(faculty_id: int, timeslot_id: int) -> bool:
        # Check against assignments in ACTIVE timetables only.
        return db.query(models.TimetableEntry).join(models.Timetable).filter(
            models.Timetable.is_active == True,
            models.TimetableEntry.timeslot_id == timeslot_id,
            models.TimetableEntry.faculty_id == faculty_id
        ).count() > 0

    section_occupied_slots = set() # (timeslot_id)
    entries = []
    
    # Randomize subject processing order
    alloc_subjects = list(subjects)
    random.shuffle(alloc_subjects)
    
    for subject in alloc_subjects:
        hours_needed = subject.weekly_hours
        
        # Get assigned faculty
        eligible_assignments = db.query(models.FacultySubjectAssignment).filter(
            models.FacultySubjectAssignment.subject_id == subject.id
        ).all()
        
        assigned_faculty = None
        if eligible_assignments:
            # Simple Strategy: Pick Random
            assignment = random.choice(eligible_assignments)
            assigned_faculty = db.query(models.Faculty).get(assignment.faculty_id)
        
        while hours_needed > 0:
            # Candidate slots (all non-break slots)
            slot_candidates = list(timeslots)
            random.shuffle(slot_candidates)
            
            placed = False
            for slot in slot_candidates:
                if slot.id in section_occupied_slots:
                    continue
                
                # Check Faculty Constraint
                if assigned_faculty:
                    if is_faculty_busy(assigned_faculty.id, slot.id):
                        continue
                
                # Assign
                entry = models.TimetableEntry(
                    timetable_id=new_timetable.id,
                    subject_id=subject.id,
                    faculty_id=assigned_faculty.id if assigned_faculty else None,
                    room_id=None,
                    timeslot_id=slot.id
                )
                db.add(entry)
                section_occupied_slots.add(slot.id)
                placed = True
                
                # Decrement needed
                hours_needed -= 1
                break # Move to next hour for this subject
            
            if not placed:
                print(f"Warning: Could not place subject {subject.name} (ID: {subject.id})")
                break # Prevent infinite loop
            
    db.commit()
    db.refresh(new_timetable)
    return new_timetable

@router.get("/", response_model=List[schemas.Timetable])
def get_timetables(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    # Should probably filter by user rights, but for MVP Admin sees all
    return db.query(models.Timetable).offset(skip).limit(limit).all()

@router.get("/{timetable_id}", response_model=schemas.Timetable)
def get_timetable(timetable_id: int, db: Session = Depends(get_db)):
    tt = db.query(models.Timetable).filter(models.Timetable.id == timetable_id).first()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found")
    return tt
