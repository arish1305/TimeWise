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
        
        # 2. Fetch Subjects (Primary Department OR Shared allowed_department_ids)
        all_subjects_for_sem = db.query(models.Subject).filter(
            models.Subject.semester == request.semester
        ).all()
        
        subjects_db = []
        for s in all_subjects_for_sem:
            is_primary = s.department_id == department_id
            allowed_depts = getattr(s, 'allowed_department_ids', []) or []
            is_shared = department_id in allowed_depts
            
            if is_primary or is_shared:
                subjects_db.append(s)
        
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
        
        # 4. Initialize Timetable and Locked Slots Early
        existing_tt = db.query(models.Timetable).filter(
            models.Timetable.section_id == request.section_id,
            models.Timetable.semester == request.semester
        ).first()
        
        locked_slot_ids = set()
        locked_slots_payload = []

        if existing_tt:
            # Fetch existing locked entries (Manual Locks from UI)
            locked_entries = db.query(models.TimetableEntry).filter(
                models.TimetableEntry.timetable_id == existing_tt.id,
                models.TimetableEntry.is_locked == True
            ).all()
            for e in locked_entries:
                locked_slot_ids.add(e.timeslot_id)
                locked_slots_payload.append({
                    "subject_id": e.subject_id,
                    "faculty_id": e.faculty_id,
                    "room_id": e.room_id,
                    "timeslot_id": e.timeslot_id
                })

            # Delete only AI entries to refresh generation
            db.query(models.TimetableEntry).filter(
                models.TimetableEntry.timetable_id == existing_tt.id,
                models.TimetableEntry.is_locked == False
            ).delete()
            db.commit()
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

        # Sync manual slots from Subject definitions
        for s in subjects_db:
            m_slots = getattr(s, 'manual_timeslot_ids', []) or []
            if m_slots:
                # Find faculty for this section
                a_list = db.query(models.FacultySubjectAssignment).filter(
                    models.FacultySubjectAssignment.subject_id == s.id
                ).all()
                f_id = None
                for a in a_list:
                    if not a.section_ids or request.section_id in a.section_ids:
                        f_id = a.faculty_id
                        break
                
                for ts_id in m_slots:
                    if ts_id not in locked_slot_ids:
                        # Add to DB as locked entry
                        entry = models.TimetableEntry(
                            timetable_id=new_timetable.id,
                            timeslot_id=ts_id,
                            subject_id=s.id,
                            faculty_id=f_id,
                            is_locked=True,
                            created_by=models.EntryCreator.ADMIN
                        )
                        db.add(entry)
                        locked_slot_ids.add(ts_id)
                        locked_slots_payload.append({
                            "subject_id": s.id,
                            "faculty_id": f_id,
                            "room_id": None,
                            "timeslot_id": ts_id
                        })
        db.commit()

        # 5. Prepare Data for AI Engine
        AI_ENGINE_URL = os.getenv("AI_ENGINE_URL", "http://localhost:8001")
        
        subjects_payload = []
        faculty_ids = set()
        for s in subjects_db:
            assigns = db.query(models.FacultySubjectAssignment).filter(
                models.FacultySubjectAssignment.subject_id == s.id
            ).all()
            
            section_eligible_assigns = [a for a in assigns if not a.section_ids or request.section_id in a.section_ids]
            fid = section_eligible_assigns[0].faculty_id if section_eligible_assigns else None
            if fid: faculty_ids.add(fid)
                
            # Send TOTAL weekly hours; AI engine will handle subtraction of locked sessions
            subjects_payload.append({
                "id": s.id,
                "name": s.name,
                "credits": s.weekly_hours, 
                "faculty_id": fid,
                "is_elective": s.is_elective,
                "elective_group_id": s.elective_group_id
            })

        faculty_db = db.query(models.Faculty).filter(models.Faculty.id.in_(faculty_ids)).all()
        faculty_payload = [{"id": f.id, "name": f.name} for f in faculty_db]
        rooms_payload = [{"id": r.id, "capacity": r.capacity} for r in db.query(models.Room).all()]
        timeslots_payload = [{"id": t.id, "day": t.day, "time": str(t.start_time)} for t in timeslots_db]
        
        # Fetch commitments/preferences
        existing_commitments = {}
        if faculty_ids:
            conflicting_entries = db.query(models.TimetableEntry).join(models.Timetable).filter(
                models.Timetable.semester == request.semester,
                models.Timetable.section_id != request.section_id,
                models.TimetableEntry.faculty_id.in_(faculty_ids)
            ).all()
            for e in conflicting_entries:
                if e.faculty_id:
                    existing_commitments.setdefault(e.faculty_id, []).append(e.timeslot_id)
        
        faculty_preferences = {f.id: {"max_hours": f.max_hours_per_week, "preferred_slots": f.preferred_slots} for f in faculty_db}

        payload = {
            "semester": request.semester,
            "subjects": subjects_payload,
            "faculty": faculty_payload,
            "rooms": rooms_payload,
            "timeslots": timeslots_payload,
            "locked_slots": locked_slots_payload,
            "constraints": {
                "prior_commitments": existing_commitments,
                "faculty_preferences": faculty_preferences
            }
        }
        # 6. Call AI Engine (with fallback to random allocation)
        import json
        import urllib.request
        import urllib.error
        
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

        if schedule:
            # Use AI Engine schedule
            section_occupied_slots = set(locked_slot_ids)
            for item in schedule:
                # Check if this subject is an elective to allow parallel slotting
                # IMPORTANT: Only group if it is an elective AND has a group ID
                sub_obj = db.query(models.Subject).get(item['subject_id'])
                is_el = (sub_obj.is_elective and sub_obj.elective_group_id) if sub_obj else False
                
                if not is_el and item['timeslot_id'] in section_occupied_slots:
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
                
                # If it's a core subject, mark the slot as strictly occupied
                if not is_el:
                    section_occupied_slots.add(item['timeslot_id'])
        else:
            # Fallback: Random allocation (same logic as generate-all)
            rooms_db_all = db.query(models.Room).all()
            default_room = rooms_db_all[0] if rooms_db_all else None
            # Fallback Logic with CBCS support
            core_subjects = []
            elective_groups = {}
            for s in subjects_db:
                if s.is_elective and s.elective_group_id:
                    gid = s.elective_group_id
                    if gid not in elective_groups: elective_groups[gid] = []
                    elective_groups[gid].append(s)
                else:
                    core_subjects.append(s)
            
            allocated_slots = set(locked_slot_ids)
            rooms_db_all = db.query(models.Room).all()
            default_room = rooms_db_all[0] if rooms_db_all else None

            # 1. Schedule Elective Groups
            for gid, group_subs in elective_groups.items():
                # Determine sessions needed by looking at remaining hours for each subject in group
                # (Total hours - manual slots already assigned in DB as locked)
                sub_remaining = []
                for s in group_subs:
                    m_count = len(getattr(s, 'manual_timeslot_ids', []) or [])
                    sub_remaining.append(s.weekly_hours - m_count)
                
                hours_needed = max(sub_remaining) if sub_remaining else 0
                attempts = 0
                while hours_needed > 0 and attempts < 100:
                    attempts += 1
                    slot = random.choice(timeslots_db)
                    if slot.id in allocated_slots: continue
                    
                    # Find rooms for each
                    for i, s in enumerate(group_subs):
                        # Get faculty
                        assigns = db.query(models.FacultySubjectAssignment).filter(models.FacultySubjectAssignment.subject_id == s.id).all()
                        fid = next((a.faculty_id for a in assigns if not a.section_ids or request.section_id in a.section_ids), None)
                        
                        entry = models.TimetableEntry(
                            timetable_id=new_timetable.id,
                            timeslot_id=slot.id,
                            subject_id=s.id,
                            faculty_id=fid,
                            room_id=rooms_db_all[i % len(rooms_db_all)].id if rooms_db_all else None,
                            is_locked=False,
                            created_by=models.EntryCreator.AI
                        )
                        db.add(entry)
                    allocated_slots.add(slot.id)
                    hours_needed -= 1

            # 2. Schedule Core Subjects
            for subject in core_subjects:
                hours_needed = subject.weekly_hours - len(getattr(subject, 'manual_timeslot_ids', []) or [])
                if hours_needed <= 0: continue
                
                # Get faculty
                assigns = db.query(models.FacultySubjectAssignment).filter(models.FacultySubjectAssignment.subject_id == subject.id).all()
                fid = next((a.faculty_id for a in assigns if not a.section_ids or request.section_id in a.section_ids), None)
                
                attempts = 0
                while hours_needed > 0 and attempts < 100:
                    attempts += 1
                    slot = random.choice(timeslots_db)
                    if slot.id in allocated_slots: continue
                    
                    entry = models.TimetableEntry(
                        timetable_id=new_timetable.id,
                        timeslot_id=slot.id,
                        subject_id=subject.id,
                        faculty_id=fid,
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
def generate_all_timetables(db: Session = Depends(get_db)):
    """
    Generates timetables for ALL sections across all departments using available subjects.
    Returns summary of generation results.
    """
    # Fetch all sections
    all_sections = db.query(models.Section).all()
    
    if not all_sections:
        raise HTTPException(status_code=404, detail="No sections found in database")
    
    results = {
        "total": len(all_sections), # Will update with actual timetable attempts
        "generated": 0,
        "failed": 0,
        "errors": [],
        "timetables": []
    }
    
    total_attempts = 0

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
            
            # Fetch ALL subjects for this department OR shared with it
            all_subjects = db.query(models.Subject).all()
            subjects = []
            for s in all_subjects:
                is_primary = s.department_id == department_id
                allowed_depts = getattr(s, 'allowed_department_ids', []) or []
                is_shared = department_id in allowed_depts
                
                if is_primary or is_shared:
                    subjects.append(s)
            
            if not subjects:
                results["failed"] += 1
                results["errors"].append({
                    "section_id": section.id,
                    "section_name": section.name,
                    "error": "No subjects found for department"
                })
                continue
            
            # Group eligible subjects by semester
            semester_subjects = {}
            for subject in subjects:
                # Find eligible faculty for this subject and section
                assigns = db.query(models.FacultySubjectAssignment).filter(
                    models.FacultySubjectAssignment.subject_id == subject.id
                ).all()
                
                is_eligible = False
                faculty_id = None
                
                if not assigns:
                    is_eligible = True # Treat as eligible but no faculty assigned yet
                else:
                    for a in assigns:
                        if not a.section_ids or section.id in a.section_ids:
                            is_eligible = True
                            faculty_id = a.faculty_id
                            break
                            
                if is_eligible:
                    sem = subject.semester
                    if sem not in semester_subjects:
                        semester_subjects[sem] = []
                    semester_subjects[sem].append({
                        "subject": subject,
                        "faculty_id": faculty_id
                    })
                    
            if not semester_subjects:
                results["failed"] += 1
                results["errors"].append({
                    "section_id": section.id,
                    "section_name": section.name,
                    "error": "No eligible subjects for this section"
                })
                continue

            # For each semester group, generate a timetable
            for sem, eligible_data in semester_subjects.items():
                total_attempts += 1
                
                # Delete existing timetable for this section and semester if any
                existing = db.query(models.Timetable).filter(
                    models.Timetable.section_id == section.id,
                    models.Timetable.semester == sem
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
                    semester=sem,
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
                for item in eligible_data:
                    subject = item["subject"]
                    fid = item["faculty_id"]
                    manual_slots = getattr(subject, 'manual_timeslot_ids', []) or []
                    
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
    
                # Separate Core and Elective Groups
                core_data = []
                elective_groups = {}
                for item in eligible_data:
                    gid = item["subject"].elective_group_id
                    if item["subject"].is_elective and gid:
                        if gid not in elective_groups: elective_groups[gid] = []
                        elective_groups[gid].append(item)
                    else:
                        core_data.append(item)

                # 1. Schedule Elective Groups
                for gid, group_items in elective_groups.items():
                    hours_needed = max([item["subject"].weekly_hours - len(getattr(item["subject"], 'manual_timeslot_ids', []) or []) for item in group_items])
                    attempts = 0
                    while hours_needed > 0 and attempts < 100:
                        attempts += 1
                        slot = random.choice(timeslots)
                        if slot.id in allocated_slots: continue
                        
                        for i, item in enumerate(group_items):
                            entry = models.TimetableEntry(
                                timetable_id=new_timetable.id,
                                timeslot_id=slot.id,
                                subject_id=item["subject"].id,
                                faculty_id=item["faculty_id"],
                                is_locked=False,
                                created_by=models.EntryCreator.AI
                            )
                            db.add(entry)
                        allocated_slots.add(slot.id)
                        hours_needed -= 1

                # 2. Schedule Core Subjects
                for item in core_data:
                    subject = item["subject"]
                    assigned_faculty_id = item["faculty_id"]
                    
                    hours_needed = subject.weekly_hours - len(getattr(subject, 'manual_timeslot_ids', []) or [])
                    if hours_needed <= 0: continue
                    
                    attempts = 0
                    while hours_needed > 0 and attempts < 100:
                        attempts += 1
                        slot = random.choice(timeslots)
                        if slot.id in allocated_slots: continue
                        
                        entry = models.TimetableEntry(
                            timetable_id=new_timetable.id,
                            timeslot_id=slot.id,
                            subject_id=subject.id,
                            faculty_id=assigned_faculty_id,
                            is_locked=False,
                            created_by=models.EntryCreator.AI
                        )
                        db.add(entry)
                        allocated_slots.add(slot.id)
                        hours_needed -= 1
                
                db.commit()
                
                results["generated"] += 1
                results["timetables"].append({
                    "timetable_id": new_timetable.id,
                    "section_id": section.id,
                    "section_name": section.name,
                    "year": academic_year.name,
                    "semester": sem
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
            
    results["total"] = total_attempts if total_attempts > 0 else len(all_sections)
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

@router.delete("/clear-all")
def clear_all_timetables(db: Session = Depends(get_db)):
    """Deletes all timetables and their entries from the system."""
    try:
        db.query(models.TimetableEntry).delete()
        db.query(models.Timetable).delete()
        db.commit()
        return {"status": "success", "message": "All timetables cleared successfully."}
    except Exception as e:
        db.rollback()
        print(f"Server Error clearing timetables: {e}")
        raise HTTPException(status_code=500, detail=str(e))
