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
    tags=["timetables"]
)


def _build_faculty_timetable_payload(faculty: models.Faculty, db: Session):
    entries = db.query(models.TimetableEntry).join(models.Timetable).filter(
        models.TimetableEntry.faculty_id == faculty.id,
        models.Timetable.status != "ARCHIVED"
    ).all()

    payload_entries = []
    for entry in entries:
        timetable = entry.timetable
        section = timetable.section if timetable else None
        academic_year = section.academic_year if section else None
        department = academic_year.department if academic_year else None
        timeslot = entry.timeslot
        subject = entry.subject

        payload_entries.append({
            "timetable_id": timetable.id if timetable else 0,
            "timetable_status": timetable.status if timetable else "UNKNOWN",
            "semester": timetable.semester if timetable else 0,
            "section_id": section.id if section else 0,
            "section_name": section.name if section else "Unknown",
            "academic_year_name": academic_year.name if academic_year else None,
            "department_name": department.name if department else None,
            "department_code": department.code if department else None,
            "subject_id": subject.id if subject else 0,
            "subject_code": subject.code if subject else None,
            "subject_name": subject.name if subject else None,
            "timeslot_id": timeslot.id if timeslot else 0,
            "day": timeslot.day if timeslot else None,
            "start_time": timeslot.start_time if timeslot else None,
            "end_time": timeslot.end_time if timeslot else None,
            "is_locked": entry.is_locked,
            "created_by": entry.created_by,
        })

    payload_entries.sort(
        key=lambda item: (
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].index(item["day"])
            if item["day"] in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            else 99,
            item["start_time"] or "",
            item["section_name"],
        )
    )

    return {
        "faculty_id": faculty.id,
        "faculty_name": faculty.name,
        "faculty_id_code": faculty.faculty_id_code,
        "entries": payload_entries,
    }

@router.post("/{timetable_id}/validate", response_model=schemas.ValidationResponse)
def validate_timetable(
    timetable_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin)
):
    tt = db.query(models.Timetable).filter(models.Timetable.id == timetable_id).first()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found")
        
    return validate_timetable_internal(tt, db)

def validate_timetable_internal(timetable: models.Timetable, db: Session):
    errors = []
    warnings = []
    error_slots = []
    warning_slots = []
    
    other_entries = db.query(models.TimetableEntry).join(models.Timetable).filter(
        models.Timetable.id != timetable.id,
        models.Timetable.status != "ARCHIVED"
    ).all()
    
    faculty_slots = {}
    for e in other_entries:
        if e.faculty_id:
            faculty_slots.setdefault(e.faculty_id, {}).setdefault(e.timeslot_id, []).append(True)
            
    subject_days = {}
    faculty_daily_load = {}
    section_slots = {}
    
    for entry in timetable.entries:
        ts = db.query(models.TimeSlot).get(entry.timeslot_id)
        if not ts: continue

            
        if entry.faculty_id:
            if entry.faculty_id in faculty_slots and entry.timeslot_id in faculty_slots[entry.faculty_id]:
                fac = db.query(models.Faculty).get(entry.faculty_id)
                errors.append(f"Faculty conflict: {fac.name if fac else ''} booked at {ts.day} {ts.start_time}.")
                error_slots.append(entry.timeslot_id)
            faculty_slots.setdefault(entry.faculty_id, {}).setdefault(entry.timeslot_id, []).append(True)
            
            faculty_daily_load.setdefault(entry.faculty_id, {}).setdefault(ts.day, 0)
            faculty_daily_load[entry.faculty_id][ts.day] += 1
            
        if entry.timeslot_id not in section_slots:
            section_slots[entry.timeslot_id] = []
        section_slots[entry.timeslot_id].append(entry)
        
        if entry.subject_id:
            subject_days.setdefault(entry.subject_id, {}).setdefault(ts.day, 0)
            subject_days[entry.subject_id][ts.day] += 1
            
    for ts_id, entries in section_slots.items():
        if len(entries) > 1:
            all_electives = all(e.subject and e.subject.is_elective for e in entries)
            if not all_electives:
                errors.append(f"Section conflict: Multiple subjects overlapping in a single timeslot.")
                error_slots.append(ts_id)
                
    for subject_id, days in subject_days.items():
        for day, count in days.items():
            if count > 2:
                sub = db.query(models.Subject).get(subject_id)
                warnings.append(f"Uneven distribution: Subject '{sub.code if sub else subject_id}' scheduled {count} times on {day}.")
                # Note: We aren't capturing the specific slot IDs for this warning easily here, but that's okay for now.
                
    for fid, days in faculty_daily_load.items():
        for day, count in days.items():
            if count > 4:
                fac = db.query(models.Faculty).get(fid)
                warnings.append(f"Faculty overloaded: '{fac.name if fac else fid}' teaches {count} classes on {day}.")
                
    status = "FAIL" if errors else "PASS"
    return {"status": status, "errors": errors, "warnings": warnings, "error_slots": list(set(error_slots)), "warning_slots": list(set(warning_slots))}

