from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
import json
import logging
import os
import random

from database import get_db
import models
import schemas
import auth

router = APIRouter(
    prefix="/timetables",
    tags=["timetables"]
)

logger = logging.getLogger(__name__)

COMMITMENT_STATUSES = ("DRAFT", "ACTIVE", "APPROVED", "GENERATED", "EDITED")
APPROVED_COMMITMENT_STATUSES = ("APPROVED",)
DAY_ORDER = {
    "Monday": 1,
    "Tuesday": 2,
    "Wednesday": 3,
    "Thursday": 4,
    "Friday": 5,
    "Saturday": 6,
    "Sunday": 7,
}


def _default_rules() -> Dict[str, Any]:
    return {
        "max_daily_subjects": 5,
        "spread_subjects": True,
        "allow_saturday": False,
        "max_lab_per_day": 1,
    }


def _load_effective_rules(db: Session, department_id: Optional[int]) -> Dict[str, Any]:
    if department_id is not None:
        dept_rules = db.query(models.SchedulingRule).filter(
            models.SchedulingRule.department_id == department_id,
            models.SchedulingRule.name == "default",
            models.SchedulingRule.is_active == True,
        ).order_by(models.SchedulingRule.id.desc()).first()
        if dept_rules and isinstance(dept_rules.rules, dict):
            return {**_default_rules(), **dept_rules.rules}

    global_rules = db.query(models.SchedulingRule).filter(
        models.SchedulingRule.department_id.is_(None),
        models.SchedulingRule.name == "default",
        models.SchedulingRule.is_active == True,
    ).order_by(models.SchedulingRule.id.desc()).first()
    if global_rules and isinstance(global_rules.rules, dict):
        return {**_default_rules(), **global_rules.rules}

    return _default_rules()


def _is_cbcs_subject(subject: Optional[models.Subject]) -> bool:
    if not subject:
        return False
    allowed_departments = getattr(subject, "allowed_department_ids", None) or []
    return bool(allowed_departments)


def _query_department_timeslots(db: Session, department_id: int, include_breaks: bool = False):
    q = db.query(models.TimeSlot).filter(models.TimeSlot.department_id == department_id)
    if not include_breaks:
        q = q.filter(models.TimeSlot.is_break == False)
    return q


def _time_value(value: Any) -> str:
    return str(value or "")


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


def _is_faculty_unavailable_for_slot(db: Session, faculty_id: Optional[int], slot_id: Optional[int]) -> bool:
    if not faculty_id or not slot_id:
        return False
    return db.query(models.FacultyAvailability.id).filter(
        models.FacultyAvailability.faculty_id == faculty_id,
        models.FacultyAvailability.timeslot_id == slot_id,
        models.FacultyAvailability.status == models.FacultyAvailabilityStatus.UNAVAILABLE.value,
    ).first() is not None


def _solve_timetable_locally(
    subjects: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]],
    constraints: Dict[str, Any],
    locked_slots: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    from scheduler import CSPSolver
    
    solver = CSPSolver(
        subjects=subjects,
        faculty=faculty,
        timeslots=timeslots,
        constraints=constraints,
        locked_slots=locked_slots
    )
    return solver.solve()


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


def _log_edit_event(
    db: Session,
    timetable_id: int,
    event_type: str,
    payload: Dict[str, Any],
    entry_id: Optional[int] = None,
    edited_by: Optional[int] = None,
    version: int = 1,
) -> None:
    db.add(models.TimetableEditEvent(
        timetable_id=timetable_id,
        entry_id=entry_id,
        event_type=event_type,
        payload=payload,
        edited_by=edited_by,
        version=version,
    ))


def _entry_is_blocked_by_lock(entry: models.TimetableEntry) -> bool:
    return bool(entry.is_locked)


def _is_faculty_conflict_for_slot(
    db: Session,
    timetable_id: int,
    faculty_id: Optional[int],
    slot_id: int,
    subject_id: Optional[int],
) -> bool:
    if not faculty_id:
        return False
    if _is_faculty_unavailable_for_slot(db, faculty_id, slot_id):
        return True

    conflicts = db.query(models.TimetableEntry).join(models.Timetable).filter(
        models.Timetable.id != timetable_id,
        models.Timetable.status.in_(COMMITMENT_STATUSES),
        models.TimetableEntry.faculty_id == faculty_id,
        models.TimetableEntry.timeslot_id == slot_id,
    ).all()
    if not conflicts:
        return False

    for conflict in conflicts:
        if conflict.subject_id != subject_id:
            return True
    return False


def _section_has_non_overlap_entry(
    db: Session,
    timetable_id: int,
    slot_id: int,
    moving_entry_id: Optional[int] = None,
) -> bool:
    entries = db.query(models.TimetableEntry).filter(
        models.TimetableEntry.timetable_id == timetable_id,
        models.TimetableEntry.timeslot_id == slot_id,
    ).all()
    for entry in entries:
        if moving_entry_id and entry.id == moving_entry_id:
            continue
        return True
    return False


