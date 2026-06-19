from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any
import csv
import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, time
import database, models, schemas, auth

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(auth.require_admin)]
)

XLSX_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _default_rule_payload() -> Dict[str, Any]:
    return {
        "max_daily_subjects": 5,
        "spread_subjects": True,
        "allow_saturday": False,
        "max_lab_per_day": 1,
    }


def _normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _split_department_codes(value: Any) -> List[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []

    normalized = text.replace(";", ",").replace("|", ",")
    return [part.strip().upper() for part in normalized.split(",") if part.strip()]


def _parse_int(value: Any, default: int) -> int:
    text = "" if value is None else str(value).strip()
    if not text:
        return default
    return int(float(text))


def _find_field(row: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for k in keys:
        if k in row:
            return row[k]
    return default


def _build_faculty_from_row(row: Dict[str, Any]) -> schemas.FacultyBulkRow:
    name_val = _find_field(row, ["name", "faculty_name", "full_name", "facultyname", "fullname"])
    id_val = _find_field(row, ["faculty_id_code", "faculty_code", "id_code", "idcode", "id", "code", "faculty_id"])
    
    name = str(name_val or "").strip()
    faculty_id_code = str(id_val or "").strip() or None
    
    faculty_type = str(_find_field(row, ["faculty_type", "designation", "faculty_designation", "type", "role"]) or "ASSISTANT_PROFESSOR").strip()
    
    min_hrs = _parse_int(_find_field(row, ["min_hours_per_week", "min_hours", "min_load", "min", "minhours"]), 5)
    max_hrs = _parse_int(_find_field(row, ["max_hours_per_week", "max_hours", "max_load", "max", "maxhours"]), 18)
    
    dept_codes = _split_department_codes(_find_field(row, ["department_codes", "department_code", "departments", "department", "dept", "depts", "dept_codes", "deptcodes"]))

    return schemas.FacultyBulkRow(
        name=name,
        faculty_id_code=faculty_id_code,
        faculty_type=faculty_type,
        min_hours_per_week=min_hrs,
        max_hours_per_week=max_hrs,
        department_codes=dept_codes,
    )


def _create_faculty_records(rows: List[schemas.FacultyBulkRow], db: Session) -> Dict[str, Any]:
    created_count = 0
    errors: List[str] = []

    departments = db.query(models.Department).all()
    department_by_code = {dept.code.upper(): dept for dept in departments}
    existing_codes = {
        (code or "").strip().upper()
        for (code,) in db.query(models.Faculty.faculty_id_code).all()
        if code
    }
    batch_codes = set()

    for index, row in enumerate(rows, start=1):
        row_idx = row.row_number if getattr(row, "row_number", None) is not None else index
        try:
            with db.begin_nested():
                if not row.name or not row.name.strip():
                    raise ValueError("Name is missing")

                if not row.faculty_id_code or not row.faculty_id_code.strip():
                    raise ValueError("ID is missing")

                normalized_code = (row.faculty_id_code or "").strip().upper()
                if normalized_code:
                    if normalized_code in existing_codes or normalized_code in batch_codes:
                        raise ValueError(f"faculty_id_code '{row.faculty_id_code}' already exists")
                    batch_codes.add(normalized_code)

                unknown_codes = [code for code in row.department_codes if code not in department_by_code]
                if unknown_codes:
                    raise ValueError(f"unknown department code(s): {', '.join(unknown_codes)}")

                if row.min_hours_per_week < 0 or row.max_hours_per_week < 0:
                    raise ValueError("min/max hours must be non-negative")
                if row.min_hours_per_week > row.max_hours_per_week:
                    raise ValueError("min_hours_per_week cannot be greater than max_hours_per_week")

                db_faculty = models.Faculty(
                    name=row.name.strip(),
                    faculty_id_code=(row.faculty_id_code or "").strip() or None,
                    faculty_type=row.faculty_type.strip(),
                    min_hours_per_week=row.min_hours_per_week,
                    max_hours_per_week=row.max_hours_per_week,
                )

                if row.department_codes:
                    db_faculty.departments = [department_by_code[code] for code in row.department_codes]

                db.add(db_faculty)
                db.flush()

            created_count += 1
            if normalized_code:
                existing_codes.add(normalized_code)
        except Exception as exc:
            errors.append(f"Row {row_idx}: {exc}")

    if created_count > 0:
        db.commit()
    elif errors:
        db.rollback()

    return {"created_count": created_count, "errors": errors}


def _parse_csv_rows(file_bytes: bytes) -> List[Dict[str, Any]]:
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows: List[Dict[str, Any]] = []
    for row in reader:
        normalized = { _normalize_header(key or ""): value for key, value in row.items() }
        if any(str(value or "").strip() for value in normalized.values()):
            rows.append(normalized)
    return rows


def _column_ref_to_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return max(index - 1, 0)


def _shared_strings_map(archive: zipfile.ZipFile) -> List[str]:
    try:
        data = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    root = ET.fromstring(data)
    strings = []
    for si in root.findall("main:si", XLSX_NS):
        parts = [node.text or "" for node in si.findall(".//main:t", XLSX_NS)]
        strings.append("".join(parts))
    return strings


def _read_xlsx_rows(file_bytes: bytes) -> List[Dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
        shared_strings = _shared_strings_map(archive)
        sheet_data = archive.read("xl/worksheets/sheet1.xml")

    root = ET.fromstring(sheet_data)
    rows: List[List[str]] = []

    for row_node in root.findall(".//main:sheetData/main:row", XLSX_NS):
        cells: Dict[int, str] = {}
        for cell in row_node.findall("main:c", XLSX_NS):
            ref = cell.attrib.get("r", "")
            idx = _column_ref_to_index(ref)
            cell_type = cell.attrib.get("t")
            value_node = cell.find("main:v", XLSX_NS)
            inline_text = cell.find("main:is/main:t", XLSX_NS)

            value = ""
            if cell_type == "s" and value_node is not None and value_node.text is not None:
                value = shared_strings[int(value_node.text)]
            elif cell_type == "inlineStr" and inline_text is not None and inline_text.text is not None:
                value = inline_text.text
            elif value_node is not None and value_node.text is not None:
                value = value_node.text

            cells[idx] = value

        if cells:
            max_idx = max(cells.keys())
            row_values = [cells.get(i, "") for i in range(max_idx + 1)]
            rows.append(row_values)

    if not rows:
        return []

    headers = [_normalize_header(value) for value in rows[0]]
    parsed_rows: List[Dict[str, Any]] = []

    for row in rows[1:]:
        record = {
            headers[index]: row[index] if index < len(row) else ""
            for index in range(len(headers))
            if headers[index]
        }
        if any(str(value or "").strip() for value in record.values()):
            parsed_rows.append(record)

    return parsed_rows


def _xlsx_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_template_xlsx() -> bytes:
    headers = [
        "name",
        "faculty_id_code",
        "faculty_type",
        "min_hours_per_week",
        "max_hours_per_week",
        "department_codes",
    ]
    sample_rows = [
        ["Dr. Jane Doe", "FAC001", "ASSISTANT_PROFESSOR", "5", "18", "CSE"],
        ["Prof. Arun Kumar", "FAC002", "PROFESSOR", "8", "16", "CSE,ECE"],
    ]
    all_rows = [headers] + sample_rows
    shared_strings: List[str] = []
    string_index: Dict[str, int] = {}

    def string_id(value: str) -> int:
        if value not in string_index:
            string_index[value] = len(shared_strings)
            shared_strings.append(value)
        return string_index[value]

    sheet_rows = []
    for row_idx, row in enumerate(all_rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            col_name = ""
            current = col_idx
            while current > 0:
                current, remainder = divmod(current - 1, 26)
                col_name = chr(65 + remainder) + col_name
            shared_id = string_id(value)
            cells.append(f'<c r="{col_name}{row_idx}" t="s"><v>{shared_id}</v></c>')
        sheet_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="{XLSX_NS["main"]}" count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
        + "".join(f"<si><t>{_xlsx_escape(value)}</t></si>" for value in shared_strings)
        + "</sst>"
    )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{XLSX_NS["main"]}">'
        "<sheetData>"
        + "".join(sheet_rows)
        + "</sheetData></worksheet>"
    )

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Faculty Template" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        archive.writestr("xl/sharedStrings.xml", shared_xml)
    return buffer.getvalue()

# --- Departments ---
@router.post("/departments", response_model=schemas.Department)
def create_department(dept: schemas.DepartmentCreate, db: Session = Depends(database.get_db)):
    db_dept = models.Department(
        name=dept.name,
        code=dept.code
    )
    db.add(db_dept)
    db.commit()
    db.refresh(db_dept)
    return db_dept

@router.get("/departments", response_model=List[schemas.Department])
def read_departments(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.Department).offset(skip).limit(limit).all()

@router.put("/departments/{dept_id}", response_model=schemas.Department)
def update_department(dept_id: int, dept: schemas.DepartmentCreate, db: Session = Depends(database.get_db)):
    db_dept = db.query(models.Department).filter(models.Department.id == dept_id).first()
    if not db_dept:
        raise HTTPException(status_code=404, detail="Department not found")
    db_dept.name = dept.name
    db_dept.code = dept.code
    db.commit()
    db.refresh(db_dept)
    return db_dept

@router.delete("/departments/{dept_id}")
def delete_department(dept_id: int, db: Session = Depends(database.get_db)):
    dept = db.query(models.Department).filter(models.Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    db.delete(dept)
    db.commit()
    return {"message": "Department deleted"}

# --- Academic Years ---
@router.post("/academic-years", response_model=schemas.AcademicYear)
def create_academic_year(year: schemas.AcademicYearCreate, db: Session = Depends(database.get_db)):
    if year.level < 1 or year.level > 4:
        raise HTTPException(status_code=400, detail="Year level must be between 1 and 4.")
    db_year = models.AcademicYear(**year.dict())
    db.add(db_year)
    db.commit()
    db.refresh(db_year)
    return db_year

@router.get("/academic-years", response_model=List[schemas.AcademicYear])
def read_academic_years(department_id: int = None, db: Session = Depends(database.get_db)):
    q = db.query(models.AcademicYear)
    if department_id:
        q = q.filter(models.AcademicYear.department_id == department_id)
    return q.all()

@router.put("/academic-years/{year_id}", response_model=schemas.AcademicYear)
def update_academic_year(year_id: int, year: schemas.AcademicYearCreate, db: Session = Depends(database.get_db)):
    if year.level < 1 or year.level > 4:
        raise HTTPException(status_code=400, detail="Year level must be between 1 and 4.")
    db_year = db.query(models.AcademicYear).filter(models.AcademicYear.id == year_id).first()
    if not db_year:
        raise HTTPException(status_code=404, detail="Academic Year not found")
    db_year.name = year.name
    db_year.level = year.level
    db.commit()
    db.refresh(db_year)
    return db_year

@router.delete("/academic-years/{year_id}")
def delete_academic_year(year_id: int, db: Session = Depends(database.get_db)):
    year = db.query(models.AcademicYear).filter(models.AcademicYear.id == year_id).first()
    if not year:
        raise HTTPException(status_code=404, detail="Academic Year not found")
    db.delete(year)
    db.commit()
    return {"message": "Academic Year deleted"}

# --- Sections ---
@router.post("/sections", response_model=schemas.Section)
def create_section(section: schemas.SectionCreate, db: Session = Depends(database.get_db)):
    year = db.query(models.AcademicYear).filter(models.AcademicYear.id == section.academic_year_id).first()
    if not year:
        raise HTTPException(status_code=404, detail="Academic Year not found")

    effective_name = (section.section_name or section.name or "").strip()
    if not effective_name:
        raise HTTPException(status_code=400, detail="Section name is required")

    db_section = models.Section(
        name=effective_name,
        section_name=effective_name,
        year=section.year if section.year is not None else year.level,
        academic_year_id=section.academic_year_id,
        student_count=section.student_count,
        independent_schedule=section.independent_schedule,
    )
    db.add(db_section)
    db.commit()
    db.refresh(db_section)
    return db_section

@router.get("/sections", response_model=List[schemas.Section])
def read_sections(
    year_id: Optional[int] = None,
    department_id: Optional[int] = None,
    department: Optional[str] = None,
    semester: Optional[int] = None,
    db: Session = Depends(database.get_db)
):
    q = db.query(models.Section)
    if year_id is not None:
        q = q.filter(models.Section.academic_year_id == year_id)
    
    if department_id is not None or department is not None or semester is not None:
        q = q.join(models.AcademicYear)
        if department_id is not None:
            q = q.filter(models.AcademicYear.department_id == department_id)
        elif department is not None:
            if department.isdigit():
                q = q.filter(models.AcademicYear.department_id == int(department))
            else:
                q = q.join(models.Department, models.AcademicYear.department_id == models.Department.id).filter(models.Department.code == department)
        if semester is not None:
            target_level = (semester + 1) // 2
            q = q.filter(models.AcademicYear.level == target_level)
            
    return q.all()

@router.put("/sections/{section_id}", response_model=schemas.Section)
def update_section(section_id: int, section: schemas.SectionCreate, db: Session = Depends(database.get_db)):
    db_section = db.query(models.Section).filter(models.Section.id == section_id).first()
    if not db_section:
        raise HTTPException(status_code=404, detail="Section not found")

    year = db.query(models.AcademicYear).filter(models.AcademicYear.id == section.academic_year_id).first()
    if not year:
        raise HTTPException(status_code=404, detail="Academic Year not found")

    effective_name = (section.section_name or section.name or "").strip()
    if not effective_name:
        raise HTTPException(status_code=400, detail="Section name is required")

    db_section.name = effective_name
    db_section.section_name = effective_name
    db_section.year = section.year if section.year is not None else year.level
    db_section.academic_year_id = section.academic_year_id
    db_section.student_count = section.student_count
    db_section.independent_schedule = section.independent_schedule
    db.commit()
    db.refresh(db_section)
    return db_section

@router.delete("/sections/{section_id}")
def delete_section(section_id: int, db: Session = Depends(database.get_db)):
    section = db.query(models.Section).filter(models.Section.id == section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    db.delete(section)
    db.commit()
    return {"message": "Section deleted"}


@router.get("/rules", response_model=schemas.SchedulingRule)
def read_rules(
    department_id: Optional[int] = None,
    db: Session = Depends(database.get_db),
):
    query = db.query(models.SchedulingRule).filter(
        models.SchedulingRule.department_id == department_id,
        models.SchedulingRule.name == "default",
    ).order_by(models.SchedulingRule.id.desc())
    rules = query.first()
    if rules:
        return rules

    if department_id is not None:
        global_rules = db.query(models.SchedulingRule).filter(
            models.SchedulingRule.department_id.is_(None),
            models.SchedulingRule.name == "default",
            models.SchedulingRule.is_active == True,
        ).order_by(models.SchedulingRule.id.desc()).first()
        if global_rules:
            return global_rules

    new_rules = models.SchedulingRule(
        department_id=department_id,
        name="default",
        rules=_default_rule_payload(),
        is_active=True,
    )
    db.add(new_rules)
    db.commit()
    db.refresh(new_rules)
    return new_rules


@router.put("/rules", response_model=schemas.SchedulingRule)
def upsert_rules(
    payload: schemas.SchedulingRuleUpdate,
    db: Session = Depends(database.get_db),
):
    row = db.query(models.SchedulingRule).filter(
        models.SchedulingRule.department_id == payload.department_id,
        models.SchedulingRule.name == payload.name,
    ).order_by(models.SchedulingRule.id.desc()).first()

    if row:
        row.rules = payload.rules
        row.is_active = payload.is_active
    else:
        row = models.SchedulingRule(
            department_id=payload.department_id,
            name=payload.name,
            rules=payload.rules,
            is_active=payload.is_active,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    return row



# --- Subjects ---
@router.post("/subjects", response_model=schemas.Subject)
def create_subject(subject: schemas.SubjectCreate, db: Session = Depends(database.get_db)):
    # Verify primary department exists
    dept = db.query(models.Department).filter(models.Department.id == subject.department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Primary Department not found")

    existing_subject = db.query(models.Subject).filter(
        models.Subject.department_id == subject.department_id,
        models.Subject.code == subject.code,
    ).first()
    if existing_subject:
        raise HTTPException(status_code=400, detail="Subject code already exists in this department")

    db_subject = models.Subject(**subject.dict())
    db.add(db_subject)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Subject code already exists in this department")
    db.refresh(db_subject)
    return db_subject

@router.get("/subjects", response_model=List[schemas.Subject])
def read_subjects(
    department_id: Optional[int] = None,
    department: Optional[str] = None,
    semester: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(database.get_db)
):
    q = db.query(models.Subject)
    if department_id is not None:
        q = q.filter(models.Subject.department_id == department_id)
    elif department is not None:
        if department.isdigit():
            q = q.filter(models.Subject.department_id == int(department))
        else:
            q = q.join(models.Department).filter(models.Department.code == department)
    if semester is not None:
        q = q.filter(models.Subject.semester == semester)
    return q.offset(skip).limit(limit).all()

@router.put("/subjects/{subject_id}", response_model=schemas.Subject)
def update_subject(subject_id: int, subject: schemas.SubjectCreate, db: Session = Depends(database.get_db)):
    db_subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not db_subject:
         raise HTTPException(status_code=404, detail="Subject not found")

    existing_subject = db.query(models.Subject).filter(
        models.Subject.department_id == subject.department_id,
        models.Subject.code == subject.code,
        models.Subject.id != subject_id,
    ).first()
    if existing_subject:
        raise HTTPException(status_code=400, detail="Subject code already exists in this department")
    
    db_subject.name = subject.name
    db_subject.code = subject.code
    db_subject.department_id = subject.department_id
    db_subject.semester = subject.semester
    db_subject.subject_type = subject.subject_type
    db_subject.weekly_hours = subject.weekly_hours
    db_subject.continuous_hours = subject.continuous_hours
    db_subject.manual_timeslot_ids = subject.manual_timeslot_ids
    db_subject.is_elective = subject.is_elective
    db_subject.elective_group_id = subject.elective_group_id
    db_subject.allowed_department_ids = subject.allowed_department_ids
    
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Subject code already exists in this department")
    db.refresh(db_subject)
    return db_subject

@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: int, db: Session = Depends(database.get_db)):
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not subject:
         raise HTTPException(status_code=404, detail="Subject not found")
    
    # Delete related faculty subject assignments
    db.query(models.FacultySubjectAssignment).filter(
        models.FacultySubjectAssignment.subject_id == subject_id
    ).delete()
    
    # Delete related timetable entries
    db.query(models.TimetableEntry).filter(
        models.TimetableEntry.subject_id == subject_id
    ).delete()
    
    # Now delete the subject
    db.delete(subject)
    db.commit()
    return {"message": "Subject deleted"}

# --- Faculty ---
@router.post("/faculty", response_model=schemas.Faculty)
def create_faculty(faculty: schemas.FacultyCreate, db: Session = Depends(database.get_db)):
    # Handle Many-to-Many Departments
    db_faculty = models.Faculty(
        name=faculty.name,
        faculty_id_code=faculty.faculty_id_code,
        faculty_type=faculty.faculty_type,
        min_hours_per_week=faculty.min_hours_per_week,
        max_hours_per_week=faculty.max_hours_per_week,
        preferred_slots=faculty.preferred_slots,
        user_id=faculty.user_id
    )
    
    if faculty.department_ids:
        depts = db.query(models.Department).filter(models.Department.id.in_(faculty.department_ids)).all()
        db_faculty.departments = depts
        
    db.add(db_faculty)
    db.commit()
    db.refresh(db_faculty)
    return db_faculty

@router.get("/faculty/template")
def download_faculty_template():
    template_bytes = _build_template_xlsx()
    headers = {
        "Content-Disposition": 'attachment; filename="faculty_bulk_template.xlsx"'
    }
    return StreamingResponse(
        io.BytesIO(template_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )

@router.get("/faculty", response_model=List[schemas.Faculty])
def read_faculty(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.Faculty).offset(skip).limit(limit).all()

@router.post("/faculty/bulk", response_model=schemas.FacultyBulkResult)
def create_faculty_bulk(payload: schemas.FacultyBulkCreate, db: Session = Depends(database.get_db)):
    if not payload.rows:
        raise HTTPException(status_code=400, detail="At least one faculty row is required")
    return _create_faculty_records(payload.rows, db)

@router.post("/faculty/bulk-upload", response_model=schemas.FacultyBulkResult)
async def upload_faculty_bulk(file: UploadFile = File(...), db: Session = Depends(database.get_db)) :
    filename = file.filename or ""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        if extension == "csv":
            raw_rows = _parse_csv_rows(file_bytes)
        elif extension == "xlsx":
            raw_rows = _read_xlsx_rows(file_bytes)
        else:
            raise HTTPException(status_code=400, detail="Only .csv and .xlsx files are supported")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}")

    if not raw_rows:
        raise HTTPException(status_code=400, detail="No faculty rows found in the uploaded file")

    rows: List[schemas.FacultyBulkRow] = []
    errors: List[str] = []

    for index, row in enumerate(raw_rows, start=1):
        try:
            name_val = _find_field(row, ["name", "faculty_name", "full_name", "facultyname", "fullname"])
            id_val = _find_field(row, ["faculty_id_code", "faculty_code", "id_code", "idcode", "id", "code", "faculty_id"])

            name = str(name_val or "").strip()
            faculty_id_code = str(id_val or "").strip() or None

            if not name and not faculty_id_code:
                raise ValueError("ID and Name are missing")
            elif not name:
                raise ValueError("Name is missing")
            elif not faculty_id_code:
                raise ValueError("ID is missing")

            faculty_type = str(_find_field(row, ["faculty_type", "designation", "faculty_designation", "type", "role"]) or "ASSISTANT_PROFESSOR").strip()
            
            min_hrs = _parse_int(_find_field(row, ["min_hours_per_week", "min_hours", "min_load", "min", "minhours"]), 5)
            max_hrs = _parse_int(_find_field(row, ["max_hours_per_week", "max_hours", "max_load", "max", "maxhours"]), 18)
            
            dept_codes = _split_department_codes(_find_field(row, ["department_codes", "department_code", "departments", "department", "dept", "depts", "dept_codes", "deptcodes"]))

            bulk_row = schemas.FacultyBulkRow(
                name=name,
                faculty_id_code=faculty_id_code,
                faculty_type=faculty_type,
                min_hours_per_week=min_hrs,
                max_hours_per_week=max_hrs,
                department_codes=dept_codes,
                row_number=index
            )
            rows.append(bulk_row)
        except Exception as exc:
            errors.append(f"Row {index}: {exc}")

    # Process database records creation
    res = _create_faculty_records(rows, db)
    
    # Merge errors
    all_errors = errors + res["errors"]
    
    # Sort errors based on row index
    def get_row_num(err_msg):
        try:
            if err_msg.startswith("Row "):
                parts = err_msg.split(":", 1)
                return int(parts[0].split()[1])
        except Exception:
            pass
        return 999999
    all_errors.sort(key=get_row_num)

    return {
        "created_count": res["created_count"],
        "errors": all_errors
    }


@router.put("/faculty/{faculty_id}", response_model=schemas.Faculty)
def update_faculty(faculty_id: int, faculty: schemas.FacultyCreate, db: Session = Depends(database.get_db)):
    db_faculty = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not db_faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
        
    db_faculty.name = faculty.name
    db_faculty.faculty_id_code = faculty.faculty_id_code
    db_faculty.faculty_type = faculty.faculty_type
    db_faculty.min_hours_per_week = faculty.min_hours_per_week
    db_faculty.max_hours_per_week = faculty.max_hours_per_week
    db_faculty.preferred_slots = faculty.preferred_slots

    if faculty.department_ids is not None:
         depts = db.query(models.Department).filter(models.Department.id.in_(faculty.department_ids)).all()
         db_faculty.departments = depts
    
    db.commit()
    db.refresh(db_faculty)
    return db_faculty

@router.delete("/faculty/{faculty_id}")
def delete_faculty(faculty_id: int, db: Session = Depends(database.get_db)):
    faculty = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    
    # Delete related faculty subject assignments first
    db.query(models.FacultySubjectAssignment).filter(
        models.FacultySubjectAssignment.faculty_id == faculty_id
    ).delete()
    
    # Delete related timetable entries
    db.query(models.TimetableEntry).filter(
        models.TimetableEntry.faculty_id == faculty_id
    ).delete()
    
    # Now delete the faculty
    db.delete(faculty)
    db.commit()
    return {"message": "Faculty deleted"}

@router.post("/faculty/{faculty_id}/subjects", response_model=List[schemas.FacultySubjectAssignment])
def assign_faculty_subjects(faculty_id: int, assignments: List[schemas.FacultySubjectAssignmentCreate], db: Session = Depends(database.get_db)):
    # 1. Verify Faculty Exists
    faculty = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")

    # 2. Clear existing assignments (Simple replacement strategy)
    db.query(models.FacultySubjectAssignment).filter(models.FacultySubjectAssignment.faculty_id == faculty_id).delete()
    
    # 3. Add new assignments
    new_assignments = []
    for assignment in assignments:
        # Verify subject exists
        subject = db.query(models.Subject).filter(models.Subject.id == assignment.subject_id).first()
        if not subject:
             # Option: Skip or Raise. Raising ensures data integrity.
             raise HTTPException(status_code=404, detail=f"Subject ID {assignment.subject_id} not found")
        
        db_assignment = models.FacultySubjectAssignment(
            faculty_id=faculty_id,
            subject_id=assignment.subject_id,
            preference_level=assignment.preference_level,
            section_ids=assignment.section_ids  # Store section assignments
        )
        db.add(db_assignment)
        new_assignments.append(db_assignment)
    
    db.commit()
    
    # 4. Refresh to get relationships loaded if needed, or just return list
    # Re-querying to ensure 'subject' relationship is populated for response
    return db.query(models.FacultySubjectAssignment).filter(models.FacultySubjectAssignment.faculty_id == faculty_id).all()

# --- TimeSlots ---

def _time_to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _minutes_to_time(value: int) -> time:
    return (datetime.min + timedelta(minutes=value)).time()


def _department_timeslot_query(db: Session, department_id: Optional[int]):
    q = db.query(models.TimeSlot)
    if department_id is not None:
        return q.filter(models.TimeSlot.department_id == department_id)
    return q


@router.post("/departments/{department_id}/schedule/build", response_model=List[schemas.TimeSlot])
def build_department_schedule(
    department_id: int,
    schedule: schemas.DepartmentScheduleBuildRequest,
    db: Session = Depends(database.get_db),
):
    department = db.query(models.Department).filter(models.Department.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    existing_slot_ids = [slot.id for slot in db.query(models.TimeSlot.id).filter(models.TimeSlot.department_id == department_id).all()]
    if existing_slot_ids:
        entry_count = db.query(models.TimetableEntry).filter(
            models.TimetableEntry.timeslot_id.in_(existing_slot_ids)
        ).count()
        if entry_count:
            raise HTTPException(
                status_code=400,
                detail="Clear generated timetables for this department before rebuilding its schedule",
            )

    start = _time_to_minutes(schedule.start_time)
    end = _time_to_minutes(schedule.end_time)
    break_start = _time_to_minutes(schedule.break_start)
    break_end = _time_to_minutes(schedule.break_end)
    lunch_start = _time_to_minutes(schedule.lunch_start)
    lunch_end = _time_to_minutes(schedule.lunch_end)

    special_blocks = sorted([
        (break_start, break_end, "Break"),
        (lunch_start, lunch_end, "Lunch"),
    ])

    if not schedule.days:
        raise HTTPException(status_code=400, detail="Select at least one working day")
    if not (start < break_start < break_end <= lunch_start < lunch_end < end):
        raise HTTPException(status_code=400, detail="Use valid start/end, break, and lunch times in order")

    db.query(models.TimeSlot).filter(models.TimeSlot.department_id == department_id).delete(synchronize_session=False)

    new_slots = []
    for day in schedule.days:
        cursor = start
        while cursor < end:
            block = next((item for item in special_blocks if item[0] == cursor), None)
            if block:
                block_start, block_end, label = block
                new_slots.append(models.TimeSlot(
                    department_id=department_id,
                    day=day,
                    start_time=_minutes_to_time(block_start),
                    end_time=_minutes_to_time(block_end),
                    is_break=True,
                    label=label,
                ))
                cursor = block_end
                continue

            next_special_start = min([item[0] for item in special_blocks if item[0] > cursor] + [end])
            class_end = min(cursor + 60, next_special_start, end)
            if class_end - cursor == 60:
                new_slots.append(models.TimeSlot(
                    department_id=department_id,
                    day=day,
                    start_time=_minutes_to_time(cursor),
                    end_time=_minutes_to_time(class_end),
                    is_break=False,
                    label="Class",
                ))
            cursor = class_end if class_end > cursor else cursor + 60

    db.add_all(new_slots)
    db.commit()
    return db.query(models.TimeSlot).filter(models.TimeSlot.department_id == department_id).order_by(
        models.TimeSlot.day,
        models.TimeSlot.start_time,
    ).all()


@router.post("/timeslots", response_model=schemas.TimeSlot)
def create_timeslot(timeslot: schemas.TimeSlotCreate, db: Session = Depends(database.get_db)):
    db_timeslot = models.TimeSlot(**timeslot.dict())
    db.add(db_timeslot)
    db.commit()
    db.refresh(db_timeslot)
    return db_timeslot

@router.get("/timeslots", response_model=List[schemas.TimeSlot])
def read_timeslots(department_id: Optional[int] = None, skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return _department_timeslot_query(db, department_id).offset(skip).limit(limit).all()

@router.put("/timeslots/{timeslot_id}", response_model=schemas.TimeSlot)
def update_timeslot(timeslot_id: int, timeslot: schemas.TimeSlotCreate, db: Session = Depends(database.get_db)):
    db_timeslot = db.query(models.TimeSlot).filter(models.TimeSlot.id == timeslot_id).first()
    if not db_timeslot:
        raise HTTPException(status_code=404, detail="TimeSlot not found")
    
    db_timeslot.day = timeslot.day
    db_timeslot.department_id = timeslot.department_id
    db_timeslot.start_time = timeslot.start_time
    db_timeslot.end_time = timeslot.end_time
    db_timeslot.is_break = timeslot.is_break
    db_timeslot.label = timeslot.label
    
    db.commit()
    db.refresh(db_timeslot)
    return db_timeslot

@router.delete("/timeslots/{timeslot_id}")
def delete_timeslot(timeslot_id: int, db: Session = Depends(database.get_db)):
    timeslot = db.query(models.TimeSlot).filter(models.TimeSlot.id == timeslot_id).first()
    if not timeslot:
        raise HTTPException(status_code=404, detail="TimeSlot not found")
    db.delete(timeslot)
    db.commit()
    return {"message": "TimeSlot deleted"}


# --- Filtered/ ERP Faculty Assignment Endpoints ---

@router.get("/departments/{dept_id}/years", response_model=List[schemas.AcademicYear])
def get_department_years(dept_id: int, db: Session = Depends(database.get_db)):
    return db.query(models.AcademicYear).filter(
        models.AcademicYear.department_id == dept_id
    ).order_by(models.AcademicYear.level, models.AcademicYear.name).all()


@router.get("/departments/{dept_id}/semesters", response_model=List[int])
def get_department_semesters(dept_id: int, db: Session = Depends(database.get_db)):
    years = db.query(models.AcademicYear).filter(models.AcademicYear.department_id == dept_id).all()
    semesters = set()
    for y in years:
        semesters.add(2 * y.level - 1)
        semesters.add(2 * y.level)
    return sorted(list(semesters))


@router.get("/faculty/{faculty_id}/assignments", response_model=List[schemas.FacultySubjectAssignment])
def get_faculty_assignments(faculty_id: int, db: Session = Depends(database.get_db)):
    faculty = db.query(models.Faculty.id).filter(models.Faculty.id == faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return _faculty_assignment_query(db, faculty_id).all()


def _faculty_assignment_query(db: Session, faculty_id: int):
    return db.query(models.FacultySubjectAssignment).options(
        selectinload(models.FacultySubjectAssignment.subject)
    ).filter(models.FacultySubjectAssignment.faculty_id == faculty_id).order_by(
        models.FacultySubjectAssignment.id
    )


def _validate_assignment_sections(
    db: Session,
    subject: models.Subject,
    section_ids: Optional[List[int]],
) -> Optional[List[int]]:
    if not section_ids:
        return None

    normalized_ids = list(dict.fromkeys(section_ids))
    sections = db.query(models.Section).options(
        selectinload(models.Section.academic_year)
    ).filter(models.Section.id.in_(normalized_ids)).all()
    sections_by_id = {section.id: section for section in sections}
    missing_ids = [section_id for section_id in normalized_ids if section_id not in sections_by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Section IDs not found: {missing_ids}")

    allowed_department_ids = set(subject.allowed_department_ids or [])
    if subject.department_id is not None:
        allowed_department_ids.add(subject.department_id)
    expected_level = (subject.semester + 1) // 2
    invalid_sections = [
        section.name or f"Section {section.id}"
        for section in sections
        if not section.academic_year
        or section.academic_year.department_id not in allowed_department_ids
        or section.academic_year.level != expected_level
    ]
    if invalid_sections:
        raise HTTPException(
            status_code=400,
            detail=(
                "Sections do not match the subject department/semester: "
                + ", ".join(sorted(invalid_sections))
            ),
        )
    return normalized_ids


def _ensure_assignment_does_not_overlap(
    db: Session,
    faculty_id: int,
    subject_id: int,
    section_ids: Optional[List[int]],
    exclude_assignment_id: Optional[int] = None,
) -> None:
    query = db.query(models.FacultySubjectAssignment).filter(
        models.FacultySubjectAssignment.faculty_id == faculty_id,
        models.FacultySubjectAssignment.subject_id == subject_id,
    )
    if exclude_assignment_id is not None:
        query = query.filter(models.FacultySubjectAssignment.id != exclude_assignment_id)
    existing_assignments = query.all()
    if not existing_assignments:
        return

    if section_ids is None or any(not assignment.section_ids for assignment in existing_assignments):
        raise HTTPException(
            status_code=400,
            detail="Duplicate assignment: this subject already has an all-sections assignment.",
        )

    existing_sections = {
        section_id
        for assignment in existing_assignments
        for section_id in (assignment.section_ids or [])
    }
    duplicates = [section_id for section_id in section_ids if section_id in existing_sections]
    if duplicates:
        section_names = db.query(models.Section.name).filter(models.Section.id.in_(duplicates)).all()
        names = ", ".join(name for (name,) in section_names) or ", ".join(map(str, duplicates))
        raise HTTPException(
            status_code=400,
            detail=f"Duplicate assignment: Section(s) '{names}' already assigned.",
        )


@router.post("/faculty/{faculty_id}/assignments", response_model=schemas.FacultySubjectAssignment)
def create_faculty_assignment(
    faculty_id: int,
    payload: schemas.FacultySubjectAssignmentCreate,
    db: Session = Depends(database.get_db)
):
    # 1. Verify Faculty Exists
    faculty = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")

    # 2. Verify Subject Exists
    subject = db.query(models.Subject).filter(models.Subject.id == payload.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    section_ids = _validate_assignment_sections(db, subject, payload.section_ids)
    _ensure_assignment_does_not_overlap(db, faculty_id, payload.subject_id, section_ids)

    # 4. Create assignment
    db_assignment = models.FacultySubjectAssignment(
        faculty_id=faculty_id,
        subject_id=payload.subject_id,
        preference_level=payload.preference_level,
        section_ids=section_ids
    )
    db.add(db_assignment)
    db.flush()
    assignment_id = db_assignment.id
    db.commit()
    return _faculty_assignment_query(db, faculty_id).filter(
        models.FacultySubjectAssignment.id == assignment_id
    ).first()


@router.put("/faculty/{faculty_id}/assignments/{assignment_id}", response_model=schemas.FacultySubjectAssignment)
def update_faculty_assignment(
    faculty_id: int,
    assignment_id: int,
    payload: schemas.FacultySubjectAssignmentCreate,
    db: Session = Depends(database.get_db)
):
    db_assignment = db.query(models.FacultySubjectAssignment).filter(
        models.FacultySubjectAssignment.id == assignment_id,
        models.FacultySubjectAssignment.faculty_id == faculty_id
    ).first()
    if not db_assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    subject = db.query(models.Subject).filter(models.Subject.id == payload.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    section_ids = _validate_assignment_sections(db, subject, payload.section_ids)
    _ensure_assignment_does_not_overlap(
        db,
        faculty_id,
        payload.subject_id,
        section_ids,
        exclude_assignment_id=assignment_id,
    )

    db_assignment.subject_id = payload.subject_id
    db_assignment.section_ids = section_ids
    db_assignment.preference_level = payload.preference_level
    db.commit()
    return _faculty_assignment_query(db, faculty_id).filter(
        models.FacultySubjectAssignment.id == assignment_id
    ).first()


@router.delete("/faculty/{faculty_id}/assignments/{assignment_id}")
def delete_faculty_assignment(faculty_id: int, assignment_id: int, db: Session = Depends(database.get_db)):
    db_assignment = db.query(models.FacultySubjectAssignment).filter(
        models.FacultySubjectAssignment.id == assignment_id,
        models.FacultySubjectAssignment.faculty_id == faculty_id
    ).first()
    if not db_assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(db_assignment)
    db.commit()
    return {"message": "Assignment deleted"}
