import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from database import SessionLocal, Base, engine
import models
from routers.timetable import generate_timetable
import schemas

def test_cbcs_parallel_scheduling():
    db = SessionLocal()
    try:
        # Use existing CSE data if available, else create
        dept = db.query(models.Department).filter(models.Department.code == "CSE").first()
        if not dept:
            dept = models.Department(name="Computer Science", code="CSE")
            db.add(dept)
            db.commit()
            db.refresh(dept)
            
        year = db.query(models.AcademicYear).filter(models.AcademicYear.department_id == dept.id).first()
        if not year:
            year = models.AcademicYear(name="Year 1", level=1, department_id=dept.id)
            db.add(year)
            db.commit()
            db.refresh(year)
            
        section = db.query(models.Section).filter(models.Section.academic_year_id == year.id).first()
        if not section:
            section = models.Section(name="A", academic_year_id=year.id)
            db.add(section)
            db.commit()
            db.refresh(section)

        # Create two subjects in the same Elective Group for Semester 9 (to avoid seeding conflict)
        test_semester = 9
        
        # Cleanup old test data
        sub_ids = [s.id for s in db.query(models.Subject).filter(models.Subject.semester == test_semester).all()]
        if sub_ids:
            db.query(models.TimetableEntry).filter(models.TimetableEntry.subject_id.in_(sub_ids)).delete(synchronize_session=False)
            db.query(models.Subject).filter(models.Subject.id.in_(sub_ids)).delete(synchronize_session=False)
        db.commit()

        s1 = models.Subject(
            name="Elective A", 
            code="EA-TEST", 
            department_id=dept.id, 
            semester=test_semester, 
            weekly_hours=1, 
            is_elective=True, 
            elective_group_id="EG1"
        )
        s2 = models.Subject(
            name="Elective B", 
            code="EB-TEST", 
            department_id=dept.id, 
            semester=test_semester, 
            weekly_hours=1, 
            is_elective=True, 
            elective_group_id="EG1"
        )
        db.add_all([s1, s2])
        db.commit()
        db.refresh(s1)
        db.refresh(s2)

        # Ensure timeslots exist
        if db.query(models.TimeSlot).count() == 0:
            print("No timeslots found. Run seed.py first.")
            return False

        # Trigger Timetable Generation
        print(f"Generating timetable for Section {section.id}, Semester {test_semester}...")
        request = schemas.GenerateTimetableRequest(section_id=section.id, semester=test_semester)
        
        # We use the internal generate_timetable function (skipping auth Depends)
        tt = generate_timetable(request, db)
        
        # Verify Parallel Scheduling
        entries = tt.entries
        s1_entries = [e for e in entries if e.subject_id == s1.id]
        s2_entries = [e for e in entries if e.subject_id == s2.id]
        
        if not s1_entries or not s2_entries:
            print(f"FAILED: Found {len(s1_entries)} entries for s1 and {len(s2_entries)} for s2.")
            return False
            
        ts1 = s1_entries[0].timeslot_id
        ts2 = s2_entries[0].timeslot_id
        
        print(f"Elective A scheduled in Timeslot: {ts1}")
        print(f"Elective B scheduled in Timeslot: {ts2}")

        if ts1 == ts2:
            print("✅ SUCCESS: Parallel scheduling verified.")
            return True
        else:
            print("❌ FAILED: Electives scheduled in different slots.")
            return False
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if test_cbcs_parallel_scheduling():
        sys.exit(0)
    else:
        sys.exit(1)