@router.post("/generate", response_model=schemas.Timetable)
def generate_timetable(
    request: schemas.GenerateTimetableRequest,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin)
):
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
        ).order_by(models.Timetable.version.desc()).first()
        
        locked_slot_ids = set()
        locked_entries_by_slot = {}
        locked_slots_payload = []

        if existing_tt:
            existing_tt.status = "ARCHIVED"

        new_timetable = models.Timetable(
            section_id=request.section_id,
            semester=request.semester,
            status="DRAFT",
            is_active=False,
            version=existing_tt.version + 1 if existing_tt else 1
        )
        db.add(new_timetable)
        db.flush()

        subjects_by_id = {s.id: s for s in subjects_db}

        def can_share_locked_slot(subject, ts_id):
            if not subject.is_elective or subject.elective_group_id is None:
                return False

            existing_entries = locked_entries_by_slot.get(ts_id, [])
            if not existing_entries:
                return True

            for existing in existing_entries:
                existing_subject = subjects_by_id.get(existing["subject_id"])
                if (
                    not existing_subject
                    or not existing_subject.is_elective
                    or existing_subject.elective_group_id != subject.elective_group_id
                ):
                    return False
            return True

        def remember_locked_entry(subject_id, faculty_id, timeslot_id):
            locked_slot_ids.add(timeslot_id)
            locked_slots_payload.append({
                "subject_id": subject_id,
                "faculty_id": faculty_id,
                "timeslot_id": timeslot_id
            })
            locked_entries_by_slot.setdefault(timeslot_id, []).append({
                "subject_id": subject_id,
                "faculty_id": faculty_id,
                "timeslot_id": timeslot_id
            })

        if existing_tt:
            # Fetch existing locked entries (Manual Locks from UI)
            locked_entries = db.query(models.TimetableEntry).filter(
                models.TimetableEntry.timetable_id == existing_tt.id,
                models.TimetableEntry.is_locked == True
            ).all()
            for e in locked_entries:
                remember_locked_entry(e.subject_id, e.faculty_id, e.timeslot_id)
                # Add it to DB right away to the new_timetable
                db.add(models.TimetableEntry(
                    timetable_id=new_timetable.id,
                    timeslot_id=e.timeslot_id,
                    subject_id=e.subject_id,
                    faculty_id=e.faculty_id,
                    is_locked=True,
                    created_by=models.EntryCreator.ADMIN
                ))

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
                    locked_key_exists = any(
                        entry["subject_id"] == s.id for entry in locked_entries_by_slot.get(ts_id, [])
                    )
                    if locked_key_exists:
                        continue

                    slot_is_free = ts_id not in locked_slot_ids
                    if slot_is_free or can_share_locked_slot(s, ts_id):
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
                        remember_locked_entry(s.id, f_id, ts_id)
        db.flush()

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
        timeslots_payload = [{"id": t.id, "day": t.day, "time": str(t.start_time)} for t in timeslots_db]
        
        # Fetch commitments/preferences
        existing_commitments = {}
        conflicting_entries = db.query(models.TimetableEntry).join(models.Timetable).filter(
            models.Timetable.section_id != request.section_id,
            models.Timetable.status != "ARCHIVED"
        ).all()
        for e in conflicting_entries:
            if e.faculty_id and e.faculty_id in faculty_ids:
                existing_commitments.setdefault(e.faculty_id, []).append(e.timeslot_id)
        
        faculty_preferences = {f.id: {"max_hours": f.max_hours_per_week, "preferred_slots": f.preferred_slots} for f in faculty_db}

        payload = {
            "semester": request.semester,
            "subjects": subjects_payload,
            "faculty": faculty_payload,
            "timeslots": timeslots_payload,
            "locked_slots": locked_slots_payload,
            "constraints": {
                "prior_commitments": existing_commitments,
                "faculty_preferences": faculty_preferences
            }
        }
        # 6. Call AI Engine
        import json
        import urllib.request
        import urllib.error
        
        schedule = None
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(f"{AI_ENGINE_URL}/optimize", data=data, headers={'Content-Type': 'application/json'})
            
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status == 200:
                    result = json.loads(response.read().decode('utf-8'))
                    if result.get("status") == "success":
                        schedule = result.get("schedule", [])
            
        except urllib.error.HTTPError as e:
            # Handle AI Engine 400 Bad Request (Validation/Clash errors)
            if e.code == 400:
                error_body = json.loads(e.read().decode('utf-8'))
                db.rollback()
                raise HTTPException(status_code=400, detail=error_body.get("detail", "AI Engine encountered a clash."))
            else:
                db.rollback()
                raise HTTPException(status_code=500, detail=f"AI Engine Error: {e.reason}")
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to communicate with AI Engine: {e}")

        if schedule is not None:
            # Clear previous attempt entries for AI (keeping locked)
            db.query(models.TimetableEntry).filter(
                models.TimetableEntry.timetable_id == new_timetable.id,
                models.TimetableEntry.is_locked == False
            ).delete()
            
            section_occupied_slots = set(locked_slot_ids)
            for item in schedule:
                sub_obj = db.query(models.Subject).get(item['subject_id'])
                is_el = (sub_obj.is_elective and sub_obj.elective_group_id) if sub_obj else False
                
                if not is_el and item['timeslot_id'] in section_occupied_slots:
                    continue

                entry = models.TimetableEntry(
                    timetable_id=new_timetable.id,
                    subject_id=item['subject_id'],
                    faculty_id=item.get('faculty_id'),
                    timeslot_id=item['timeslot_id'],
                    is_locked=False,
                    created_by=models.EntryCreator.AI
                )
                db.add(entry)
                if not is_el:
                    section_occupied_slots.add(item['timeslot_id'])
            
            db.flush()
            
            val_res = validate_timetable_internal(new_timetable, db)
            if val_res["status"] != "PASS":
                db.rollback()
                error_details = "; ".join(val_res["errors"])
                raise HTTPException(status_code=400, detail=f"Validation failed after generation: {error_details}")

            db.commit()
            db.refresh(new_timetable)
            return new_timetable
        else:
            db.rollback()
            raise HTTPException(status_code=500, detail="AI Engine failed to return a valid schedule.")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Server Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-all")
