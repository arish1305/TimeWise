from database import SessionLocal
from models import User, Department, Faculty, Subject, Room, TimeSlot, FacultySubjectAssignment, Timetable, AcademicYear, Section
from sqlalchemy import text

def check_data():
    db = SessionLocal()
    try:
        print("--- Database Row Counts ---")
        tables = [
            ("Users", User),
            ("Departments", Department),
            ("Faculty", Faculty),
            ("Subjects", Subject),
            ("Rooms", Room),
            ("TimeSlots", TimeSlot),
            ("Assignments", FacultySubjectAssignment),
            ("Timetables", Timetable),
            ("AcademicYears", AcademicYear),
            ("Sections", Section)
        ]
        
        for name, model in tables:
            count = db.query(model).count()
            print(f"{name}: {count}")
            
            # Print a few examples for verification
            if count > 0:
                first = db.query(model).first()
                if hasattr(first, 'name'):
                    print(f"  - Example: {first.name}")
                elif hasattr(first, 'username'):
                    print(f"  - Example: {first.username}")
                elif hasattr(first, 'room_number'):
                    print(f"  - Example: {first.room_number}")
        
        print("\n--- Connection Info ---")
        print(db.bind.url)

    except Exception as e:
        print(f"Error checking DB: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_data()
