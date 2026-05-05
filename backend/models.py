from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum, Time, CheckConstraint, Table, JSON, DateTime
from sqlalchemy.orm import relationship
from database import Base
import enum
import datetime

# Enums
class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    FACULTY = "FACULTY"
    TIMETABLE_CELL = "TIMETABLE_CELL"



class FacultyType(str, enum.Enum):
    PROFESSOR = "PROFESSOR"
    ASSISTANT_PROFESSOR = "ASSISTANT_PROFESSOR"
    LAB_INSTRUCTOR = "LAB_INSTRUCTOR"
    GUEST = "GUEST"

class SubjectType(str, enum.Enum):
    THEORY = "THEORY"
    LAB = "LAB"

class EntryCreator(str, enum.Enum):
    ADMIN = "ADMIN"
    AI = "AI"

# Association for Many-to-Many: Faculty <-> Departments (if teaching across departments)
# For now, we keep 1-to-many as primary, but prompt says "assign faculty to one or more departments".
faculty_department_association = Table(
    'faculty_department', Base.metadata,
    Column('faculty_id', Integer, ForeignKey('faculty.id')),
    Column('department_id', Integer, ForeignKey('departments.id'))
)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default=UserRole.FACULTY)
    full_name = Column(String)
    
    faculty_profile = relationship("Faculty", back_populates="user", uselist=False)

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True) # e.g., "Computer Science Engineering"
    code = Column(String, unique=True) # e.g., "CSE"
    
    years = relationship("AcademicYear", back_populates="department", cascade="all, delete-orphan")
    subjects = relationship("Subject", back_populates="department")
    # Faculty linked via association or direct mapping. 
    # For strict ownership, maybe a "primary_department_id".
    faculty = relationship("Faculty", secondary=faculty_department_association, back_populates="departments")

class AcademicYear(Base):
    """Represents a Year within a Department, e.g., CSE Year 2"""
    __tablename__ = "academic_years"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String) # "Year 1", "Year 2"
    level = Column(Integer) # 1, 2, 3, 4
    department_id = Column(Integer, ForeignKey("departments.id"))
    
    department = relationship("Department", back_populates="years")
    sections = relationship("Section", back_populates="academic_year", cascade="all, delete-orphan")

class Section(Base):
    """Represents a Section within a Year, e.g., CSE Year 2 Section A"""
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String) # "A", "B", "C"
    academic_year_id = Column(Integer, ForeignKey("academic_years.id"))
    student_count = Column(Integer, default=60)
    
    academic_year = relationship("AcademicYear", back_populates="sections")
    timetables = relationship("Timetable", back_populates="section")

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    code = Column(String, unique=True, index=True) # e.g., "CS101"
    department_id = Column(Integer, ForeignKey("departments.id"))
    semester = Column(Integer) # e.g., 3 (for Year 2)
    subject_type = Column(String, default=SubjectType.THEORY)
    weekly_hours = Column(Integer, default=3) # Total hours per week
    continuous_hours = Column(Integer, default=1) # e.g., 3 hours block for Labs
    manual_timeslot_ids = Column(JSON, default=list) # Array of timeslot IDs for manually set timings
    is_elective = Column(Boolean, default=False)
    elective_group_id = Column(String, nullable=True) # e.g., "PE-1"
    allowed_department_ids = Column(JSON, default=list) # List of other department IDs allowed to take this subject
    
    department = relationship("Department", back_populates="subjects")
    eligible_faculty = relationship("FacultySubjectAssignment", back_populates="subject")

class Faculty(Base):
    __tablename__ = "faculty"
    id = Column(Integer, primary_key=True, index=True)
    faculty_id_code = Column(String, unique=True, index=True, nullable=True) # e.g., "FAC001"
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    name = Column(String, index=True)
    faculty_type = Column(String, default=FacultyType.ASSISTANT_PROFESSOR)
    
    # Constraints
    min_hours_per_week = Column(Integer, default=5)
    max_hours_per_week = Column(Integer, default=18)
    preferred_slots = Column(JSON, nullable=True) # {"monday": ["9:00", "10:00"]}
    
    user = relationship("User", back_populates="faculty_profile")
    departments = relationship("Department", secondary=faculty_department_association, back_populates="faculty")
    qualified_subjects = relationship("FacultySubjectAssignment", back_populates="faculty")

class FacultySubjectAssignment(Base):
    """Mapping: Which Faculty handles which Subject (and potentially for which Section/Year if specific)"""
    __tablename__ = "faculty_subject_assignments"
    id = Column(Integer, primary_key=True, index=True)
    faculty_id = Column(Integer, ForeignKey("faculty.id"))
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    preference_level = Column(Integer, default=1) # 1=High, 5=Low
    section_ids = Column(JSON, nullable=True) # List of section IDs this faculty teaches for this subject
    
    faculty = relationship("Faculty", back_populates="qualified_subjects")
    subject = relationship("Subject", back_populates="eligible_faculty")



class TimeSlot(Base):
    __tablename__ = "timeslots"
    id = Column(Integer, primary_key=True, index=True)
    day = Column(String) # Monday, Tuesday
    start_time = Column(Time)
    end_time = Column(Time)
    is_break = Column(Boolean, default=False) # Lunch break, etc.
    label = Column(String, nullable=True) # "Lunch", "Morning Break"
    
    __table_args__ = (
        CheckConstraint('end_time > start_time', name='check_timeslot_duration'),
    )

class Timetable(Base):
    __tablename__ = "timetables"
    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("sections.id")) # Timetable is usually for a section
    semester = Column(Integer)
    version = Column(Integer, default=1)
    status = Column(String, default="DRAFT") # DRAFT, APPROVED
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    section = relationship("Section", back_populates="timetables")
    entries = relationship("TimetableEntry", back_populates="timetable", cascade="all, delete-orphan")

class TimetableEntry(Base):
    __tablename__ = "timetable_entries"
    id = Column(Integer, primary_key=True, index=True)
    timetable_id = Column(Integer, ForeignKey("timetables.id"))
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=True)
    timeslot_id = Column(Integer, ForeignKey("timeslots.id"))
    is_locked = Column(Boolean, default=False)
    created_by = Column(String, default=EntryCreator.AI)
    
    timetable = relationship("Timetable", back_populates="entries")
    subject = relationship("Subject")
    faculty = relationship("Faculty")
    timeslot = relationship("TimeSlot")
