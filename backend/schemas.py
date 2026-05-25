from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, time
from models import UserRole, FacultyType, SubjectType, EntryCreator

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
    role: UserRole
    username: str
    full_name: Optional[str] = None
    faculty_id: Optional[int] = None

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[UserRole] = None
    faculty_id: Optional[int] = None

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
    department: Optional[Department] = None
    class Config:
        from_attributes = True

# --- Section Schemas ---
class SectionBase(BaseModel):
    name: str = ""
    academic_year_id: int
    student_count: int = 60
    section_name: Optional[str] = None
    year: Optional[int] = None
    independent_schedule: bool = True

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



# --- Subject Schemas ---
class SubjectBase(BaseModel):
    name: str
    code: str
    department_id: Optional[int] = None
    semester: int
    subject_type: SubjectType = SubjectType.THEORY
    weekly_hours: int = 3
    continuous_hours: int = 1
    manual_timeslot_ids: List[int] = []
    is_elective: bool = False
    elective_group_id: Optional[str] = None
    allowed_department_ids: List[int] = []

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

class FacultyBulkRow(BaseModel):
    name: str
    faculty_id_code: Optional[str] = None
    faculty_type: FacultyType = FacultyType.ASSISTANT_PROFESSOR
    min_hours_per_week: int = 5
    max_hours_per_week: int = 18
    department_codes: List[str] = []

class FacultyBulkCreate(BaseModel):
    rows: List[FacultyBulkRow]

class FacultyBulkResult(BaseModel):
    created_count: int
    errors: List[str]

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
    timeslot_id: int
    room_id: Optional[int] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None
    is_manual: bool = False
    edited_by: Optional[int] = None
    version: int = 1
    is_locked: bool = False
    created_by: str = EntryCreator.AI

class TimetableEntry(TimetableEntryBase):
    id: int
    subject: Optional[Subject] = None
    faculty: Optional[FacultyBasic] = None
    timeslot: Optional['TimeSlot'] = None 
    class Config:
        from_attributes = True

class TimetableBase(BaseModel):
    section_id: Optional[int] = None
    semester: int
    status: str = "DRAFT"
    version: int = 1
    generated_version: Optional[int] = 0
    edited_version: Optional[int] = 0
    approved_version: Optional[int] = 0

class Timetable(TimetableBase):
    id: int
    created_at: Optional[datetime] = None
    section: Optional[SectionWithYear] = None
    entries: List[TimetableEntry] = []
    time_slots: List['TimeSlot'] = []
    class Config:
        from_attributes = True

class FacultyTimetableEntry(BaseModel):
    timetable_id: int
    timetable_status: str
    semester: int
    section_id: int
    section_name: str
    academic_year_name: Optional[str] = None
    department_name: Optional[str] = None
    department_code: Optional[str] = None
    subject_id: int
    subject_code: Optional[str] = None
    subject_name: Optional[str] = None
    timeslot_id: int
    day: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    is_locked: bool = False
    created_by: str

class FacultyTimetableResponse(BaseModel):
    faculty_id: int
    faculty_name: str
    faculty_id_code: Optional[str] = None
    entries: List[FacultyTimetableEntry]

# --- Manual Entry Schemas ---
class ManualEntryRequest(BaseModel):
    section_id: int
    semester: int
    subject_id: int
    faculty_id: Optional[int] = None
    timeslot_id: int
    is_locked: bool = True

class ManualEntryUpdate(BaseModel):
    subject_id: Optional[int] = None
    faculty_id: Optional[int] = None
    is_locked: Optional[bool] = None

class RegenerateRequest(BaseModel):
    section_id: int
    semester: int

class TimeSlotBase(BaseModel):
    department_id: Optional[int] = None
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


class VisualBoardResponse(BaseModel):
    department_id: int
    semester: Optional[int] = None
    academic_year_id: Optional[int] = None
    time_slots: List[TimeSlot] = []
    timetables: List[Timetable] = []


class DepartmentScheduleBuildRequest(BaseModel):
    days: List[str] = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    start_time: time
    end_time: time
    break_start: time
    break_end: time
    lunch_start: time
    lunch_end: time

# --- Validation Schemas ---
class ValidationResponse(BaseModel):
    status: str
    errors: List[str]
    warnings: List[str]
    error_slots: List[int] = []
    warning_slots: List[int] = []


class TimetableEditRequest(BaseModel):
    entry_id: int
    source_slot: int
    target_slot: int
    target_room: Optional[int] = None
    action: str = "move"  # move | swap | duplicate | lock | delete
    apply: bool = True
    timetable_id: Optional[int] = None


class TimetableEditResponse(BaseModel):
    status: str
    message: str
    validation: ValidationResponse
    suggestions: List[Dict[str, Any]] = []
    changed_entry_ids: List[int] = []


class TimetableEditEvent(BaseModel):
    id: int
    timetable_id: int
    entry_id: Optional[int] = None
    event_type: str
    payload: Dict[str, Any] = {}
    edited_by: Optional[int] = None
    version: int = 1
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SchedulingRuleBase(BaseModel):
    department_id: Optional[int] = None
    name: str = "default"
    rules: Dict[str, Any] = {}
    is_active: bool = True


class SchedulingRuleUpdate(BaseModel):
    department_id: Optional[int] = None
    name: str = "default"
    rules: Dict[str, Any]
    is_active: bool = True


class SchedulingRule(SchedulingRuleBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
