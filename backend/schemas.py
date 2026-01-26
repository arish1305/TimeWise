from pydantic import BaseModel
from typing import Optional, List
from models import UserRole

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

class DepartmentCreate(DepartmentBase):
    pass

class Department(DepartmentBase):
    id: int
    class Config:
        from_attributes = True

# --- Course Schemas ---
class CourseBase(BaseModel):
    name: str
    department_id: int

class CourseCreate(CourseBase):
    pass

class Course(CourseBase):
    id: int
    class Config:
        from_attributes = True

# --- Room Schemas ---
class RoomBase(BaseModel):
    room_number: str
    capacity: int
    room_type: str = "CLASSROOM"

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
    credits: int
    is_lab: bool = False
    semester: int
    course_id: int

class SubjectCreate(SubjectBase):
    pass

class Subject(SubjectBase):
    id: int
    class Config:
        from_attributes = True

# --- Faculty Schemas ---
class FacultyBase(BaseModel):
    name: str
    department_id: int
    user_id: Optional[int] = None

class FacultyCreate(FacultyBase):
    pass

class Faculty(FacultyBase):
    id: int
    class Config:
        from_attributes = True

# --- Timetable Schemas ---
class GenerateTimetableRequest(BaseModel):
    semester: int
    academic_year: str = "2025-2026"

class TimetableEntryBase(BaseModel):
    subject_id: int
    faculty_id: int
    room_id: int
    timeslot_id: int

class TimetableEntry(TimetableEntryBase):
    id: int
    class Config:
        from_attributes = True

class TimetableBase(BaseModel):
    course_id: int
    semester: int
    status: str = "DRAFT"

class Timetable(TimetableBase):
    id: int
    entries: List[TimetableEntry] = []
    class Config:
        from_attributes = True


