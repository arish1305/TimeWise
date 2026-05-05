from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from models import User, UserRole, Department, Faculty, Subject, AcademicYear, Section, FacultyType, FacultySubjectAssignment
from auth import get_password_hash

def seed():
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # Admin User
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@timewise.com",
            hashed_password=get_password_hash("admin"),
            role=UserRole.ADMIN,
            full_name="System Admin"
        )
        db.add(admin)
    else:
        admin.email = "admin@timewise.com"
        admin.role = UserRole.ADMIN
        admin.full_name = "System Admin"
        admin.hashed_password = get_password_hash("admin")

    # Department
    # Use Filter by Code as it is Unique
    cse = db.query(Department).filter(Department.code == "CSE").first()
    if not cse:
        # Check if name exists but with different code? No, simple check is enough strictly on Code.
        # However, to be safe against name collision if code is different:
        cse_name_check = db.query(Department).filter(Department.name == "Computer Science Engineering").first()
        if cse_name_check:
             cse = cse_name_check
        else:
             cse = Department(name="Computer Science Engineering", code="CSE")
             db.add(cse)
             db.commit()
             db.refresh(cse)

    # Academic Years & Sections
    # Check if Year 2 exists
    year2 = db.query(AcademicYear).filter(AcademicYear.name == "Year 2", AcademicYear.department_id == cse.id).first()
    if not year2:
        year2 = AcademicYear(name="Year 2", level=2, department_id=cse.id)
        db.add(year2)
        db.commit()
        db.refresh(year2)
        
        # Sections
        sec_a = Section(name="A", academic_year_id=year2.id, student_count=60)
        sec_b = Section(name="B", academic_year_id=year2.id, student_count=60)
        db.add_all([sec_a, sec_b])

    # Faculty - Commented out to prevent recreation after user deletion
    # if not db.query(Faculty).filter(Faculty.name == "Dr. Smith").first():
    #     f1 = Faculty(name="Dr. Smith", faculty_type=FacultyType.PROFESSOR)
    #     f1.departments.append(cse)
    #     db.add(f1)
    
    # if not db.query(Faculty).filter(Faculty.name == "Prof. Johnson").first():
    #     f2 = Faculty(name="Prof. Johnson", faculty_type=FacultyType.ASSISTANT_PROFESSOR)
    #     f2.departments.append(cse)
    #     db.add(f2)

    #     db.add_all([f1, f2])
    #     if not cse.faculty: # Ensure relationship is populated
    #          cse.faculty = [f1, f2]
    #          db.commit()

    # Fixed Time Slots (Mon-Fri)
    # 09:00 - 10:00 (Lecture)
    # 10:00 - 11:00 (Lecture)
    # 11:00 - 11:15 (Break)
    # 11:15 - 12:15 (Lunch)
    # 12:15 - 13:15 (Lecture)
    # 13:15 - 14:15 (Lecture)
    # 14:15 - 15:15 (Lecture)
    
    from models import TimeSlot
    import datetime
    
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    # Define the template for one day
    # (start_str, end_str, is_break, label)
    slot_template = [
        ("09:00:00", "10:00:00", False, "Lecture 1"),
        ("10:00:00", "11:00:00", False, "Lecture 2"),
        ("11:00:00", "11:15:00", True, "Morning Break"),
        ("11:15:00", "12:15:00", True, "Lunch Break"),
        ("12:15:00", "13:15:00", False, "Lecture 3"),
        ("13:15:00", "14:15:00", False, "Lecture 4"),
        ("14:15:00", "15:15:00", False, "Lecture 5"), # Ends at 3:15 PM
    ]
    
    # Check if slots exist, if not seed them
    if db.query(TimeSlot).count() == 0:
        new_slots = []
        for day in days:
            for s in slot_template:
                start_t = datetime.datetime.strptime(s[0], "%H:%M:%S").time()
                end_t = datetime.datetime.strptime(s[1], "%H:%M:%S").time()
                ts = TimeSlot(
                    day=day,
                    start_time=start_t,
                    end_time=end_t,
                    is_break=s[2],
                    label=s[3]
                )
                new_slots.append(ts)
        db.add_all(new_slots)
        db.commit()
    

            
    db.commit()
    db.close()
    print("Seed data initialized for TimeWise AI.")

if __name__ == "__main__":
    seed()
