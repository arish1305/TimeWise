from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import time

DATABASE_URL = "postgresql://admin:password@localhost:5435/timewise"

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print("Connection Successful with postgres:admin1234!")
        
        # List tables in public schema
        result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        tables = [row[0] for row in result]

        if 'users' in tables:
            res = conn.execute(text("SELECT count(*) FROM users"))
            print(f"User count in timewise: {res.scalar()}")

        # Check other DBs?
        # Need to connect to 'postgres' db to list dbs usually, but can query pg_database from any db
        res = conn.execute(text("SELECT datname FROM pg_database WHERE datistemplate = false;"))
        dbs = [row[0] for row in res]
        print(f"Databases found: {dbs}")
        
        for t in tables:
             try:
                c = conn.execute(text(f"SELECT count(*) FROM {t}")).scalar()
                print(f"Table {t}: {c} rows")
             except:
                pass
        
except Exception as e:
    print(f"Connection Failed: {e}")
