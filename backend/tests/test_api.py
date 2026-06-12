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