def _suggest_alternative_slots(
    db: Session,
    timetable: models.Timetable,
    entry: models.TimetableEntry,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    if not timetable.section or not timetable.section.academic_year:
        return []
    department_id = timetable.section.academic_year.department_id
    slots = _query_department_timeslots(db, department_id, include_breaks=False).order_by(models.TimeSlot.day, models.TimeSlot.start_time).all()
    suggestions: List[Dict[str, Any]] = []
    for slot in slots:
        if slot.id == entry.timeslot_id:
            continue
        if _section_has_non_overlap_entry(db, timetable.id, slot.id, moving_entry_id=entry.id):
            continue
        if _is_faculty_conflict_for_slot(db, timetable.id, entry.faculty_id, slot.id, entry.subject_id):
            continue
        suggestions.append({
            "timeslot_id": slot.id,
            "day": slot.day,
            "start_time": str(slot.start_time),
            "end_time": str(slot.end_time),
            "reason": "No faculty or section clash",
        })
        if len(suggestions) >= limit:
            break
    return suggestions

@router.post("/{timetable_id}/validate", response_model=schemas.ValidationResponse)
def validate_timetable(
    timetable_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin)
):
    tt = db.query(models.Timetable).filter(models.Timetable.id == timetable_id).first()
    if not tt:
        raise HTTPException(status_code=404, detail="Timetable not found")

    department_id = None
    if tt.section and tt.section.academic_year:
        department_id = tt.section.academic_year.department_id
    rules = _load_effective_rules(db, department_id)
    return validate_timetable_internal(tt, db, rules=rules)


def _timetable_signature(timetable: models.Timetable):
    signature = []
    for entry in timetable.entries:
        if not entry.subject_id or not entry.timeslot_id:
            continue
        if entry.subject and (entry.subject.is_elective or _is_cbcs_subject(entry.subject)):
            continue
        signature.append((entry.timeslot_id, entry.subject_id))
    signature.sort()
    return tuple(signature)


def _is_duplicate_section_timetable(timetable: models.Timetable, db: Session) -> bool:
    if not timetable.section or not timetable.section.academic_year_id:
        return False
    if hasattr(timetable.section, "independent_schedule") and not timetable.section.independent_schedule:
        return False

    current_signature = _timetable_signature(timetable)
    if not current_signature:
        return False

    peer_timetables = db.query(models.Timetable).join(models.Section).filter(
        models.Timetable.id != timetable.id,
        models.Timetable.semester == timetable.semester,
        models.Timetable.status.in_(COMMITMENT_STATUSES),
        models.Section.academic_year_id == timetable.section.academic_year_id,
    ).all()

    for peer in peer_timetables:
        if _timetable_signature(peer) == current_signature:
            return True
    return False


def _is_diversifiable_subject(subject: Optional[models.Subject]) -> bool:
    if not subject:
        return False
    if subject.is_elective:
        return False
    if _is_cbcs_subject(subject):
        return False
    return True


def _section_similarity_score(timetable: models.Timetable, db: Session) -> int:
    if not timetable.section or not timetable.section.academic_year_id:
        return 0

    peer_timetables = db.query(models.Timetable).join(models.Section).filter(
        models.Timetable.id != timetable.id,
        models.Timetable.semester == timetable.semester,
        models.Timetable.status.in_(COMMITMENT_STATUSES),
        models.Section.academic_year_id == timetable.section.academic_year_id,
    ).all()
    if not peer_timetables:
        return 0

    peer_slot_subject_keys = set()
    peer_time_subject_keys = set()
    peer_subject_day_keys = set()

    for peer in peer_timetables:
        for entry in peer.entries:
            if not _is_diversifiable_subject(entry.subject):
                continue
            if not entry.timeslot:
                continue
            slot_key = (entry.timeslot_id, entry.subject_id)
            time_key = (entry.timeslot.day, str(entry.timeslot.start_time), entry.subject_id)
            day_key = (entry.timeslot.day, entry.subject_id)
            peer_slot_subject_keys.add(slot_key)
            peer_time_subject_keys.add(time_key)
            peer_subject_day_keys.add(day_key)

    score = 0
    for entry in timetable.entries:
        if not _is_diversifiable_subject(entry.subject):
            continue
        if not entry.timeslot:
            continue
        slot_key = (entry.timeslot_id, entry.subject_id)
        time_key = (entry.timeslot.day, str(entry.timeslot.start_time), entry.subject_id)
        day_key = (entry.timeslot.day, entry.subject_id)

        if slot_key in peer_slot_subject_keys:
            score += 6
        if time_key in peer_time_subject_keys:
            score += 3
        if day_key in peer_subject_day_keys:
            score += 1

    return score


