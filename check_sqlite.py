from sqlalchemy import create_engine
from sqlalchemy import text

# Absolute path to be safe
DATABASE_URL = "sqlite:///d:/TimeWise/timewise.db"

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print("Connection Successful to SQLite!")
        
        # Check tables
        # List tables (SQLite specific)
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
        tables = [row[0] for row in result]
        print(f"Tables found: {tables}")
        
        if 'users' in tables:
            res = conn.execute(text("SELECT count(*) FROM users"))
            print(f"User count: {res.scalar()}")
            
        for t in tables:
            try:
                c = conn.execute(text(f"SELECT count(*) FROM {t}")).scalar()
                print(f"Table {t}: {c} rows")
            except:
                pass

except Exception as e:
    print(f"Connection Failed: {e}")
