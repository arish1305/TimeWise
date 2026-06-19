from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

import auth
import models
import schemas
from database import get_db

router = APIRouter(
    prefix="/faculty",
    tags=["faculty-availability"],
)


def _get_faculty_or_404(db: Session, faculty_id: int) -> models.Faculty:
    faculty = db.query(models.Faculty).options(
        selectinload(models.Faculty.departments)
    ).filter(models.Faculty.id == faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return faculty


def _faculty_timeslot_query(db: Session, faculty: models.Faculty, department_id: Optional[int] = None):
    query = db.query(models.TimeSlot).filter(models.TimeSlot.is_break == False)
    if department_id is not None:
        return query.filter(models.TimeSlot.department_id == department_id)

    department_ids = [department.id for department in faculty.departments]
    if department_ids:
        return query.filter(models.TimeSlot.department_id.in_(department_ids))
    return query


@router.get("/{faculty_id}/availability", response_model=schemas.FacultyAvailabilityResponse)
def get_faculty_availability(
    faculty_id: int,
    department_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin),
):
    faculty = _get_faculty_or_404(db, faculty_id)
    timeslots = _faculty_timeslot_query(db, faculty, department_id).order_by(
        models.TimeSlot.day,
        models.TimeSlot.start_time,
    ).all()

    availability_rows = db.query(models.FacultyAvailability).filter(
        models.FacultyAvailability.faculty_id == faculty_id,
        models.FacultyAvailability.timeslot_id.in_([slot.id for slot in timeslots]) if timeslots else False,
    ).all()
    status_by_slot = {row.timeslot_id: row.status for row in availability_rows}

    return {
        "faculty_id": faculty_id,
        "entries": [
            {
                "timeslot_id": slot.id,
                "status": status_by_slot.get(slot.id, models.FacultyAvailabilityStatus.AVAILABLE.value),
                "day": slot.day,
                "start_time": slot.start_time,
                "end_time": slot.end_time,
                "is_break": bool(slot.is_break),
                "department_id": slot.department_id,
            }
            for slot in timeslots
        ],
    }


@router.post("/{faculty_id}/availability", response_model=schemas.FacultyAvailabilityResponse)
def update_faculty_availability(
    faculty_id: int,
    payload: schemas.FacultyAvailabilityBulkUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin),
):
    faculty = _get_faculty_or_404(db, faculty_id)
    timeslot_ids = [entry.timeslot_id for entry in payload.entries]
    duplicate_timeslot_ids = sorted({timeslot_id for timeslot_id in timeslot_ids if timeslot_ids.count(timeslot_id) > 1})
    if duplicate_timeslot_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Duplicate timeslot_id values in availability payload: {duplicate_timeslot_ids}",
        )

    if timeslot_ids:
        existing_timeslot_ids = {
            row[0]
            for row in db.query(models.TimeSlot.id).filter(models.TimeSlot.id.in_(timeslot_ids)).all()
        }
        missing_timeslot_ids = sorted(set(timeslot_ids) - existing_timeslot_ids)
        if missing_timeslot_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Timeslot IDs not found: {missing_timeslot_ids}",
            )

    existing_rows = {
        row.timeslot_id: row
        for row in db.query(models.FacultyAvailability).filter(
            models.FacultyAvailability.faculty_id == faculty_id,
            models.FacultyAvailability.timeslot_id.in_(timeslot_ids) if timeslot_ids else False,
        ).all()
    }

    for entry in payload.entries:
        status = entry.status.value if hasattr(entry.status, "value") else str(entry.status)
        existing = existing_rows.get(entry.timeslot_id)

        if status == models.FacultyAvailabilityStatus.AVAILABLE.value:
            if existing:
                db.delete(existing)
            continue

        if existing:
            existing.status = status
            existing.updated_at = datetime.utcnow()
        else:
            db.add(models.FacultyAvailability(
                faculty_id=faculty_id,
                timeslot_id=entry.timeslot_id,
                status=status,
            ))

    db.commit()
    return get_faculty_availability(
        faculty_id=faculty_id,
        department_id=None,
        db=db,
        current_user=current_user,
    )


@router.delete("/{faculty_id}/availability")
def reset_faculty_availability(
    faculty_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth.require_admin),
):
    _get_faculty_or_404(db, faculty_id)
    deleted = db.query(models.FacultyAvailability).filter(
        models.FacultyAvailability.faculty_id == faculty_id
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": "Faculty availability reset to default", "deleted": deleted}