def _build_peer_timetable_payload(
    section: models.Section,
    semester: int,
    db: Session,
    exclude_timetable_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not section or not section.academic_year_id:
        return []
    if hasattr(section, "independent_schedule") and not section.independent_schedule:
        return []

    peer_query = db.query(models.Timetable).join(models.Section).filter(
        models.Timetable.semester == semester,
        models.Timetable.status.in_(COMMITMENT_STATUSES),
        models.Section.academic_year_id == section.academic_year_id,
        models.Section.id != section.id,
    )
    if exclude_timetable_id is not None:
        peer_query = peer_query.filter(models.Timetable.id != exclude_timetable_id)

    payload = []
    for peer in peer_query.all():
        entries = []
        for entry in peer.entries:
            if not _is_diversifiable_subject(entry.subject):
                continue
            if not entry.timeslot:
                continue
            entries.append({
                "subject_id": entry.subject_id,
                "timeslot_id": entry.timeslot_id,
                "day": entry.timeslot.day,
                "time": str(entry.timeslot.start_time),
            })

        if entries:
            payload.append({
                "timetable_id": peer.id,
                "section_id": peer.section_id,
                "entries": entries,
            })

    return payload


def load_faculty_commitments(
    db: Session,
    faculty_ids: Optional[List[int]] = None,
    exclude_timetable_id: Optional[int] = None,
) -> Dict[int, List[int]]:
    query = db.query(models.TimetableEntry).join(models.Timetable).filter(
        models.Timetable.status.in_(APPROVED_COMMITMENT_STATUSES),
        models.TimetableEntry.faculty_id.isnot(None),
    )
    if faculty_ids is not None:
        if not faculty_ids:
            return {}
        query = query.filter(models.TimetableEntry.faculty_id.in_(faculty_ids))
    if exclude_timetable_id is not None:
        query = query.filter(models.Timetable.id != exclude_timetable_id)

    commitments: Dict[int, List[int]] = {}
    for entry in query.all():
        commitments.setdefault(entry.faculty_id, [])
        if entry.timeslot_id not in commitments[entry.faculty_id]:
            commitments[entry.faculty_id].append(entry.timeslot_id)
    return commitments


def _load_faculty_availability(
    db: Session,
    faculty_ids: List[int],
    timeslot_ids: Optional[List[int]] = None,
) -> Dict[int, Dict[str, List[int]]]:
    availability = {
        faculty_id: {"preferred_slots": [], "unavailable_slots": []}
        for faculty_id in faculty_ids
    }
    if not faculty_ids:
        return availability

    query = db.query(models.FacultyAvailability).filter(
        models.FacultyAvailability.faculty_id.in_(faculty_ids)
    )
    if timeslot_ids is not None:
        if not timeslot_ids:
            return availability
        query = query.filter(models.FacultyAvailability.timeslot_id.in_(timeslot_ids))

    for row in query.all():
        if row.status == models.FacultyAvailabilityStatus.PREFERRED.value:
            availability.setdefault(row.faculty_id, {"preferred_slots": [], "unavailable_slots": []})["preferred_slots"].append(row.timeslot_id)
        elif row.status == models.FacultyAvailabilityStatus.UNAVAILABLE.value:
            availability.setdefault(row.faculty_id, {"preferred_slots": [], "unavailable_slots": []})["unavailable_slots"].append(row.timeslot_id)

    return availability


def _faculty_can_take_slot_for_entry(
    timetable: models.Timetable,
    entry: models.TimetableEntry,
    candidate_slot_id: int,
    db: Session,
) -> bool:
    if not entry.faculty_id:
        return True
    if _is_faculty_unavailable_for_slot(db, entry.faculty_id, candidate_slot_id):
        return False

    conflicting_entries = db.query(models.TimetableEntry).join(models.Timetable).filter(
        models.Timetable.id != timetable.id,
        models.Timetable.status.in_(COMMITMENT_STATUSES),
        models.TimetableEntry.faculty_id == entry.faculty_id,
        models.TimetableEntry.timeslot_id == candidate_slot_id,
    ).all()
    if not conflicting_entries:
        return True

    current_subject = entry.subject
    if not current_subject or not _is_cbcs_subject(current_subject):
        return False

    for conflict in conflicting_entries:
        if conflict.subject_id != entry.subject_id:
            return False
    return True


def _attempt_duplicate_repair(
    timetable: models.Timetable,
    db: Session,
    timeslots_db: List[models.TimeSlot],
) -> bool:
    if not _is_duplicate_section_timetable(timetable, db):
        return True

    ordered_slots = sorted(
        timeslots_db,
        key=lambda slot: (DAY_ORDER.get(slot.day, 99), slot.start_time, slot.id),
    )
    if not ordered_slots:
        return False

    slot_ids = [slot.id for slot in ordered_slots]
    rotation = (timetable.section_id or 0) % len(slot_ids)
    rotated_slot_ids = slot_ids[rotation:] + slot_ids[:rotation]

    movable_entries = [entry for entry in timetable.entries if not entry.is_locked]
    if not movable_entries:
        return False

    occupied_slot_ids = {entry.timeslot_id for entry in timetable.entries if entry.timeslot_id}

    for entry in movable_entries:
        original_slot_id = entry.timeslot_id
        for candidate_slot_id in rotated_slot_ids:
            if candidate_slot_id == original_slot_id:
                continue
            if candidate_slot_id in occupied_slot_ids:
                continue
            if not _faculty_can_take_slot_for_entry(timetable, entry, candidate_slot_id, db):
                continue

            entry.timeslot_id = candidate_slot_id
            occupied_slot_ids.remove(original_slot_id)
            occupied_slot_ids.add(candidate_slot_id)
            db.flush()

            if not _is_duplicate_section_timetable(timetable, db):
                return True

            entry.timeslot_id = original_slot_id
            occupied_slot_ids.remove(candidate_slot_id)
            occupied_slot_ids.add(original_slot_id)
            db.flush()

    # If all slots are occupied, try swapping two movable entries.
    for left_idx in range(len(movable_entries)):
        left = movable_entries[left_idx]
        left_subject = left.subject
        if left_subject and (left_subject.is_elective or _is_cbcs_subject(left_subject)):
            continue

        for right_idx in range(left_idx + 1, len(movable_entries)):
            right = movable_entries[right_idx]
            right_subject = right.subject
            if right_subject and (right_subject.is_elective or _is_cbcs_subject(right_subject)):
                continue

            if left.timeslot_id == right.timeslot_id:
                continue

            left_original = left.timeslot_id
            right_original = right.timeslot_id
            if not _faculty_can_take_slot_for_entry(timetable, left, right_original, db):
                continue
            if not _faculty_can_take_slot_for_entry(timetable, right, left_original, db):
                continue

            left.timeslot_id = right_original
            right.timeslot_id = left_original
            db.flush()

            if not _is_duplicate_section_timetable(timetable, db):
                return True

            left.timeslot_id = left_original
            right.timeslot_id = right_original
            db.flush()

    return False


def validate_timetable_internal(timetable: models.Timetable, db: Session, rules: Optional[Dict[str, Any]] = None):
    rules = rules or _default_rules()
    errors = []
    warnings = []
    error_slots = []
    warning_slots = []
    
    other_entries = db.query(models.TimetableEntry).join(models.Timetable).filter(
        models.Timetable.id != timetable.id,
        models.Timetable.status.in_(COMMITMENT_STATUSES)
    ).all()
    
    faculty_slots = {}
    approved_faculty_slots = {}
    for e in other_entries:
        if e.faculty_id:
            faculty_slots.setdefault(e.faculty_id, {}).setdefault(e.timeslot_id, []).append(e)
            if e.timetable and e.timetable.status in APPROVED_COMMITMENT_STATUSES:
                approved_faculty_slots.setdefault(e.faculty_id, {}).setdefault(e.timeslot_id, []).append(e)
            
    current_faculty_ids = sorted({entry.faculty_id for entry in timetable.entries if entry.faculty_id})
    current_timeslot_ids = sorted({entry.timeslot_id for entry in timetable.entries if entry.timeslot_id})
    unavailable_by_faculty: Dict[int, set] = {}
    if current_faculty_ids and current_timeslot_ids:
        availability_rows = db.query(models.FacultyAvailability).filter(
            models.FacultyAvailability.faculty_id.in_(current_faculty_ids),
            models.FacultyAvailability.timeslot_id.in_(current_timeslot_ids),
            models.FacultyAvailability.status == models.FacultyAvailabilityStatus.UNAVAILABLE.value,
        ).all()
        for row in availability_rows:
            unavailable_by_faculty.setdefault(row.faculty_id, set()).add(row.timeslot_id)

    subject_days = {}
    faculty_daily_load = {}
    section_slots = {}
    
    for entry in timetable.entries:
        ts = db.query(models.TimeSlot).get(entry.timeslot_id)
        if not ts: continue

            
        if entry.faculty_id:
            if entry.timeslot_id in unavailable_by_faculty.get(entry.faculty_id, set()):
                fac = db.query(models.Faculty).get(entry.faculty_id)
                errors.append(
                    f"Faculty availability violation: {fac.name if fac else entry.faculty_id} is unavailable at {ts.day} {ts.start_time}."
                )
                error_slots.append(entry.timeslot_id)

            if entry.faculty_id in faculty_slots and entry.timeslot_id in faculty_slots[entry.faculty_id]:
                conflicting_entries = faculty_slots[entry.faculty_id][entry.timeslot_id]
                if not all(_entries_share_cbcs_session(entry, existing) for existing in conflicting_entries):
                    fac = db.query(models.Faculty).get(entry.faculty_id)
                    if entry.timeslot_id in approved_faculty_slots.get(entry.faculty_id, {}):
                        errors.append(
                            f"Faculty commitment conflict: {fac.name if fac else ''} already has an approved timetable at {ts.day} {ts.start_time}."
                        )
                    else:
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

    if _is_duplicate_section_timetable(timetable, db):
        errors.append("Section uniqueness conflict: This section timetable duplicates another section in the same year/semester.")
                
    for subject_id, days in subject_days.items():
        for day, count in days.items():
            sub = db.query(models.Subject).get(subject_id)
            base_subject_cap = int(rules.get("max_same_subject_per_day", 2) or 2)
            allowed_same_day = max(base_subject_cap, int(getattr(sub, "continuous_hours", 1) or 1))
            if count > allowed_same_day:
                warnings.append(f"Uneven distribution: Subject '{sub.code if sub else subject_id}' scheduled {count} times on {day}.")
                # Note: We aren't capturing the specific slot IDs for this warning easily here, but that's okay for now.
                
    for fid, days in faculty_daily_load.items():
        for day, count in days.items():
            max_daily_faculty_load_warn = int(rules.get("max_daily_faculty_load_warn", 4) or 4)
            if count > max_daily_faculty_load_warn:
                fac = db.query(models.Faculty).get(fid)
                warnings.append(f"Faculty overloaded: '{fac.name if fac else fid}' teaches {count} classes on {day}.")
                
    status = "FAIL" if errors else "PASS"
    return {"status": status, "errors": errors, "warnings": warnings, "error_slots": list(set(error_slots)), "warning_slots": list(set(warning_slots))}

@router.post("/generate", response_model=schemas.Timetable)
def generate_timetable(
    request: schemas.GenerateTimetableRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(auth.require_admin)
):
    try:
        # 1. Fetch Section
        section = db.query(models.Section).get(request.section_id)
        if not section:
            raise HTTPException(status_code=404, detail="Section not found")
            
        academic_year = section.academic_year
        department_id = academic_year.department_id
        effective_rules = _load_effective_rules(db, department_id)
        department_name = academic_year.department.name if academic_year and academic_year.department else department_id
        logger.info(
            "Timetable generation started: section_id=%s, section=%s, department=%s, semester=%s",
            section.id,
            section.name,
            department_name,
            request.semester,
        )
        
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
        logger.info(
            "Generation subject selection: section_id=%s, semester=%s, subjects=%s",
            section.id,
            request.semester,
            len(subjects_db),
        )

        # 3. Fetch TimeSlots
        timeslots_db = _query_department_timeslots(db, department_id, include_breaks=False).all()
        if not timeslots_db:
            raise HTTPException(status_code=400, detail="Build the Department Day Schedule before generating timetables")

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

        new_version = existing_tt.version + 1 if existing_tt else 1
        new_timetable = models.Timetable(
            section_id=request.section_id,
            semester=request.semester,
            status="GENERATED",
            is_active=False,
            version=new_version,
            generated_version=new_version,
            edited_version=0,
            approved_version=0
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
        missing_faculty_subjects = [
            f"{s.code or s.id}:{s.name or ''}".strip()
            for s in subjects_db
            if not subject_faculty_ids.get(s.id)
        ]
        if missing_faculty_subjects:
            logger.warning(
                "Generation has subjects without faculty assignments: section_id=%s, semester=%s, count=%s, subjects=%s",
                section.id,
                request.semester,
                len(missing_faculty_subjects),
                missing_faculty_subjects,
            )
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

        # Reuse already generated CBCS slots for shared subjects.
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
        shared_locked_slots = sum(
            1 for entries in locked_entries_by_slot.values() if len(entries) > 1
        )
        logger.info(
            "Locked slot preparation complete: section_id=%s, locked_entries=%s, unique_locked_slots=%s, shared_locked_slots=%s",
            section.id,
            len(locked_slots_payload),
            len(locked_slot_ids),
            shared_locked_slots,
        )

        # 5. Prepare Data for AI Engine
        AI_ENGINE_URL = os.getenv("AI_ENGINE_URL", "http://localhost:8001")
        
        subjects_payload = []
        faculty_ids = set()
        for s in subjects_db:
            fid = subject_faculty_ids.get(s.id)
            if fid: faculty_ids.add(fid)
                
            subjects_payload.append({
                "id": s.id,
                "name": s.name,
                "weekly_hours": s.weekly_hours,
                "credits": s.weekly_hours, 
                "continuous_hours": s.continuous_hours,
                "subject_type": s.subject_type or "THEORY",
                "faculty_id": fid,
                "is_elective": s.is_elective,
                "elective_group_id": s.elective_group_id,
                "is_cbcs_shared": _is_cbcs_subject(s),
            })

        faculty_id_list = sorted(faculty_ids)
        faculty_db = db.query(models.Faculty).filter(models.Faculty.id.in_(faculty_id_list)).all()
        faculty_payload = [{"id": f.id, "name": f.name} for f in faculty_db]
        timeslots_db_all = _query_department_timeslots(db, department_id, include_breaks=True).all()
        timeslots_payload = [{"id": t.id, "day": t.day, "time": str(t.start_time), "end_time": str(t.end_time), "is_break": t.is_break} for t in timeslots_db_all]
        timeslot_ids = [t.id for t in timeslots_db_all]
        locked_hours_by_subject = {}
        for locked in locked_slots_payload:
            sid = locked.get("subject_id")
            if sid is not None:
                locked_hours_by_subject[sid] = locked_hours_by_subject.get(sid, 0) + 1
        gross_required_hours = sum(int(s.weekly_hours or 0) for s in subjects_db)
        net_required_hours = sum(
            max(0, int(s.weekly_hours or 0) - locked_hours_by_subject.get(s.id, 0))
            for s in subjects_db
        )
        teaching_slots_count = sum(1 for t in timeslots_payload if not t.get("is_break"))
        
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
        
        faculty_availability = _load_faculty_availability(db, faculty_id_list, timeslot_ids)
        approved_commitments = load_faculty_commitments(
            db=db,
            faculty_ids=faculty_id_list,
            exclude_timetable_id=new_timetable.id,
        )
        faculty_preferences = {f.id: {"max_hours": f.max_hours_per_week, "preferred_slots": f.preferred_slots} for f in faculty_db}
        peer_timetables_payload = _build_peer_timetable_payload(
            section=section,
            semester=request.semester,
            db=db,
            exclude_timetable_id=new_timetable.id,
        )

        payload = {
            "semester": request.semester,
            "subjects": subjects_payload,
            "faculty": faculty_payload,
            "timeslots": timeslots_payload,
            "locked_slots": locked_slots_payload,
            "constraints": {
                "prior_commitments": existing_commitments,
                "prior_commitment_entries": prior_commitment_entries,
                "approved_commitments": approved_commitments,
                "faculty_availability": faculty_availability,
                "faculty_preferences": faculty_preferences,
                "rules": effective_rules,
                "peer_timetables": peer_timetables_payload,
                "enforce_distinct_sections": False,
                "coverage_mode": "fill_remaining",
                "allow_partial_schedule": True,
                "allow_partial_schedule_fallback": True,
                "candidate_limit": 15,
            }
        }
        base_random_seed = random.SystemRandom().randint(1, 1_000_000_000)
        payload["constraints"]["random_seed"] = base_random_seed
        logger.info(
            "AI payload prepared: section_id=%s, semester=%s, subjects=%s, faculty=%s, teaching_slots=%s, gross_required=%s, net_required=%s, locked_entries=%s, unique_locked_slots=%s, prior_commitment_faculty=%s, approved_commitment_faculty=%s, peer_timetables=%s, seed=%s",
            section.id,
            request.semester,
            len(subjects_payload),
            len(faculty_payload),
            teaching_slots_count,
            gross_required_hours,
            net_required_hours,
            len(locked_slots_payload),
            len(locked_slot_ids),
            len(existing_commitments),
            len(approved_commitments),
            len(peer_timetables_payload),
            base_random_seed,
        )
        for faculty in faculty_db:
            availability = faculty_availability.get(faculty.id, {})
            logger.info(
                "Faculty availability summary before solve: faculty_id=%s, name=%s, preferred=%s, unavailable=%s, commitments=%s",
                faculty.id,
                faculty.name,
                len(availability.get("preferred_slots", [])),
                len(availability.get("unavailable_slots", [])),
                len(existing_commitments.get(faculty.id, [])),
            )

        # 6. Call AI Engine - Orchestration Only, NO local fallbacks
        import urllib.request
        import urllib.error
        
        schedule = None
        ai_result = {}
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(f"{AI_ENGINE_URL}/optimize", data=data, headers={'Content-Type': 'application/json'})
            
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    ai_result = json.loads(response.read().decode('utf-8'))
                    if ai_result.get("status") == "success":
                        schedule = ai_result.get("schedule", [])
            
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode('utf-8')
            try:
                err_detail = json.loads(err_msg).get("detail", err_msg)
            except Exception:
                err_detail = err_msg
            db.rollback()
            raise HTTPException(status_code=e.code, detail=f"AI Engine Optimization Failed: {err_detail}")
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"AI Engine Connection Error: {str(e)}")

        if schedule is None:
            db.rollback()
            raise HTTPException(status_code=500, detail="AI Engine failed to generate a valid timetable.")
        coverage_report = ai_result.get("coverage_report") or {}
        logger.info(
            "AI generation result: section_id=%s, timetable_id=%s, schedule_entries=%s, solver_status=%s, unmet_hours=%s, empty_teaching_slots=%s",
            section.id,
            new_timetable.id,
            len(schedule),
            (ai_result.get("constraint_summary") or "").splitlines()[0] if ai_result.get("constraint_summary") else "UNKNOWN",
            coverage_report.get("unmet_hours"),
            coverage_report.get("empty_teaching_slots"),
        )
        for subject_coverage in coverage_report.get("subjects", []):
            if subject_coverage.get("unmet_hours") or subject_coverage.get("over_scheduled_hours"):
                logger.warning(
                    "AI subject coverage: section_id=%s, subject_id=%s, required=%s, scheduled=%s, locked=%s, unmet=%s, over=%s",
                    section.id,
                    subject_coverage.get("subject_id"),
                    subject_coverage.get("required_hours"),
                    subject_coverage.get("scheduled_hours"),
                    subject_coverage.get("locked_hours"),
                    subject_coverage.get("unmet_hours"),
                    subject_coverage.get("over_scheduled_hours"),
                )
        scheduled_slots_by_faculty: Dict[int, set] = {}
        for item in schedule:
            item_faculty_id = item.get("faculty_id")
            if item_faculty_id:
                scheduled_slots_by_faculty.setdefault(item_faculty_id, set()).add(item.get("timeslot_id"))
        for faculty in faculty_db:
            scheduled_slots = scheduled_slots_by_faculty.get(faculty.id, set())
            availability = faculty_availability.get(faculty.id, {})
            preferred_slots = set(availability.get("preferred_slots", []))
            unavailable_slots = set(availability.get("unavailable_slots", []))
            commitment_slots = set(existing_commitments.get(faculty.id, []))
            logger.info(
                "Faculty utilization after solve: faculty_id=%s, name=%s, preferred_used=%s/%s, unavailable_violations=%s, commitment_violations=%s",
                faculty.id,
                faculty.name,
                len(scheduled_slots & preferred_slots),
                len(preferred_slots),
                len(scheduled_slots & unavailable_slots),
                len(scheduled_slots & commitment_slots),
            )

        # 7. Apply the schedule directly to the database
        section_entries_by_slot = {
            ts_id: list(entries) for ts_id, entries in locked_entries_by_slot.items()
        }
        skipped_schedule_items = 0
        for item in schedule:
            sub_obj = db.query(models.Subject).get(item['subject_id'])
            slot_entries = section_entries_by_slot.get(item['timeslot_id'], [])
            if slot_entries and not can_share_slot_with_existing(sub_obj, slot_entries, item['timeslot_id']):
                skipped_schedule_items += 1
                logger.warning(
                    "Skipping AI entry because it conflicts with locked/placed entries: timetable_id=%s, subject_id=%s, timeslot_id=%s",
                    new_timetable.id,
                    item.get("subject_id"),
                    item.get("timeslot_id"),
                )
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
        if _is_duplicate_section_timetable(new_timetable, db):
            logger.warning(
                "Generated timetable duplicates a peer before repair: timetable_id=%s, section_id=%s",
                new_timetable.id,
                section.id,
            )
            if _attempt_duplicate_repair(new_timetable, db, timeslots_db):
                logger.info(
                    "Duplicate timetable repaired by moving/swapping non-locked entries: timetable_id=%s",
                    new_timetable.id,
                )
            else:
                logger.warning(
                    "Duplicate timetable repair could not find a legal move: timetable_id=%s",
                    new_timetable.id,
                )

        logger.info(
            "AI schedule applied: timetable_id=%s, requested_entries=%s, skipped_entries=%s, db_entries=%s",
            new_timetable.id,
            len(schedule),
            skipped_schedule_items,
            len(new_timetable.entries),
        )

        # Final validate check
        final_validation = validate_timetable_internal(new_timetable, db, rules=effective_rules)
        logger.info(
            "Final timetable validation: timetable_id=%s, status=%s, errors=%s, warnings=%s",
            new_timetable.id,
            final_validation["status"],
            len(final_validation["errors"]),
            len(final_validation["warnings"]),
        )
        if final_validation["status"] != "PASS":
            error_details = "; ".join(final_validation["errors"])
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Validation failed after generation: {error_details}")

        _log_edit_event(
            db=db,
            timetable_id=new_timetable.id,
            event_type="generation",
            payload={
                "section_id": new_timetable.section_id,
                "semester": new_timetable.semester,
                "version": new_timetable.version,
                "entry_count": len(schedule)
            },
            edited_by=getattr(current_user, "id", None),
            version=new_timetable.version or 1,
        )
        db.commit()
        db.refresh(new_timetable)
        return new_timetable

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-all")
def generate_all_timetables(
    department_id: Optional[int] = None,
    semester: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin)
):
    """
    Generates timetables for ALL sections across all departments using available subjects.
    Returns summary of generation results.
    """
    # Fetch sections (optionally scope to one department)
    sections_query = db.query(models.Section)
    if department_id is not None:
        sections_query = sections_query.join(models.AcademicYear).filter(
            models.AcademicYear.department_id == department_id
        )
    all_sections = sections_query.all()
    
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
                if semester is not None and sem != semester:
                    continue
                total_attempts += 1
                try:
                    # Leverage the exact same AI generation logic as single generation
                    gen_req = schemas.GenerateTimetableRequest(
                        section_id=section.id,
                        semester=sem
                    )
                    
                    # Generate the timetable (this will throw an HTTPException on clash/error)
                    new_timetable = generate_timetable(gen_req, db)
                    
                    # Bulk generation defaults to GENERATED status
                    new_timetable.status = "GENERATED"
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