def generate_all_timetables(
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin)
):
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
                try:
                    # Leverage the exact same AI generation logic as single generation
                    gen_req = schemas.GenerateTimetableRequest(
                        section_id=section.id,
                        semester=sem
                    )
                    
                    # Generate the timetable (this will throw an HTTPException on clash/error)
                    new_timetable = generate_timetable(gen_req, db)
                    
                    # Bulk generation defaults to ACTIVE status
                    new_timetable.status = "ACTIVE"
                    db.commit()
                    
                    results["generated"] += 1
                    results["timetables"].append({
                        "timetable_id": new_timetable.id,
                        "section_id": section.id,
                        "section_name": section.name,
                        "year": academic_year.name,
                        "semester": sem
                    })
                    
                except HTTPException as e:
                    results["failed"] += 1
                    results["errors"].append({
                        "section_id": section.id,
                        "section_name": section.name,
                        "error": e.detail
                    })
                    continue
                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({
                        "section_id": section.id,
                        "section_name": section.name,
                        "error": str(e)
                    })
                    continue
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "section_id": section.id,
                "section_name": section.name,
                "error": f"Failed to process section: {str(e)}"
            })
            db.rollback()
            continue
            
    results["total"] = total_attempts if total_attempts > 0 else len(all_sections)
    return results



