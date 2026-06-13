import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
import sys
import importlib.util
from pathlib import Path
from datetime import time
from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) in sys.path:
    sys.path.remove(str(BACKEND_ROOT))
sys.path.insert(0, str(BACKEND_ROOT))

import models

spec = importlib.util.spec_from_file_location("backend_main_for_tests", BACKEND_ROOT / "main.py")
backend_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend_main)
app = backend_main.app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to TimeWise AI Backend API"}

def test_health_check_non_existent():
    response = client.get("/non-existent")
    assert response.status_code == 404


def test_faculty_availability_api_bulk_update_and_reset():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    backend_main.Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()

    department = models.Department(name="API Department", code="APID")
    faculty = models.Faculty(name="Dr. API", faculty_id_code="API1")
    faculty.departments = [department]
    slot_one = models.TimeSlot(
        department_id=1,
        day="Monday",
        start_time=time(9, 0),
        end_time=time(10, 0),
        is_break=False,
    )
    slot_two = models.TimeSlot(
        department_id=1,
        day="Tuesday",
        start_time=time(10, 0),
        end_time=time(11, 0),
        is_break=False,
    )
    db.add_all([department, faculty, slot_one, slot_two])
    db.commit()
    db.refresh(faculty)
    db.refresh(slot_one)
    db.refresh(slot_two)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    backend_main.app.dependency_overrides[backend_main.faculty_availability.get_db] = override_get_db
    backend_main.app.dependency_overrides[backend_main.faculty_availability.auth.require_admin] = lambda: SimpleNamespace(
        username="admin",
        role=models.UserRole.ADMIN,
        user_id=1,
    )
    try:
        response = client.post(f"/faculty/{faculty.id}/availability", json={
            "entries": [
                {"timeslot_id": slot_one.id, "status": "PREFERRED"},
                {"timeslot_id": slot_two.id, "status": "UNAVAILABLE"},
            ]
        })
        assert response.status_code == 200
        statuses = {entry["timeslot_id"]: entry["status"] for entry in response.json()["entries"]}
        assert statuses[slot_one.id] == "PREFERRED"
        assert statuses[slot_two.id] == "UNAVAILABLE"

        duplicate_response = client.post(f"/faculty/{faculty.id}/availability", json={
            "entries": [
                {"timeslot_id": slot_one.id, "status": "PREFERRED"},
                {"timeslot_id": slot_one.id, "status": "UNAVAILABLE"},
            ]
        })
        assert duplicate_response.status_code == 400
        assert "Duplicate timeslot_id" in duplicate_response.json()["detail"]

        reset_response = client.delete(f"/faculty/{faculty.id}/availability")
        assert reset_response.status_code == 200
        assert reset_response.json()["deleted"] == 2

        get_response = client.get(f"/faculty/{faculty.id}/availability")
        assert get_response.status_code == 200
        assert {entry["status"] for entry in get_response.json()["entries"]} == {"AVAILABLE"}
    finally:
        backend_main.app.dependency_overrides.clear()
        db.close()


def test_faculty_bulk_onboarding_lenient():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    backend_main.Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()

    # Add department
    dept = models.Department(name="Computer Science Engineering", code="CSE")
    db.add(dept)
    db.commit()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    # Import admin router dependencies
    import database
    from routers.admin import auth
    backend_main.app.dependency_overrides[database.get_db] = override_get_db
    backend_main.app.dependency_overrides[auth.require_admin] = lambda: SimpleNamespace(
        username="admin",
        role=models.UserRole.ADMIN,
        user_id=1,
    )

    try:
        # Test manual bulk onboarding with custom designation (faculty_type)
        response = client.post("/admin/faculty/bulk", json={
            "rows": [
                {
                    "name": "Dr. John Doe",
                    "faculty_id_code": "FAC101",
                    "faculty_type": "Visiting Professor",
                    "min_hours_per_week": 6,
                    "max_hours_per_week": 12,
                    "department_codes": ["CSE"]
                },
                {
                    "name": "Dr. Missing ID",
                    "faculty_id_code": "",  # Missing ID
                    "faculty_type": "ASSISTANT_PROFESSOR",
                    "min_hours_per_week": 5,
                    "max_hours_per_week": 18,
                    "department_codes": ["CSE"]
                }
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["created_count"] == 1
        assert len(data["errors"]) == 1
        assert "Row 2: ID is missing" in data["errors"][0]

        # Verify Dr. John Doe was created with custom designation
        fac = db.query(models.Faculty).filter(models.Faculty.faculty_id_code == "FAC101").first()
        assert fac is not None
        assert fac.name == "Dr. John Doe"
        assert fac.faculty_type == "Visiting Professor"

        # Test bulk upload with CSV and flexible headers
        csv_content = (
            "Faculty Name,ID,Designation,Min Hours,Max Hours,Department Codes\n"
            "Dr. Alice Smith,FAC102,Senior Lecturer,4,16,CSE\n"
            ",FAC103,Professor,5,18,CSE\n" # Missing name
        )
        
        from io import BytesIO
        file = {"file": ("faculty.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")}
        
        upload_response = client.post("/admin/faculty/bulk-upload", files=file)
        assert upload_response.status_code == 200
        upload_data = upload_response.json()
        
        assert upload_data["created_count"] == 1
        assert len(upload_data["errors"]) == 1
        assert "Row 2: Name is missing" in upload_data["errors"][0]

        # Verify Alice Smith was created
        fac2 = db.query(models.Faculty).filter(models.Faculty.faculty_id_code == "FAC102").first()
        assert fac2 is not None
        assert fac2.name == "Dr. Alice Smith"
        assert fac2.faculty_type == "Senior Lecturer"
        
    finally:
        backend_main.app.dependency_overrides.clear()
        db.close()
