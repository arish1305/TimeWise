import os
import sys

# Add DLL directory to ensure libpq is found by psycopg
try:
    os.add_dll_directory(r"C:\Program Files\PostgreSQL\18\pgAdmin 4\runtime")
except AttributeError:
    # Older Python versions may not have add_dll_directory
    os.environ["PATH"] += os.pathsep + r"C:\Program Files\PostgreSQL\18\pgAdmin 4\runtime"
except Exception as e:
    print("Warning adding DLL directory:", e)

from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://admin:password@localhost:5435/timewise")

with engine.connect() as conn:
    print("--- ACADEMIC YEARS ---")
    res = conn.execute(text("SELECT id, name, level FROM academic_years"))
    for row in res:
        print(f"ID: {row[0]}, Name: {row[1]}, Level: {row[2]}")

    print("\n--- SECTIONS ---")
    res = conn.execute(text("SELECT id, name, academic_year_id, department_id FROM sections"))
    for row in res:
        print(f"ID: {row[0]}, Name: {row[1]}, Year ID: {row[2]}, Dept ID: {row[3]}")

    print("\n--- TIMETABLES ---")
    res = conn.execute(text("SELECT id, section_id, status, version FROM timetables"))
    for row in res:
        print(f"ID: {row[0]}, Section ID: {row[1]}, Status: {row[2]}, Version: {row[3]}")
