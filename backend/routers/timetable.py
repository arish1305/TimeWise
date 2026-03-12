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
    try:
        # 1. Fetch Section
        section = db.query(models.Section).get(request.section_id)
        if not section:
            raise HTTPException(status_code=404, detail="Section not found")
            
        academic_year = section.academic_year
        department_id = academic_year.department_id
        
        # 2. Fetch Subjects
        subjects_db = db.query(models.Subject).filter(
            models.Subject.department_id == department_id,
            models.Subject.semester == request.semester
        ).all()
        
        if not subjects_db:
            raise HTTPException(status_code=400, detail="No subjects found for this Department and Semester")

        # 3. Fetch TimeSlots
        timeslots_db = db.query(models.TimeSlot).filter(models.TimeSlot.is_break == False).all()
        if not timeslots_db:
            raise HTTPException(status_code=400, detail="No time slots defined")

        # 4. Prepare Data for AI Engine
        import os
        import json
        import urllib.request
        import urllib.error
        
        AI_ENGINE_URL = os.getenv("AI_ENGINE_URL", "http://localhost:8001")
        
        # Format Subjects
        subjects_payload = []
        faculty_ids = set()
        for s in subjects_db:
            assigns = db.query(models.FacultySubjectAssignment).filter(
                models.FacultySubjectAssignment.subject_id == s.id
            ).all()
            
            valid_assign = None
            for a in assigns:
                if not a.section_ids or request.section_id in a.section_ids:
                    valid_assign = a
                    break
            
            fid = valid_assign.faculty_id if valid_assign else None
            if fid:
                faculty_ids.add(fid)
                
            # Reduce subject credits by the number of locked manual timeslots
            manual_slots = getattr(s, 'manual_timeslot_ids', []) or []
            remaining_credits = s.weekly_hours - len(manual_slots)
            
            if remaining_credits > 0:
                subjects_payload.append({
                    "id": s.id,
                    "name": s.name,
                    "credits": remaining_credits, 
                    "faculty_id": fid
                })

        # Format Faculty
        faculty_db = db.query(models.Faculty).filter(models.Faculty.id.in_(faculty_ids)).all()
        faculty_payload = [{"id": f.id, "name": f.name} for f in faculty_db]
        
        # Format Rooms
        rooms_db = db.query(models.Room).all()
        rooms_payload = [{"id": r.id, "capacity": r.capacity} for r in rooms_db]
        
        # Format TimeSlots
        timeslots_payload = [{"id": t.id, "day": t.day, "time": str(t.start_time)} for t in timeslots_db]
        
        # 4.1 Fetch Existing Faculty Commitments (Global Constraints)
        # Find all active timetables for the same semester (excluding this section's previous attempts if any)
        # We assume "Active" or even "Draft" in other sections counts as busy to avoid conflicts.
        # Ideally, we should only count "APPROVED" or "ACTIVE" timetables, but for MVP we count all non-active/current.
        
        existing_commitments = {} # {faculty_id: [timeslot_id, ...]}
        faculty_preferences = {}  # {faculty_id: {preferred_slots: ..., max_hours: ...}}
        
        # Get all timetable entries for the involved faculty in the same semester
        if faculty_ids:
            conflicting_entries = db.query(models.TimetableEntry).join(models.Timetable).filter(
                models.Timetable.semester == request.semester,
                models.Timetable.section_id != request.section_id, # Don't count current section
                models.TimetableEntry.faculty_id.in_(faculty_ids)
            ).all()
            
            for entry in conflicting_entries:
                if entry.faculty_id:
                    if entry.faculty_id not in existing_commitments:
                        existing_commitments[entry.faculty_id] = []
                    existing_commitments[entry.faculty_id].append(entry.timeslot_id)
        
        # Populate Preferences
        for f in faculty_db:
             faculty_preferences[f.id] = {
                 "max_hours": f.max_hours_per_week,
                 "preferred_slots": f.preferred_slots # JSON
             }

        payload = {
            "semester": request.semester,
            "subjects": subjects_payload,
            "faculty": faculty_payload,
            "rooms": rooms_payload,
            "timeslots": timeslots_payload,
            "constraints": {
                "prior_commitments": existing_commitments,
                "faculty_preferences": faculty_preferences
            }
        }
        
        # 5. Call AI Engine (with fallback to random allocation)
        schedule = None
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(f"{AI_ENGINE_URL}/optimize", data=data, headers={'Content-Type': 'application/json'})
            
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    result = json.loads(response.read().decode('utf-8'))
                    if result.get("status") == "success":
                        schedule = result.get("schedule", [])
            
        except (urllib.error.URLError, Exception) as e:
            print(f"AI Engine unavailable, falling back to random allocation: {e}")

        # 6. Check for existing locked entries in this section
        existing_tt = db.query(models.Timetable).filter(
            models.Timetable.section_id == request.section_id,
            models.Timetable.semester == request.semester
        ).first()
        
        locked_entries = []
        locked_slot_ids = set()
        if existing_tt:
            locked_entries = db.query(models.TimetableEntry).filter(
                models.TimetableEntry.timetable_id == existing_tt.id,
                models.TimetableEntry.is_locked == True
            ).all()
            locked_slot_ids = {e.timeslot_id for e in locked_entries}
            # Delete only AI entries from existing timetable
            db.query(models.TimetableEntry).filter(
                models.TimetableEntry.timetable_id == existing_tt.id,
                models.TimetableEntry.is_locked == False
            ).delete()
            db.commit()
            # Reuse existing timetable
            new_timetable = existing_tt
            new_timetable.status = "DRAFT"
            db.commit()
        else:
            new_timetable = models.Timetable(
                section_id=request.section_id,
                semester=request.semester,
                status="DRAFT",
                is_active=False
            )
            db.add(new_timetable)
            db.commit()
            db.refresh(new_timetable)
            
        # 6.5 Pre-allocate manual entries from subjects
        for s in subjects_db:
            manual_slots = getattr(s, 'manual_timeslot_ids', []) or []
            if manual_slots:
                # Find eligible faculty for this section
                assigns = db.query(models.FacultySubjectAssignment).filter(
                    models.FacultySubjectAssignment.subject_id == s.id
                ).all()
                fid = None
                for a in assigns:
                    if not a.section_ids or request.section_id in a.section_ids:
                        fid = a.faculty_id
                        break
                
                for timeslot_id in manual_slots:
                    entry = models.TimetableEntry(
                        timetable_id=new_timetable.id,
                        timeslot_id=timeslot_id,
                        subject_id=s.id,
                        faculty_id=fid,
                        room_id=None, # Or assign a default room if needed
                        is_locked=True, # Locked so AI doesn't touch it
                        created_by=models.EntryCreator.ADMIN
                    )
                    db.add(entry)
                    locked_slot_ids.add(timeslot_id)
                    
        db.commit()
        
        if schedule:
            # Use AI Engine schedule
            section_occupied_slots = set(locked_slot_ids)
            for item in schedule:
                if item['timeslot_id'] in section_occupied_slots:
                    continue
                entry = models.TimetableEntry(
                    timetable_id=new_timetable.id,
                    subject_id=item['subject_id'],
                    faculty_id=item.get('faculty_id'),
                    room_id=item.get('room_id'),
                    timeslot_id=item['timeslot_id'],
                    is_locked=False,
                    created_by=models.EntryCreator.AI
                )
                db.add(entry)
                section_occupied_slots.add(item['timeslot_id'])
        else:
            # Fallback: Random allocation (same logic as generate-all)
            rooms_db_all = db.query(models.Room).all()
            default_room = rooms_db_all[0] if rooms_db_all else None
            allocated_slots = set(locked_slot_ids)
            
            # Calculate already-assigned hours per subject from locked entries
            locked_subject_hours = {}
            for le in locked_entries:
                locked_subject_hours[le.subject_id] = locked_subject_hours.get(le.subject_id, 0) + 1
            
            for subject in subjects_db:
                hours_needed = subject.weekly_hours - locked_subject_hours.get(subject.id, 0)
                if hours_needed <= 0:
                    continue
                
                # Get faculty assigned to this subject
                eligible_assignments = db.query(models.FacultySubjectAssignment).filter(
                    models.FacultySubjectAssignment.subject_id == subject.id
                ).all()
                
                section_eligible = []
                for assignment in eligible_assignments:
                    if assignment.section_ids is None or not assignment.section_ids:
                        section_eligible.append(assignment)
                    elif request.section_id in assignment.section_ids:
                        section_eligible.append(assignment)
                
                assigned_faculty = None
                if section_eligible:
                    chosen = random.choice(section_eligible)
                    assigned_faculty = db.query(models.Faculty).get(chosen.faculty_id)
                
                attempts = 0
                while hours_needed > 0 and attempts < 100:
                    attempts += 1
                    slot = random.choice(timeslots_db)
                    
                    if slot.id in allocated_slots:
                        continue
                    
                    entry = models.TimetableEntry(
                        timetable_id=new_timetable.id,
                        timeslot_id=slot.id,
                        subject_id=subject.id,
                        faculty_id=assigned_faculty.id if assigned_faculty else None,
                        room_id=default_room.id if default_room else None,
                        is_locked=False,
                        created_by=models.EntryCreator.AI
                    )
                    db.add(entry)
                    allocated_slots.add(slot.id)
                    hours_needed -= 1
                
        db.commit()
        db.refresh(new_timetable)
        return new_timetable

    except HTTPException:
        raise
    except Exception as e:
        print(f"Server Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
            
            # Pre-allocate manual entries from subjects
            for subject in subjects:
                manual_slots = getattr(subject, 'manual_timeslot_ids', []) or []
                if manual_slots:
                    # Find eligible faculty
                    assigns = db.query(models.FacultySubjectAssignment).filter(
                        models.FacultySubjectAssignment.subject_id == subject.id
                    ).all()
                    fid = None
                    for a in assigns:
                        if not a.section_ids or section.id in a.section_ids:
                            fid = a.faculty_id
                            break
                    
                    for timeslot_id in manual_slots:
                        if timeslot_id not in allocated_slots:
                            entry = models.TimetableEntry(
                                timetable_id=new_timetable.id,
                                timeslot_id=timeslot_id,
                                subject_id=subject.id,
                                faculty_id=fid,
                                is_locked=True,
                                created_by=models.EntryCreator.ADMIN
                            )
                            db.add(entry)
                            allocated_slots.add(timeslot_id)
            db.commit()

            for subject in subjects:
                # To be completely accurate, we subtract hours for the manual slots.
                hours_needed = subject.weekly_hours
                manual_slots = getattr(subject, 'manual_timeslot_ids', []) or []
                hours_needed -= len(manual_slots)
                
                if hours_needed <= 0:
                    continue
                
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
                    
                    if slot.id in allocated_slots or slot.id in (getattr(subject, 'manual_timeslot_ids', []) or []):
                        continue
                    
                    # Create entry
                    entry = models.TimetableEntry(
                        timetable_id=new_timetable.id,
                        timeslot_id=slot.id,
                        subject_id=subject.id,
                        faculty_id=assigned_faculty.id if assigned_faculty else None,
                        is_locked=False,
                        created_by=models.EntryCreator.AI
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



@router.post("/regenerate", response_model=schemas.Timetable)
def regenerate_timetable(request: schemas.RegenerateRequest, db: Session = Depends(get_db)):
    """Delete AI entries and regenerate, keeping locked entries."""
    timetable = db.query(models.Timetable).filter(
        models.Timetable.section_id == request.section_id,
        models.Timetable.semester == request.semester
    ).first()
    
    if not timetable:
        raise HTTPException(status_code=404, detail="No timetable found for this section and semester")
    
    # Delete only AI-generated entries
    db.query(models.TimetableEntry).filter(
        models.TimetableEntry.timetable_id == timetable.id,
        models.TimetableEntry.is_locked == False
    ).delete()
    db.commit()
    
    # Reuse existing generate logic via internal call
    gen_request = schemas.GenerateTimetableRequest(
        section_id=request.section_id,
        semester=request.semester
    )
    return generate_timetable(gen_request, db)

# --- Read Endpoints ---

@router.get("/", response_model=List[schemas.Timetable])
def get_timetables(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.Timetable).offset(skip).limit(limit).all()

@router.get("/{timetable_id}", response_model=schemas.Timetable)
def get_timetable(timetable_id: int, db: Session = Depends(get_db)):
    tt = db.query(models.Timetable).filter(models.Timetable.id == timetable_id).first()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found")
    return tt
