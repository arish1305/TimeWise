from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
import random

from database import get_db
import models
import schemas
import auth

router = APIRouter(
    prefix="/timetables",
    tags=["timetables"]
)

COMMITMENT_STATUSES = ("ACTIVE", "APPROVED")
DAY_ORDER = {
    "Monday": 1,
    "Tuesday": 2,
    "Wednesday": 3,
    "Thursday": 4,
    "Friday": 5,
    "Saturday": 6,
    "Sunday": 7,
}


def _is_cbcs_subject(subject: Optional[models.Subject]) -> bool:
    if not subject:
        return False
    allowed_departments = getattr(subject, "allowed_department_ids", None) or []
    return bool(allowed_departments)


def _entries_share_cbcs_session(left: models.TimetableEntry, right: models.TimetableEntry) -> bool:
    if not left.subject or not right.subject:
        return False
    return (
        left.subject_id == right.subject_id
        and left.faculty_id == right.faculty_id
        and left.timeslot_id == right.timeslot_id
        and _is_cbcs_subject(left.subject)
        and _is_cbcs_subject(right.subject)
    )


def _subject_overlap_group_key(subject: Optional[models.Subject], timeslot_id: Optional[int]) -> Optional[str]:
    if not subject or not subject.is_elective:
        return None

    group_id = (subject.elective_group_id or "").strip()
    if group_id:
        return f"G:{group_id}"

    manual_slots = getattr(subject, "manual_timeslot_ids", []) or []
    if timeslot_id in manual_slots:
        return f"M:{timeslot_id}"
    return None


def _entries_can_overlap_in_section(entries: List[models.TimetableEntry]) -> bool:
    subject_ids = [entry.subject_id for entry in entries if entry.subject_id]
    if len(subject_ids) != len(set(subject_ids)):
        return False

    if not entries:
        return True
    slot_id = entries[0].timeslot_id

    group_keys = set()
    for entry in entries:
        if not entry.subject:
            return False
        group_key = _subject_overlap_group_key(entry.subject, slot_id)
        if not group_key:
            return False
        group_keys.add(group_key)
    return len(group_keys) == 1