# --- Visual Board & Editing ---

@router.get("/board", response_model=schemas.VisualBoardResponse)
def get_visual_board(
    department_id: int,
    semester: Optional[int] = None,
    academic_year_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin),
):
    tt_query = db.query(models.Timetable).join(models.Section).join(models.AcademicYear).filter(
        models.AcademicYear.department_id == department_id
    )
    if semester is not None:
        tt_query = tt_query.filter(models.Timetable.semester == semester)
    if academic_year_id is not None:
        tt_query = tt_query.filter(models.Section.academic_year_id == academic_year_id)

    timetables = tt_query.order_by(
        models.AcademicYear.level.asc(),
        models.Section.name.asc(),
        models.Timetable.created_at.desc(),
    ).all()

    latest_by_section_semester: Dict[tuple, models.Timetable] = {}
    for tt in timetables:
        key = (tt.section_id, tt.semester)
        current = latest_by_section_semester.get(key)
        if not current or (tt.version or 0) > (current.version or 0):
            latest_by_section_semester[key] = tt

    slots = _query_department_timeslots(db, department_id, include_breaks=True).order_by(
        models.TimeSlot.day.asc(),
        models.TimeSlot.start_time.asc(),
    ).all()

    return {
        "department_id": department_id,
        "semester": semester,
        "academic_year_id": academic_year_id,
        "time_slots": slots,
        "timetables": list(latest_by_section_semester.values()),
    }