@router.post("/regenerate", response_model=schemas.Timetable)
def regenerate_timetable(
    request: schemas.RegenerateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin)
):
    """Regenerate a new version of the timetable, archiving the old one."""
    gen_request = schemas.GenerateTimetableRequest(
        section_id=request.section_id,
        semester=request.semester
    )
    return generate_timetable(gen_request, db)

# --- Read Endpoints ---

@router.get("/", response_model=List[schemas.Timetable])
def get_timetables(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin)
):
    return db.query(models.Timetable).order_by(models.Timetable.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/faculty/me", response_model=schemas.FacultyTimetableResponse)
def get_faculty_timetable(
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_faculty)
):
    faculty = db.query(models.Faculty).filter(models.Faculty.id == current_user.faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty profile not found")

    return _build_faculty_timetable_payload(faculty, db)


@router.get("/faculty", response_model=schemas.FacultyTimetableResponse)
def get_admin_faculty_timetable(
    faculty_id: Optional[int] = None,
    faculty_id_code: Optional[str] = None,
    faculty_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin)
):
    faculty = None

    if faculty_id is not None:
        faculty = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()

    if faculty is None and faculty_id_code:
        normalized_code = faculty_id_code.strip()
        faculty = db.query(models.Faculty).filter(models.Faculty.faculty_id_code == normalized_code).first()

    if faculty is None and faculty_name:
        normalized_name = faculty_name.strip()
        faculty = db.query(models.Faculty).filter(models.Faculty.name.ilike(normalized_name)).first()

    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")

    return _build_faculty_timetable_payload(faculty, db)

@router.get("/{timetable_id}", response_model=schemas.Timetable)
def get_timetable(
    timetable_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin)
):
    tt = db.query(models.Timetable).filter(models.Timetable.id == timetable_id).first()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found")
        
    tt_dict = {
        "id": tt.id,
        "section_id": tt.section_id,
        "semester": tt.semester,
        "status": tt.status,
        "section": tt.section,
        "entries": list(tt.entries)
    }

    # Find all CBCS entries in the same semester that share a timeslot with an elective in this timetable
    elective_timeslots = set()
    for entry in tt.entries:
        if entry.subject and entry.subject.is_elective:
            elective_timeslots.add(entry.timeslot_id)
            
    if elective_timeslots:
        # Find all other entries in the same semester for these timeslots that are also electives
        other_entries = db.query(models.TimetableEntry).join(models.Timetable).join(models.Subject).filter(
            models.Timetable.semester == tt.semester,
            models.TimetableEntry.timeslot_id.in_(elective_timeslots),
            models.Subject.is_elective == True,
            models.Timetable.id != tt.id
        ).all()
        
        # Deduplicate by (subject_id, timeslot_id) to avoid duplicates if multiple sections share the same elective
        existing_keys = {(e.subject_id, e.timeslot_id) for e in tt.entries}
        
        for entry in other_entries:
            key = (entry.subject_id, entry.timeslot_id)
            if key not in existing_keys:
                tt_dict["entries"].append(entry)
                existing_keys.add(key)

    return tt_dict

@router.delete("/clear-all")
def clear_all_timetables(
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin)
):
    """Delete every generated timetable record, including history and locked entries."""
    try:
        deleted_entries = db.query(models.TimetableEntry).delete(synchronize_session=False)
        deleted_timetables = db.query(models.Timetable).delete(synchronize_session=False)
        db.commit()
        return {
            "status": "success",
            "message": "All generated timetable data cleared successfully.",
            "deleted_timetables": deleted_timetables,
            "deleted_entries": deleted_entries
        }
    except Exception as e:
        db.rollback()
        print(f"Server Error clearing timetables: {e}")
        raise HTTPException(status_code=500, detail=str(e))
