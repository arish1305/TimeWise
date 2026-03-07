from pydantic import BaseModel
from typing import Optional, List
from models import UserRole, RoomType, FacultyType, SubjectType, EntryCreator

class UserBase(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None
    role: UserRole

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# --- Department Schemas ---
class DepartmentBase(BaseModel):
    name: str
    code: str

class DepartmentCreate(DepartmentBase):
    pass

class Department(DepartmentBase):
    id: int
    class Config:
        from_attributes = True

# --- Academic Year Schemas ---
class AcademicYearBase(BaseModel):
    name: str
    level: int
    department_id: int

class AcademicYearCreate(AcademicYearBase):
    pass

class AcademicYear(AcademicYearBase):
    id: int
    class Config:
        from_attributes = True

# --- Section Schemas ---
class SectionBase(BaseModel):
    name: str
    academic_year_id: int
    student_count: int = 60

class SectionCreate(SectionBase):
    pass

class Section(SectionBase):
    id: int
    class Config:
        from_attributes = True

class SectionWithYear(SectionBase):
    id: int
    academic_year: Optional[AcademicYear] = None
    class Config:
        from_attributes = True

# --- Room Schemas ---
class RoomBase(BaseModel):
    room_number: str
    capacity: int
    room_type: RoomType = RoomType.CLASSROOM
    departments: Optional[List[int]] = None # List of Department IDs

class RoomCreate(RoomBase):
    pass

class Room(RoomBase):
    id: int
    class Config:
        from_attributes = True

# --- Subject Schemas ---
class SubjectBase(BaseModel):
    name: str
    code: str
    department_id: int
    semester: int
    subject_type: SubjectType = SubjectType.THEORY
    weekly_hours: int = 3
    continuous_hours: int = 1

class SubjectCreate(SubjectBase):
    pass

class Subject(SubjectBase):
    id: int
    class Config:
        from_attributes = True

# --- Faculty Schemas ---
class FacultySubjectAssignmentBase(BaseModel):
    subject_id: int
    preference_level: int = 1
    section_ids: Optional[List[int]] = None  # List of section IDs

class FacultySubjectAssignmentCreate(FacultySubjectAssignmentBase):
    pass

class FacultySubjectAssignment(FacultySubjectAssignmentBase):
    id: int
    faculty_id: int
    subject: Optional['Subject'] = None
    class Config:
        from_attributes = True

class FacultyBase(BaseModel):
    name: str
    faculty_id_code: Optional[str] = None # e.g. FAC001
    faculty_type: FacultyType = FacultyType.ASSISTANT_PROFESSOR
    min_hours_per_week: int = 5
    max_hours_per_week: int = 18
    preferred_slots: Optional[dict] = None

class FacultyCreate(FacultyBase):
    user_id: Optional[int] = None
    department_ids: List[int] = [] # List of department IDs to assign

class Faculty(FacultyBase):
    id: int
    departments: List[Department] = []
    qualified_subjects: List[FacultySubjectAssignment] = []
    class Config:
        from_attributes = True

# --- Timetable Schemas ---
class GenerateTimetableRequest(BaseModel):
    semester: int
    section_id: int # Timetable is per section now
    academic_year_id: Optional[int] = None

# Simpler Faculty schema for timetable entries (avoids circular refs)
class FacultyBasic(BaseModel):
    id: int
    name: str
    faculty_id_code: Optional[str] = None
    class Config:
        from_attributes = True

class TimetableEntryBase(BaseModel):
    subject_id: int
    faculty_id: Optional[int] = None
    room_id: Optional[int] = None
    timeslot_id: int
    is_locked: bool = False
    created_by: str = EntryCreator.AI

class TimetableEntry(TimetableEntryBase):
    id: int
    subject: Optional[Subject] = None
    faculty: Optional[FacultyBasic] = None
    room: Optional[Room] = None
    timeslot: Optional['TimeSlot'] = None 
    class Config:
        from_attributes = True

class TimetableBase(BaseModel):
    section_id: Optional[int] = None
    semester: int
    status: str = "DRAFT"

class Timetable(TimetableBase):
    id: int
    section: Optional[SectionWithYear] = None
    entries: List[TimetableEntry] = []
    class Config:
        from_attributes = True

# --- Manual Entry Schemas ---
class ManualEntryRequest(BaseModel):
    section_id: int
    semester: int
    subject_id: int
    faculty_id: Optional[int] = None
    room_id: Optional[int] = None
    timeslot_id: int
    is_locked: bool = True

class ManualEntryUpdate(BaseModel):
    subject_id: Optional[int] = None
    faculty_id: Optional[int] = None
    room_id: Optional[int] = None
    is_locked: Optional[bool] = None

class RegenerateRequest(BaseModel):
    section_id: int
    semester: int

# --- TimeSlot Schemas ---
from datetime import time

class TimeSlotBase(BaseModel):
    day: str
    start_time: time
    end_time: time
    is_break: bool = False
    label: Optional[str] = None

class TimeSlotCreate(TimeSlotBase):
    pass

class TimeSlot(TimeSlotBase):
    id: int
    class Config:
        from_attributes = True