def _solve_timetable_locally(
    subjects: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]],
    constraints: Dict[str, Any],
    locked_slots: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    subject_by_id = {subject["id"]: subject for subject in subjects}
    faculty_by_id = {item["id"]: item for item in faculty}
    faculty_preferences = constraints.get("faculty_preferences", {}) or {}
    prior_commitments = constraints.get("prior_commitments", {}) or {}
    prior_entries = constraints.get("prior_commitment_entries", {}) or {}

    sorted_slots = sorted(
        timeslots,
        key=lambda slot: (DAY_ORDER.get(slot.get("day"), 99), str(slot.get("time", "")), slot["id"])
    )

    faculty_busy = {item["id"]: set() for item in faculty}
    faculty_hours = {item["id"]: 0 for item in faculty}
    section_busy = set()
    locked_hours = {}
    subject_day_count: Dict[int, Dict[str, int]] = {}
    prior_subjects_by_faculty_slot: Dict[int, Dict[int, List[int]]] = {}

    for fid, entries in prior_entries.items():
        try:
            faculty_id = int(fid)
        except (TypeError, ValueError):
            continue
        for entry in entries or []:
            ts_id = entry.get("timeslot_id")
            subject_id = entry.get("subject_id")
            if ts_id is None:
                continue
            prior_subjects_by_faculty_slot.setdefault(faculty_id, {}).setdefault(ts_id, []).append(subject_id)

    for fid, slots in prior_commitments.items():
        try:
            faculty_id = int(fid)
        except (TypeError, ValueError):
            continue
        faculty_busy.setdefault(faculty_id, set()).update(slots or [])
        faculty_hours[faculty_id] = faculty_hours.get(faculty_id, 0) + len(slots or [])

    for locked in locked_slots or []:
        subject_id = locked.get("subject_id")
        faculty_id = locked.get("faculty_id")
        timeslot_id = locked.get("timeslot_id")
        if timeslot_id is None:
            continue

        section_busy.add(timeslot_id)
        if subject_id:
            locked_hours[subject_id] = locked_hours.get(subject_id, 0) + 1
            slot = next((item for item in sorted_slots if item["id"] == timeslot_id), None)
            if slot:
                subject_day_count.setdefault(subject_id, {}).setdefault(slot.get("day"), 0)
                subject_day_count[subject_id][slot.get("day")] += 1
        if faculty_id:
            faculty_busy.setdefault(faculty_id, set()).add(timeslot_id)
            faculty_hours[faculty_id] = faculty_hours.get(faculty_id, 0) + 1

    def max_hours_for(faculty_id: int) -> int:
        prefs = faculty_preferences.get(faculty_id) or faculty_preferences.get(str(faculty_id)) or {}
        return int(prefs.get("max_hours", 18) or 18)

    def can_share_faculty_slot(subject: Dict[str, Any], faculty_id: int, timeslot_id: int) -> bool:
        if not subject.get("is_cbcs_shared"):
            return False
        committed_subjects = prior_subjects_by_faculty_slot.get(faculty_id, {}).get(timeslot_id, [])
        return bool(committed_subjects) and all(subject_id == subject.get("id") for subject_id in committed_subjects)

    def faculty_available(subject: Dict[str, Any], timeslot_id: int, enforce_max_hours: bool) -> bool:
        faculty_id = subject.get("faculty_id")
        if not faculty_id:
            return True
        if timeslot_id in faculty_busy.get(faculty_id, set()) and not can_share_faculty_slot(subject, faculty_id, timeslot_id):
            return False
        return not enforce_max_hours or faculty_hours.get(faculty_id, 0) < max_hours_for(faculty_id)

    def remember(entry: Dict[str, Any], slot: Dict[str, Any]) -> None:
        subject_id = entry["subject_id"]
        faculty_id = entry.get("faculty_id")
        timeslot_id = entry["timeslot_id"]
        section_busy.add(timeslot_id)
        subject_day_count.setdefault(subject_id, {}).setdefault(slot.get("day"), 0)
        subject_day_count[subject_id][slot.get("day")] += 1
        if faculty_id:
            faculty_busy.setdefault(faculty_id, set()).add(timeslot_id)
            faculty_hours[faculty_id] = faculty_hours.get(faculty_id, 0) + 1

    def ordered_slots_for(subject: Dict[str, Any]) -> List[Dict[str, Any]]:
        subject_id = subject["id"]
        return sorted(
            sorted_slots,
            key=lambda slot: (
                subject_day_count.get(subject_id, {}).get(slot.get("day"), 0),
                DAY_ORDER.get(slot.get("day"), 99),
                str(slot.get("time", "")),
                slot["id"],
            )
        )

    schedule: List[Dict[str, Any]] = []

    elective_groups: Dict[str, List[Dict[str, Any]]] = {}
    core_subjects: List[Dict[str, Any]] = []
    for subject in subjects:
        group_id = str(subject.get("elective_group_id") or "").strip()
        if subject.get("is_elective") and group_id:
            elective_groups.setdefault(group_id, []).append(subject)
        else:
            core_subjects.append(subject)

    for group_subjects in elective_groups.values():
        sessions_needed = max(
            max(0, int(subject.get("credits", 3) or 0) - locked_hours.get(subject["id"], 0))
            for subject in group_subjects
        )
        for _ in range(sessions_needed):
            assigned = False
            for enforce_max_hours in (True, False):
                for slot in sorted_slots:
                    if slot["id"] in section_busy:
                        continue
                    if not all(faculty_available(subject, slot["id"], enforce_max_hours) for subject in group_subjects):
                        continue
                    for subject in group_subjects:
                        entry = {
                            "subject_id": subject["id"],
                            "faculty_id": subject.get("faculty_id"),
                            "timeslot_id": slot["id"],
                        }
                        schedule.append(entry)
                        remember(entry, slot)
                    assigned = True
                    break
                if assigned:
                    break
            if not assigned:
                break

    core_subjects.sort(
        key=lambda subject: int(subject.get("credits", 3) or 0) - locked_hours.get(subject["id"], 0),
        reverse=True
    )
    for subject in core_subjects:
        sessions_needed = max(0, int(subject.get("credits", 3) or 0) - locked_hours.get(subject["id"], 0))
        for _ in range(sessions_needed):
            assigned = False
            for enforce_max_hours in (True, False):
                for slot in ordered_slots_for(subject):
                    if slot["id"] in section_busy:
                        continue
                    if not faculty_available(subject, slot["id"], enforce_max_hours):
                        continue
                    entry = {
                        "subject_id": subject["id"],
                        "faculty_id": subject.get("faculty_id"),
                        "timeslot_id": slot["id"],
                    }
                    schedule.append(entry)
                    remember(entry, slot)
                    assigned = True
                    break
                if assigned:
                    break

            if not assigned:
                for slot in ordered_slots_for(subject):
                    if slot["id"] not in section_busy:
                        entry = {
                            "subject_id": subject["id"],
                            "faculty_id": None,
                            "timeslot_id": slot["id"],
                        }
                        schedule.append(entry)
                        remember(entry, slot)
                        assigned = True
                        break
            if not assigned:
                break

    return schedule


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
        models.Timetable.status.in_(COMMITMENT_STATUSES)
    ).all()
    
    faculty_slots = {}
    for e in other_entries:
        if e.faculty_id:
            faculty_slots.setdefault(e.faculty_id, {}).setdefault(e.timeslot_id, []).append(e)
            
    subject_days = {}
    faculty_daily_load = {}
    section_slots = {}
    
    for entry in timetable.entries:
        ts = db.query(models.TimeSlot).get(entry.timeslot_id)
        if not ts: continue

            
        if entry.faculty_id:
            if entry.faculty_id in faculty_slots and entry.timeslot_id in faculty_slots[entry.faculty_id]:
                conflicting_entries = faculty_slots[entry.faculty_id][entry.timeslot_id]
                if not all(_entries_share_cbcs_session(entry, existing) for existing in conflicting_entries):
                    fac = db.query(models.Faculty).get(entry.faculty_id)
                    errors.append(f"Faculty conflict: {fac.name if fac else ''} booked at {ts.day} {ts.start_time}.")
                    error_slots.append(entry.timeslot_id)
            faculty_slots.setdefault(entry.faculty_id, {}).setdefault(entry.timeslot_id, []).append(entry)
            
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
            if not _entries_can_overlap_in_section(entries):
                errors.append("Section conflict: Multiple unrelated subjects overlap in a single timeslot.")
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

        def get_subject(subject_id: Optional[int]) -> Optional[models.Subject]:
            if not subject_id:
                return None
            subject = subjects_by_id.get(subject_id)
            if subject:
                return subject
            return db.query(models.Subject).get(subject_id)

        def can_share_slot_with_existing(
            subject_obj: Optional[models.Subject],
            existing_entries: List[dict],
            timeslot_id: Optional[int]
        ) -> bool:
            if not existing_entries:
                return True
            current_group_key = _subject_overlap_group_key(subject_obj, timeslot_id)
            if not current_group_key:
                return False

            for existing in existing_entries:
                existing_subject = get_subject(existing.get("subject_id"))
                existing_group_key = _subject_overlap_group_key(existing_subject, timeslot_id)
                if (
                    not existing_subject
                    or not existing_group_key
                    or existing_group_key != current_group_key
                    or existing_subject.id == subject_obj.id
                ):
                    return False
            return True

        def resolve_faculty_id(subject_id: int) -> Optional[int]:
            assignments = db.query(models.FacultySubjectAssignment).filter(
                models.FacultySubjectAssignment.subject_id == subject_id
            ).order_by(models.FacultySubjectAssignment.preference_level.asc()).all()

            for assignment in assignments:
                if not assignment.section_ids or request.section_id in assignment.section_ids:
                    return assignment.faculty_id
            return None

        subject_faculty_ids = {s.id: resolve_faculty_id(s.id) for s in subjects_db}
        for s in subjects_db:
            if not _is_cbcs_subject(s):
                continue

            existing_shared_faculty = db.query(models.TimetableEntry.faculty_id).join(models.Timetable).filter(
                models.Timetable.section_id != request.section_id,
                models.Timetable.semester == request.semester,
                models.Timetable.status.in_(COMMITMENT_STATUSES),
                models.TimetableEntry.subject_id == s.id,
                models.TimetableEntry.faculty_id.isnot(None),
            ).first()
            if existing_shared_faculty and existing_shared_faculty[0]:
                subject_faculty_ids[s.id] = existing_shared_faculty[0]

        def can_share_locked_slot(subject, ts_id):
            return can_share_slot_with_existing(subject, locked_entries_by_slot.get(ts_id, []), ts_id)

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
                models.TimetableEntry.is_locked == True,
                models.TimetableEntry.created_by.in_([
                    models.EntryCreator.ADMIN.value,
                    str(models.EntryCreator.ADMIN),
                ])
            ).all()
            for e in locked_entries:
                subject_obj = get_subject(e.subject_id)
                if not can_share_locked_slot(subject_obj, e.timeslot_id):
                    slot = db.query(models.TimeSlot).get(e.timeslot_id)
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Locked slot conflict at {slot.day if slot else 'Unknown'} "
                            f"{slot.start_time if slot else e.timeslot_id}. "
                            "Adjust locked entries so only same elective-group subjects overlap."
                        )
                    )
                remember_locked_entry(e.subject_id, e.faculty_id, e.timeslot_id)
                # Add it to DB right away to the new_timetable
                db.add(models.TimetableEntry(
                    timetable_id=new_timetable.id,
                    timeslot_id=e.timeslot_id,
                    subject_id=e.subject_id,
                    faculty_id=e.faculty_id,
                    is_locked=True,
                    created_by=models.EntryCreator.ADMIN.value
                ))

        # Sync manual slots from Subject definitions
        for s in subjects_db:
            m_slots = getattr(s, 'manual_timeslot_ids', []) or []
            if m_slots:
                f_id = subject_faculty_ids.get(s.id)
                
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
                            created_by=models.EntryCreator.ADMIN.value
                        )
                        db.add(entry)
                        remember_locked_entry(s.id, f_id, ts_id)

        # Reuse already generated CBCS slots for shared subjects. This keeps one
        # shared subject with one staff member at the same hour across departments.
        for s in subjects_db:
            if not _is_cbcs_subject(s):
                continue

            f_id = subject_faculty_ids.get(s.id)
            if not f_id:
                continue

            shared_entries = db.query(models.TimetableEntry).join(models.Timetable).filter(
                models.Timetable.section_id != request.section_id,
                models.Timetable.semester == request.semester,
                models.Timetable.status.in_(COMMITMENT_STATUSES),
                models.TimetableEntry.subject_id == s.id,
                models.TimetableEntry.faculty_id == f_id,
            ).all()

            inherited_timeslots = []
            seen_timeslots = set()
            for shared_entry in shared_entries:
                if shared_entry.timeslot_id in seen_timeslots:
                    continue
                seen_timeslots.add(shared_entry.timeslot_id)
                inherited_timeslots.append(shared_entry.timeslot_id)

            for ts_id in inherited_timeslots[:s.weekly_hours]:
                locked_key_exists = any(
                    entry["subject_id"] == s.id for entry in locked_entries_by_slot.get(ts_id, [])
                )
                if locked_key_exists:
                    continue

                if ts_id in locked_slot_ids and not can_share_locked_slot(s, ts_id):
                    slot = db.query(models.TimeSlot).get(ts_id)
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"CBCS subject '{s.code}' must share {slot.day} {slot.start_time if slot else ts_id}, "
                            "but this section already has a locked class there."
                        )
                    )

                db.add(models.TimetableEntry(
                    timetable_id=new_timetable.id,
                    timeslot_id=ts_id,
                    subject_id=s.id,
                    faculty_id=f_id,
                    is_locked=True,
                    created_by=models.EntryCreator.AI.value
                ))
                remember_locked_entry(s.id, f_id, ts_id)
        db.flush()

        # 5. Prepare Data for AI Engine
        AI_ENGINE_URL = os.getenv("AI_ENGINE_URL", "http://localhost:8001")
        
        subjects_payload = []
        faculty_ids = set()
        for s in subjects_db:
            fid = subject_faculty_ids.get(s.id)
            if fid: faculty_ids.add(fid)
                
            # Send TOTAL weekly hours; AI engine will handle subtraction of locked sessions
            subjects_payload.append({
                "id": s.id,
                "name": s.name,
                "credits": s.weekly_hours, 
                "faculty_id": fid,
                "is_elective": s.is_elective,
                "elective_group_id": s.elective_group_id,
                "is_cbcs_shared": _is_cbcs_subject(s),
            })

        faculty_db = db.query(models.Faculty).filter(models.Faculty.id.in_(faculty_ids)).all()
        faculty_payload = [{"id": f.id, "name": f.name} for f in faculty_db]
        timeslots_payload = [{"id": t.id, "day": t.day, "time": str(t.start_time)} for t in timeslots_db]
        
        # Fetch commitments/preferences
        existing_commitments = {}
        prior_commitment_entries = {}
        conflicting_entries = db.query(models.TimetableEntry).join(models.Timetable).filter(
            models.Timetable.section_id != request.section_id,
            models.Timetable.status.in_(COMMITMENT_STATUSES)
        ).all()
        for e in conflicting_entries:
            if e.faculty_id and e.faculty_id in faculty_ids:
                existing_commitments.setdefault(e.faculty_id, []).append(e.timeslot_id)
                prior_commitment_entries.setdefault(e.faculty_id, []).append({
                    "timeslot_id": e.timeslot_id,
                    "subject_id": e.subject_id,
                })
        
        faculty_preferences = {f.id: {"max_hours": f.max_hours_per_week, "preferred_slots": f.preferred_slots} for f in faculty_db}

        payload = {
            "semester": request.semester,
            "subjects": subjects_payload,
            "faculty": faculty_payload,
            "timeslots": timeslots_payload,
            "locked_slots": locked_slots_payload,
            "constraints": {
                "prior_commitments": existing_commitments,
                "prior_commitment_entries": prior_commitment_entries,
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
                e.read()
                schedule = _solve_timetable_locally(
                    subjects=subjects_payload,
                    faculty=faculty_payload,
                    timeslots=timeslots_payload,
                    constraints=payload["constraints"],
                    locked_slots=locked_slots_payload,
                )
            else:
                db.rollback()
                raise HTTPException(status_code=500, detail=f"AI Engine Error: {e.reason}")
        except Exception as e:
            schedule = _solve_timetable_locally(
                subjects=subjects_payload,
                faculty=faculty_payload,
                timeslots=timeslots_payload,
                constraints=payload["constraints"],
                locked_slots=locked_slots_payload,
            )

        if schedule is not None:
            # Clear previous attempt entries for AI (keeping locked)
            db.query(models.TimetableEntry).filter(
                models.TimetableEntry.timetable_id == new_timetable.id,
                models.TimetableEntry.is_locked == False
            ).delete()
            
            section_entries_by_slot = {
                ts_id: list(entries) for ts_id, entries in locked_entries_by_slot.items()
            }
            for item in schedule:
                sub_obj = db.query(models.Subject).get(item['subject_id'])
                slot_entries = section_entries_by_slot.get(item['timeslot_id'], [])
                if slot_entries and not can_share_slot_with_existing(sub_obj, slot_entries, item['timeslot_id']):
                    continue

                entry = models.TimetableEntry(
                    timetable_id=new_timetable.id,
                    subject_id=item['subject_id'],
                    faculty_id=item.get('faculty_id'),
                    timeslot_id=item['timeslot_id'],
                    is_locked=False,
                    created_by=models.EntryCreator.AI.value
                )
                db.add(entry)
                section_entries_by_slot.setdefault(item['timeslot_id'], []).append({
                    "subject_id": item["subject_id"],
                    "faculty_id": item.get("faculty_id"),
                    "timeslot_id": item["timeslot_id"],
                })
            
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

    # Find related CBCS/elective entries in active timetables that share a slot
    # with an elective in this timetable.
    shared_timeslots = set()
    elective_group_ids = set()
    cbcs_subject_ids = set()
    for entry in tt.entries:
        if entry.subject and (entry.subject.is_elective or _is_cbcs_subject(entry.subject)):
            shared_timeslots.add(entry.timeslot_id)
            if entry.subject.elective_group_id:
                elective_group_ids.add(entry.subject.elective_group_id)
            if _is_cbcs_subject(entry.subject):
                cbcs_subject_ids.add(entry.subject_id)
            
    if shared_timeslots:
        other_entries = db.query(models.TimetableEntry).join(models.Timetable).join(models.Subject).filter(
            models.Timetable.semester == tt.semester,
            models.Timetable.status.in_(COMMITMENT_STATUSES),
            models.TimetableEntry.timeslot_id.in_(shared_timeslots),
            models.Timetable.id != tt.id
        ).all()
        
        # Deduplicate by (subject_id, timeslot_id) to avoid duplicates if multiple sections share the same elective
        existing_keys = {(e.subject_id, e.timeslot_id) for e in tt.entries}
        
        for entry in other_entries:
            is_related_cbcs = entry.subject_id in cbcs_subject_ids
            is_related_elective_group = (
                entry.subject
                and entry.subject.elective_group_id
                and entry.subject.elective_group_id in elective_group_ids
            )
            if not is_related_cbcs and not is_related_elective_group:
                continue

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
