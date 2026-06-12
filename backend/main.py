import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

# Set up logging for the backend
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from routers import auth, admin, timetable, faculty_availability
from database import (
    engine,
    Base,
    wait_for_db,
    migrate_subject_code_uniqueness,
    migrate_timeslot_departments,
    migrate_section_v2_fields,
    migrate_scheduling_rules,
    migrate_timetable_editing_v2,
    migrate_timetable_versions,
    migrate_faculty_availability,
)

app = FastAPI(title="TimeWise AI Backend", version="0.1.0")

# Auto-seed on startup
from seed import seed
@app.on_event("startup")
def on_startup():
    startup_lock_key = 502601
    lock_connection = None
    try:
        wait_for_db()
        if engine.dialect.name == "postgresql":
            lock_connection = engine.connect()
            lock_connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": startup_lock_key})

        Base.metadata.create_all(bind=engine)
        migrate_subject_code_uniqueness()
        migrate_timeslot_departments()
        migrate_section_v2_fields()
        migrate_scheduling_rules()
        migrate_timetable_editing_v2()
        migrate_timetable_versions()
        migrate_faculty_availability()
        seed()
    except Exception as e:
        logger.error(f"Startup error: {e}")
    finally:
        if lock_connection is not None:
            try:
                lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": startup_lock_key})
            finally:
                lock_connection.close()

import os

# Get allowed origins from environment variable, default to allowing all for backward compatibility in dev
ALLOWED_ORIGINS = os.getenv("BACKEND_CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(faculty_availability.router)
app.include_router(timetable.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to TimeWise AI Backend API"}
