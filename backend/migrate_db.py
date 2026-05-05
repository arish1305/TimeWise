import sqlite3
import os

def migrate():
    db_path = os.path.join(os.path.dirname(__file__), 'timewise.db')
    print(f"Connecting to database at {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if allowed_department_ids exists
        cursor.execute("PRAGMA table_info(subjects);")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'allowed_department_ids' not in columns:
            print("Adding allowed_department_ids column to subjects table...")
            cursor.execute("ALTER TABLE subjects ADD COLUMN allowed_department_ids JSON DEFAULT '[]';")
            conn.commit()
            print("Migration successful.")
        else:
            print("Column allowed_department_ids already exists.")
            
        # Check if created_at exists in timetables
        cursor.execute("PRAGMA table_info(timetables);")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'created_at' not in columns:
            print("Adding created_at column to timetables table...")
            cursor.execute("ALTER TABLE timetables ADD COLUMN created_at DATETIME;")
            cursor.execute("UPDATE timetables SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL;")
            conn.commit()
            print("Migration of created_at successful.")
        else:
            print("Column created_at already exists.")
            
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == '__main__':
    migrate()
