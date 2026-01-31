"""
Script to clear all seed data from the database.
This will delete:
- Faculty (Dr. Smith, Prof. Johnson)
- Subjects (CS101-CS106)
- Their related assignments and timetable entries
"""

from database import SessionLocal
from models import Faculty, Subject, FacultySubjectAssignment, TimetableEntry, Timetable

def clear_seed_data():
    db = SessionLocal()
    
    try:
        print("Starting to clear seed data...")
        
        # Delete all timetables and their entries
        print("Deleting timetables...")
        db.query(TimetableEntry).delete()
        db.query(Timetable).delete()
        
        # Delete all faculty subject assignments
        print("Deleting faculty assignments...")
        db.query(FacultySubjectAssignment).delete()
        
        # Delete seed faculty
        print("Deleting faculty...")
        dr_smith = db.query(Faculty).filter(Faculty.name == "Dr. Smith").first()
        if dr_smith:
            db.delete(dr_smith)
            print("  - Deleted Dr. Smith")
        
        prof_johnson = db.query(Faculty).filter(Faculty.name == "Prof. Johnson").first()
        if prof_johnson:
            db.delete(prof_johnson)
            print("  - Deleted Prof. Johnson")
        
        # Delete seed subjects
        print("Deleting subjects...")
        subject_codes = ["CS101", "CS102", "CS103", "CS104", "CS105", "CS106"]
        for code in subject_codes:
            subject = db.query(Subject).filter(Subject.code == code).first()
            if subject:
                db.delete(subject)
                print(f"  - Deleted {code}")
        
        db.commit()
        print("\n✅ All seed data cleared successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    clear_seed_data()
