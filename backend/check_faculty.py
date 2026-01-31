from database import SessionLocal
from models import Faculty
from sqlalchemy import text

# This script uses the DATABASE_URL defined in .env or database.py
# It is now database-agnostic (works for Postgres or SQLite)

try:
    db = SessionLocal()
    
    # Check connection
    db.execute(text("SELECT 1"))
    print("Database connection successful.")

    faculty_count = db.query(Faculty).count()
    print(f"Total Faculty in DB: {faculty_count}")
    
    faculty_list = db.query(Faculty).all()
    for f in faculty_list:
        print(f"ID: {f.id}, Name: {f.name}, Code: {f.faculty_id_code}")
        
    db.close()
except Exception as e:
    print(f"Error connecting or querying database: {e}")
