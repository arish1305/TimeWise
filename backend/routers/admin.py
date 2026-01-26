from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import database, models, schemas, auth

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(auth.get_current_user)] # Protect all admin routes
)

# --- Departments ---
@router.post("/departments", response_model=schemas.Department)
def create_department(dept: schemas.DepartmentCreate, db: Session = Depends(database.get_db)):
    db_dept = models.Department(
        name=dept.name,
        code=dept.code
    )
    db.add(db_dept)
    db.commit()
    db.refresh(db_dept)
    return db_dept

@router.get("/departments", response_model=List[schemas.Department])
def read_departments(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.Department).offset(skip).limit(limit).all()

@router.put("/departments/{dept_id}", response_model=schemas.Department)
def update_department(dept_id: int, dept: schemas.DepartmentCreate, db: Session = Depends(database.get_db)):
    db_dept = db.query(models.Department).filter(models.Department.id == dept_id).first()
    if not db_dept:
        raise HTTPException(status_code=404, detail="Department not found")
    db_dept.name = dept.name
    db_dept.code = dept.code
    db.commit()
    db.refresh(db_dept)
    return db_dept

@router.delete("/departments/{dept_id}")
def delete_department(dept_id: int, db: Session = Depends(database.get_db)):
    dept = db.query(models.Department).filter(models.Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    db.delete(dept)
    db.commit()
    return {"message": "Department deleted"}

# --- Academic Years ---
@router.post("/academic-years", response_model=schemas.AcademicYear)
def create_academic_year(year: schemas.AcademicYearCreate, db: Session = Depends(database.get_db)):
    db_year = models.AcademicYear(**year.dict())
    db.add(db_year)
    db.commit()
    db.refresh(db_year)
    return db_year

@router.get("/academic-years", response_model=List[schemas.AcademicYear])
def read_academic_years(department_id: int = None, db: Session = Depends(database.get_db)):
    q = db.query(models.AcademicYear)
    if department_id:
        q = q.filter(models.AcademicYear.department_id == department_id)
    return q.all()

@router.put("/academic-years/{year_id}", response_model=schemas.AcademicYear)
def update_academic_year(year_id: int, year: schemas.AcademicYearCreate, db: Session = Depends(database.get_db)):
    db_year = db.query(models.AcademicYear).filter(models.AcademicYear.id == year_id).first()
    if not db_year:
        raise HTTPException(status_code=404, detail="Academic Year not found")
    db_year.name = year.name
    db_year.level = year.level
    db.commit()
    db.refresh(db_year)
    return db_year

@router.delete("/academic-years/{year_id}")
def delete_academic_year(year_id: int, db: Session = Depends(database.get_db)):
    year = db.query(models.AcademicYear).filter(models.AcademicYear.id == year_id).first()
    if not year:
        raise HTTPException(status_code=404, detail="Academic Year not found")
    db.delete(year)
    db.commit()
    return {"message": "Academic Year deleted"}

# --- Sections ---
@router.post("/sections", response_model=schemas.Section)
def create_section(section: schemas.SectionCreate, db: Session = Depends(database.get_db)):
    db_section = models.Section(**section.dict())
    db.add(db_section)
    db.commit()
    db.refresh(db_section)
    return db_section

@router.get("/sections", response_model=List[schemas.Section])
def read_sections(year_id: int = None, db: Session = Depends(database.get_db)):
    q = db.query(models.Section)
    if year_id:
        q = q.filter(models.Section.academic_year_id == year_id)
    return q.all()

@router.put("/sections/{section_id}", response_model=schemas.Section)
def update_section(section_id: int, section: schemas.SectionCreate, db: Session = Depends(database.get_db)):
    db_section = db.query(models.Section).filter(models.Section.id == section_id).first()
    if not db_section:
        raise HTTPException(status_code=404, detail="Section not found")
    db_section.name = section.name
    db_section.student_count = section.student_count
    db.commit()
    db.refresh(db_section)
    return db_section

@router.delete("/sections/{section_id}")
def delete_section(section_id: int, db: Session = Depends(database.get_db)):
    section = db.query(models.Section).filter(models.Section.id == section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    db.delete(section)
    db.commit()
    return {"message": "Section deleted"}

# --- Rooms ---
@router.post("/rooms", response_model=schemas.Room)
def create_room(room: schemas.RoomCreate, db: Session = Depends(database.get_db)):
    db_room = models.Room(**room.dict())
    db.add(db_room)
    db.commit()
    db.refresh(db_room)
    return db_room

@router.get("/rooms", response_model=List[schemas.Room])
def read_rooms(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.Room).offset(skip).limit(limit).all()

# --- Subjects ---
@router.post("/subjects", response_model=schemas.Subject)
def create_subject(subject: schemas.SubjectCreate, db: Session = Depends(database.get_db)):
    # Verify department exists
    dept = db.query(models.Department).filter(models.Department.id == subject.department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    db_subject = models.Subject(**subject.dict())
    db.add(db_subject)
    db.commit()
    db.refresh(db_subject)
    return db_subject

@router.get("/subjects", response_model=List[schemas.Subject])
def read_subjects(department_id: int = None, skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    q = db.query(models.Subject)
    if department_id:
        q = q.filter(models.Subject.department_id == department_id)
    return q.offset(skip).limit(limit).all()

@router.put("/subjects/{subject_id}", response_model=schemas.Subject)
def update_subject(subject_id: int, subject: schemas.SubjectCreate, db: Session = Depends(database.get_db)):
    db_subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not db_subject:
         raise HTTPException(status_code=404, detail="Subject not found")
    
    db_subject.name = subject.name
    db_subject.code = subject.code
    db_subject.department_id = subject.department_id
    db_subject.semester = subject.semester
    db_subject.subject_type = subject.subject_type
    db_subject.weekly_hours = subject.weekly_hours
    db_subject.continuous_hours = subject.continuous_hours
    
    db.commit()
    db.refresh(db_subject)
    return db_subject

@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: int, db: Session = Depends(database.get_db)):
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not subject:
         raise HTTPException(status_code=404, detail="Subject not found")
    db.delete(subject)
    db.commit()
    return {"message": "Subject deleted"}

# --- Faculty ---
@router.post("/faculty", response_model=schemas.Faculty)
def create_faculty(faculty: schemas.FacultyCreate, db: Session = Depends(database.get_db)):
    # Handle Many-to-Many Departments
    db_faculty = models.Faculty(
        name=faculty.name,
        faculty_id_code=faculty.faculty_id_code,
        faculty_type=faculty.faculty_type,
        min_hours_per_week=faculty.min_hours_per_week,
        max_hours_per_week=faculty.max_hours_per_week,
        preferred_slots=faculty.preferred_slots,
        user_id=faculty.user_id
    )
    
    if faculty.department_ids:
        depts = db.query(models.Department).filter(models.Department.id.in_(faculty.department_ids)).all()
        db_faculty.departments = depts
        
    db.add(db_faculty)
    db.commit()
    db.refresh(db_faculty)
    return db_faculty

@router.get("/faculty", response_model=List[schemas.Faculty])
def read_faculty(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.Faculty).offset(skip).limit(limit).all()

@router.put("/faculty/{faculty_id}", response_model=schemas.Faculty)
def update_faculty(faculty_id: int, faculty: schemas.FacultyCreate, db: Session = Depends(database.get_db)):
    db_faculty = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not db_faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
        
    db_faculty.name = faculty.name
    db_faculty.faculty_id_code = faculty.faculty_id_code
    db_faculty.faculty_type = faculty.faculty_type
    db_faculty.min_hours_per_week = faculty.min_hours_per_week
    db_faculty.max_hours_per_week = faculty.max_hours_per_week
    db_faculty.preferred_slots = faculty.preferred_slots

    if faculty.department_ids is not None:
         depts = db.query(models.Department).filter(models.Department.id.in_(faculty.department_ids)).all()
         db_faculty.departments = depts
    
    db.commit()
    db.refresh(db_faculty)
    return db_faculty

@router.delete("/faculty/{faculty_id}")
def delete_faculty(faculty_id: int, db: Session = Depends(database.get_db)):
    faculty = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    db.delete(faculty)
    db.commit()
    return {"message": "Faculty deleted"}

@router.post("/faculty/{faculty_id}/subjects", response_model=List[schemas.FacultySubjectAssignment])
def assign_faculty_subjects(faculty_id: int, assignments: List[schemas.FacultySubjectAssignmentCreate], db: Session = Depends(database.get_db)):
    # 1. Verify Faculty Exists
    faculty = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")

    # 2. Clear existing assignments (Simple replacement strategy)
    db.query(models.FacultySubjectAssignment).filter(models.FacultySubjectAssignment.faculty_id == faculty_id).delete()
    
    # 3. Add new assignments
    new_assignments = []
    for assignment in assignments:
        # Verify subject exists
        subject = db.query(models.Subject).filter(models.Subject.id == assignment.subject_id).first()
        if not subject:
             # Option: Skip or Raise. Raising ensures data integrity.
             raise HTTPException(status_code=404, detail=f"Subject ID {assignment.subject_id} not found")
        
        db_assignment = models.FacultySubjectAssignment(
            faculty_id=faculty_id,
            subject_id=assignment.subject_id,
            preference_level=assignment.preference_level
        )
        db.add(db_assignment)
        new_assignments.append(db_assignment)
    
    db.commit()
    
    # 4. Refresh to get relationships loaded if needed, or just return list
    # Re-querying to ensure 'subject' relationship is populated for response
    return db.query(models.FacultySubjectAssignment).filter(models.FacultySubjectAssignment.faculty_id == faculty_id).all()

# --- TimeSlots ---
@router.post("/timeslots", response_model=schemas.TimeSlot)
def create_timeslot(timeslot: schemas.TimeSlotCreate, db: Session = Depends(database.get_db)):
    db_timeslot = models.TimeSlot(**timeslot.dict())
    db.add(db_timeslot)
    db.commit()
    db.refresh(db_timeslot)
    return db_timeslot

@router.get("/timeslots", response_model=List[schemas.TimeSlot])
def read_timeslots(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.TimeSlot).offset(skip).limit(limit).all()

@router.put("/timeslots/{timeslot_id}", response_model=schemas.TimeSlot)
def update_timeslot(timeslot_id: int, timeslot: schemas.TimeSlotCreate, db: Session = Depends(database.get_db)):
    db_timeslot = db.query(models.TimeSlot).filter(models.TimeSlot.id == timeslot_id).first()
    if not db_timeslot:
        raise HTTPException(status_code=404, detail="TimeSlot not found")
    
    db_timeslot.day = timeslot.day
    db_timeslot.start_time = timeslot.start_time
    db_timeslot.end_time = timeslot.end_time
    db_timeslot.is_break = timeslot.is_break
    db_timeslot.label = timeslot.label
    
    db.commit()
    db.refresh(db_timeslot)
    return db_timeslot

@router.delete("/timeslots/{timeslot_id}")
def delete_timeslot(timeslot_id: int, db: Session = Depends(database.get_db)):
    timeslot = db.query(models.TimeSlot).filter(models.TimeSlot.id == timeslot_id).first()
    if not timeslot:
        raise HTTPException(status_code=404, detail="TimeSlot not found")
    db.delete(timeslot)
    db.commit()
    return {"message": "TimeSlot deleted"}
