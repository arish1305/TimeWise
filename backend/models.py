from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum, ARRAY, Time, Date, CheckConstraint
from sqlalchemy.orm import relationship
from database import Base
import enum

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    FACULTY = "FACULTY"
    TIMETABLE_CELL = "TIMETABLE_CELL"

class RoomType(str, enum.Enum):
    CLASSROOM = "CLASSROOM"
    LAB = "LAB"
    SEMINAR_HALL = "SEMINAR_HALL"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default=UserRole.FACULTY)
    full_name = Column(String)
    
    # Relationships
    faculty_profile = relationship("Faculty", back_populates="user", uselist=False)

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    
    courses = relationship("Course", back_populates="department")
    faculty = relationship("Faculty", back_populates="department")

class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"))
    name = Column(String, index=True) # e.g., B.Tech CSE
    
    department = relationship("Department", back_populates="courses")
    subjects = relationship("Subject", back_populates="course")

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"))
    name = Column(String, index=True)
    code = Column(String, unique=True, index=True)
    credits = Column(Integer)
    is_lab = Column(Boolean, default=False)
    semester = Column(Integer)
    
    course = relationship("Course", back_populates="subjects")

class Faculty(Base):
    __tablename__ = "faculty"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Link to auth user
    name = Column(String, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"))
    
    # Store availability as a JSON or structured string if needed, 
    # but for now we might keeping it simple or link to a separate table if complex.
    # Simple approach: list of avoid timeslots or preferred timeslots could be separate tables.
    
    department = relationship("Department", back_populates="faculty")
    user = relationship("User", back_populates="faculty_profile")

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    room_number = Column(String, unique=True, index=True)
    capacity = Column(Integer)
    room_type = Column(String, default=RoomType.CLASSROOM)

class TimeSlot(Base):
    __tablename__ = "timeslots"
    id = Column(Integer, primary_key=True, index=True)
    day = Column(String) # Monday, Tuesday, etc.
    start_time = Column(Time)
    end_time = Column(Time)
    
    __table_args__ = (
        CheckConstraint('end_time > start_time', name='check_timeslot_duration'),
    )

class Timetable(Base):
    __tablename__ = "timetables"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"))
    semester = Column(Integer)
    version = Column(Integer, default=1)
    status = Column(String, default="DRAFT") # DRAFT, PENDING_APPROVAL, APPROVED, PUBLISHED
    is_active = Column(Boolean, default=False)
    
    entries = relationship("TimetableEntry", back_populates="timetable")

class TimetableEntry(Base):
    __tablename__ = "timetable_entries"
    id = Column(Integer, primary_key=True, index=True)
    timetable_id = Column(Integer, ForeignKey("timetables.id"))
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    faculty_id = Column(Integer, ForeignKey("faculty.id"))
    room_id = Column(Integer, ForeignKey("rooms.id"))
    timeslot_id = Column(Integer, ForeignKey("timeslots.id"))
    
    timetable = relationship("Timetable", back_populates="entries")
