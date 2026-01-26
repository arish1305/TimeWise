from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from models import User, UserRole, Department, Room, Faculty, Subject, Course
from auth import get_password_hash

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # Admin User
    if not db.query(User).filter(User.username == "admin").first():
        admin = User(
            username="admin",
            email="admin@timewise.com",
            hashed_password=get_password_hash("admin123"),
            role=UserRole.ADMIN,
            full_name="System Admin"
        )
        db.add(admin)

    # Department
    cse = db.query(Department).filter(Department.name == "CSE").first()
    if not cse:
        cse = Department(name="CSE")
        db.add(cse)
        db.commit()
        db.refresh(cse)

    # Faculty
    if not db.query(Faculty).filter(Faculty.name == "Dr. Smith").first():
        f1 = Faculty(name="Dr. Smith", department_id=cse.id)
        f2 = Faculty(name="Prof. Johnson", department_id=cse.id)
        db.add_all([f1, f2])

    # Rooms
    if not db.query(Room).filter(Room.room_number == "101").first():
        r1 = Room(room_number="101", capacity=60)
        r2 = Room(room_number="102", capacity=60)
        db.add_all([r1, r2])
        
    # Course & Subjects
    btech = db.query(Course).filter(Course.name == "B.Tech CSE").first()
    if not btech:
        btech = Course(name="B.Tech CSE", department_id=cse.id)
        db.add(btech)
        db.commit()
        db.refresh(btech)
        
        s1 = Subject(name="Data Structures", code="CS101", credits=3, semester=1, course_id=btech.id)
        s2 = Subject(name="Algorithms", code="CS102", credits=3, semester=1, course_id=btech.id)
        db.add_all([s1, s2])

    db.commit()
    db.close()
    print("Seed data initialized.")

if __name__ == "__main__":
    seed()
