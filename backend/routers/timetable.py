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
        
        # Get assigned faculty for this section
        eligible_assignments = db.query(models.FacultySubjectAssignment).filter(
            models.FacultySubjectAssignment.subject_id == subject.id
        ).all()
        
        # Filter by section assignment
        section_eligible = []
        for assignment in eligible_assignments:
            # If section_ids is None or empty, faculty is available for all sections
            # Otherwise, check if current section is in the assigned sections
            if assignment.section_ids is None or not assignment.section_ids:
                section_eligible.append(assignment)
            elif request.section_id in assignment.section_ids:
                section_eligible.append(assignment)
        
        assigned_faculty = None
        if section_eligible:
            # Simple Strategy: Pick Random from section-eligible faculty
            assignment = random.choice(section_eligible)
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

@router.post("/generate-all")
def generate_all_timetables(semester: Optional[int] = 3, db: Session = Depends(get_db)):
    """
    Generates timetables for ALL sections across all departments.
    Returns summary of generation results.
    """
    # Fetch all sections
    all_sections = db.query(models.Section).all()
    
    if not all_sections:
        raise HTTPException(status_code=404, detail="No sections found in database")
    
    results = {
        "total": len(all_sections),
        "generated": 0,
        "failed": 0,
        "errors": [],
        "timetables": []
    }
    
    for section in all_sections:
        try:
            # Get department via academic year
            academic_year = section.academic_year
            if not academic_year:
                results["failed"] += 1
                results["errors"].append({
                    "section_id": section.id,
                    "section_name": section.name,
                    "error": "No academic year associated"
                })
                continue
            
            department_id = academic_year.department_id
            
            # Fetch subjects for this department and semester
            subjects = db.query(models.Subject).filter(
                models.Subject.department_id == department_id,
                models.Subject.semester == semester
            ).all()
            
            if not subjects:
                results["failed"] += 1
                results["errors"].append({
                    "section_id": section.id,
                    "section_name": section.name,
                    "error": f"No subjects found for semester {semester}"
                })
                continue
            
            # Delete existing timetable for this section if any
            existing = db.query(models.Timetable).filter(
                models.Timetable.section_id == section.id,
                models.Timetable.semester == semester
            ).first()
            
            if existing:
                # Delete entries first
                db.query(models.TimetableEntry).filter(
                    models.TimetableEntry.timetable_id == existing.id
                ).delete()
                db.delete(existing)
                db.commit()
            
            # Create new timetable
            new_timetable = models.Timetable(
                section_id=section.id,
                semester=semester,
                status="ACTIVE"
            )
            db.add(new_timetable)
            db.commit()
            db.refresh(new_timetable)
            
            # Fetch timeslots
            timeslots = db.query(models.TimeSlot).filter(models.TimeSlot.is_break == False).all()
            
            if not timeslots:
                results["failed"] += 1
                results["errors"].append({
                    "section_id": section.id,
                    "section_name": section.name,
                    "error": "No timeslots available"
                })
                db.delete(new_timetable)
                db.commit()
                continue
            
            # Allocate subjects to timeslots
            allocated_slots = set()
            
            for subject in subjects:
                hours_needed = subject.weekly_hours
                
                # Get faculty assigned to this subject for this section
                eligible_assignments = db.query(models.FacultySubjectAssignment).filter(
                    models.FacultySubjectAssignment.subject_id == subject.id
                ).all()
                
                # Filter by section assignment
                section_eligible = []
                for assignment in eligible_assignments:
                    if assignment.section_ids is None or not assignment.section_ids:
                        section_eligible.append(assignment)
                    elif section.id in assignment.section_ids:
                        section_eligible.append(assignment)
                
                assigned_faculty = None
                if section_eligible:
                    assignment = random.choice(section_eligible)
                    assigned_faculty = db.query(models.Faculty).get(assignment.faculty_id)
                
                # Allocate timeslots
                attempts = 0
                while hours_needed > 0 and attempts < 100:
                    attempts += 1
                    slot = random.choice(timeslots)
                    
                    if slot.id in allocated_slots:
                        continue
                    
                    # Create entry
                    entry = models.TimetableEntry(
                        timetable_id=new_timetable.id,
                        timeslot_id=slot.id,
                        subject_id=subject.id,
                        faculty_id=assigned_faculty.id if assigned_faculty else None
                    )
                    db.add(entry)
                    allocated_slots.add(slot.id)
                    hours_needed -= 1
                    
                    if hours_needed <= 0:
                        break
            
            db.commit()
            
            results["generated"] += 1
            results["timetables"].append({
                "timetable_id": new_timetable.id,
                "section_id": section.id,
                "section_name": section.name,
                "year": academic_year.name
            })
            
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "section_id": section.id,
                "section_name": section.name,
                "error": str(e)
            })
            db.rollback()
            continue
    
    return results

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