@router.put("/edit", response_model=schemas.TimetableEditResponse)
def edit_timetable_entry(
    request: schemas.TimetableEditRequest,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin),
):
    entry = db.query(models.TimetableEntry).filter(models.TimetableEntry.id == request.entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Timetable entry not found")
    if entry.timeslot_id != request.source_slot:
        raise HTTPException(status_code=400, detail="Source slot mismatch")
    if _entry_is_blocked_by_lock(entry) and request.action in ("move", "swap", "delete"):
        raise HTTPException(status_code=400, detail="Locked entries cannot be moved or deleted")

    timetable = db.query(models.Timetable).filter(models.Timetable.id == entry.timetable_id).first()
    if not timetable:
        raise HTTPException(status_code=404, detail="Timetable not found")

    source_slot = entry.timeslot_id
    source_room = entry.room_id
    source_lock = entry.is_locked
    source_version = entry.version or 1
    changed_ids = [entry.id]
    created_entry: Optional[models.TimetableEntry] = None
    swap_entry: Optional[models.TimetableEntry] = None
    swap_original_slot: Optional[int] = None

    try:
        if request.action == "lock":
            entry.is_locked = True
            entry.is_manual = True
            entry.edited_by = current_user.user_id
            entry.version = source_version + 1
        elif request.action == "delete":
            db.delete(entry)
        elif request.action == "duplicate":
            if _section_has_non_overlap_entry(db, timetable.id, request.target_slot):
                suggestions = _suggest_alternative_slots(db, timetable, entry)
                raise HTTPException(status_code=400, detail={
                    "message": "Target slot already has an entry in this section",
                    "suggestions": suggestions,
                })
            if _is_faculty_conflict_for_slot(db, timetable.id, entry.faculty_id, request.target_slot, entry.subject_id):
                suggestions = _suggest_alternative_slots(db, timetable, entry)
                raise HTTPException(status_code=400, detail={
                    "message": "Faculty clash at target slot",
                    "suggestions": suggestions,
                })
            created_entry = models.TimetableEntry(
                timetable_id=timetable.id,
                subject_id=entry.subject_id,
                faculty_id=entry.faculty_id,
                timeslot_id=request.target_slot,
                room_id=request.target_room,
                is_locked=False,
                is_manual=True,
                edited_by=current_user.user_id,
                version=(entry.version or 1) + 1,
                created_by=models.EntryCreator.ADMIN.value,
            )
            db.add(created_entry)
            db.flush()
            changed_ids.append(created_entry.id)
        elif request.action == "swap":
            swap_entry = db.query(models.TimetableEntry).filter(
                models.TimetableEntry.timetable_id == timetable.id,
                models.TimetableEntry.timeslot_id == request.target_slot,
            ).first()
            if not swap_entry:
                raise HTTPException(status_code=400, detail="No target entry found to swap with")
            if _entry_is_blocked_by_lock(swap_entry):
                raise HTTPException(status_code=400, detail="Cannot swap with locked entry")

            if _is_faculty_conflict_for_slot(db, timetable.id, entry.faculty_id, request.target_slot, entry.subject_id):
                raise HTTPException(status_code=400, detail="Faculty clash for source entry at target slot")
            if _is_faculty_conflict_for_slot(db, timetable.id, swap_entry.faculty_id, source_slot, swap_entry.subject_id):
                raise HTTPException(status_code=400, detail="Faculty clash for target entry at source slot")

            swap_original_slot = swap_entry.timeslot_id
            entry.timeslot_id = request.target_slot
            entry.room_id = request.target_room
            entry.version = source_version + 1
            entry.is_manual = True
            entry.edited_by = current_user.user_id

            swap_entry.timeslot_id = source_slot
            swap_entry.version = (swap_entry.version or 1) + 1
            swap_entry.is_manual = True
            swap_entry.edited_by = current_user.user_id
            changed_ids.append(swap_entry.id)
        else:
            if _section_has_non_overlap_entry(db, timetable.id, request.target_slot, moving_entry_id=entry.id):
                suggestions = _suggest_alternative_slots(db, timetable, entry)
                raise HTTPException(status_code=400, detail={
                    "message": "Target slot already has an entry in this section",
                    "suggestions": suggestions,
                })
            if _is_faculty_conflict_for_slot(db, timetable.id, entry.faculty_id, request.target_slot, entry.subject_id):
                suggestions = _suggest_alternative_slots(db, timetable, entry)
                raise HTTPException(status_code=400, detail={
                    "message": "Faculty clash at target slot",
                    "suggestions": suggestions,
                })

            entry.timeslot_id = request.target_slot
            entry.room_id = request.target_room
            entry.version = source_version + 1
            entry.is_manual = True
            entry.edited_by = current_user.user_id

        db.flush()

        rules = _default_rules()
        if timetable.section and timetable.section.academic_year:
            rules = _load_effective_rules(db, timetable.section.academic_year.department_id)
        validation = validate_timetable_internal(timetable, db, rules=rules)

        suggestions: List[Dict[str, Any]] = []
        if validation["status"] != "PASS":
            if entry and request.action != "delete":
                suggestions = _suggest_alternative_slots(db, timetable, entry)
            # rollback data mutation
            db.rollback()
            return {
                "status": "INVALID",
                "message": "Move failed validation",
                "validation": validation,
                "suggestions": suggestions,
                "changed_entry_ids": changed_ids,
            }

        if not request.apply:
            db.rollback()
            return {
                "status": "VALID",
                "message": "Move is valid (preview only)",
                "validation": validation,
                "suggestions": [],
                "changed_entry_ids": changed_ids,
            }

        _log_edit_event(
            db=db,
            timetable_id=timetable.id,
            entry_id=entry.id if entry else None,
            event_type=request.action,
            payload={
                "source_slot": request.source_slot,
                "target_slot": request.target_slot,
                "target_room": request.target_room,
                "changed_entry_ids": changed_ids,
            },
            edited_by=current_user.user_id,
            version=timetable.version or 1,
        )
        timetable.status = "EDITED"
        timetable.edited_version = (timetable.edited_version or 0) + 1
        db.flush()
        db.commit()

        # Log manual edit to learning layer
        from learning_layer import log_learning_event
        log_learning_event(
            event_type="manual_edit",
            timetable_id=timetable.id,
            payload={
                "action": request.action,
                "entry_id": request.entry_id,
                "source_slot": request.source_slot,
                "target_slot": request.target_slot,
                "target_room": request.target_room,
                "changed_entry_ids": changed_ids,
            }
        )

        return {
            "status": "APPLIED",
            "message": "Edit applied",
            "validation": validation,
            "suggestions": [],
            "changed_entry_ids": changed_ids,
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to edit timetable: {exc}")


@router.post("/{timetable_id}/approve", response_model=schemas.Timetable)
def approve_timetable(
    timetable_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin)
):
    timetable = db.query(models.Timetable).filter(models.Timetable.id == timetable_id).first()
    if not timetable:
        raise HTTPException(status_code=404, detail="Timetable not found")
        
    # Archive/Deactivate other timetables for the same section and semester
    other_timetables = db.query(models.Timetable).filter(
        models.Timetable.section_id == timetable.section_id,
        models.Timetable.semester == timetable.semester,
        models.Timetable.id != timetable_id
    ).all()
    
    for ot in other_timetables:
        ot.status = "ARCHIVED"
        ot.is_active = False
        
    timetable.status = "APPROVED"
    timetable.is_active = True
    timetable.approved_version = (timetable.approved_version or 0) + 1
    
    _log_edit_event(
        db=db,
        timetable_id=timetable.id,
        event_type="approve",
        payload={
            "section_id": timetable.section_id,
            "semester": timetable.semester,
            "approved_version": timetable.approved_version,
        },
        edited_by=current_user.user_id,
        version=timetable.version or 1,
    )
    
    db.commit()

    # Log approved timetable to learning layer
    from learning_layer import log_learning_event
    logged_entries = [
        {
            "subject_id": e.subject_id,
            "subject_code": e.subject.code if e.subject else None,
            "faculty_id": e.faculty_id,
            "faculty_name": e.faculty.name if e.faculty else None,
            "timeslot_id": e.timeslot_id,
            "day": e.timeslot.day if e.timeslot else None,
            "start_time": str(e.timeslot.start_time) if e.timeslot else None,
            "is_locked": e.is_locked
        }
        for e in timetable.entries
    ]
    log_learning_event(
        event_type="accepted",
        timetable_id=timetable.id,
        payload={
            "section_id": timetable.section_id,
            "semester": timetable.semester,
            "approved_version": timetable.approved_version,
            "entries": logged_entries
        }
    )

    return get_timetable(timetable_id, db, current_user)


@router.get("/{timetable_id}/history", response_model=List[schemas.TimetableEditEvent])
def get_timetable_history(
    timetable_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin),
):
    return db.query(models.TimetableEditEvent).filter(
        models.TimetableEditEvent.timetable_id == timetable_id
    ).order_by(models.TimetableEditEvent.created_at.desc()).limit(200).all()

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
        "version": tt.version,
        "status": tt.status,
        "created_at": tt.created_at,
        "section": tt.section,
        "entries": list(tt.entries),
        "time_slots": _query_department_timeslots(
            db,
            tt.section.academic_year.department_id,
            include_breaks=True,
        ).all() if tt.section and tt.section.academic_year else [],
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
        db.query(models.TimetableEditEvent).delete(synchronize_session=False)
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
