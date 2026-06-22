import os
import sys
import time

print("Script started...")

# Add DLL directory to ensure libpq is found by psycopg
try:
    os.add_dll_directory(r"C:\Program Files\PostgreSQL\18\pgAdmin 4\runtime")
    print("Added DLL directory successfully.")
except AttributeError:
    os.environ["PATH"] += os.pathsep + r"C:\Program Files\PostgreSQL\18\pgAdmin 4\runtime"
    print("Added to PATH environment variable.")
except Exception as e:
    print("Warning adding DLL directory:", e)

from sqlalchemy import create_engine, text

# Try 127.0.0.1
print("Attempting connection to 127.0.0.1:5435...")
try:
    engine = create_engine(
        "postgresql+psycopg://admin:password@127.0.0.1:5435/timewise",
        connect_args={"connect_timeout": 3}
    )
    with engine.connect() as conn:
        print("Successfully connected to 127.0.0.1:5435!")
        # Run a query
        res = conn.execute(text("SELECT id, name FROM academic_years"))
        for row in res:
            print(f"Year ID: {row[0]}, Name: {row[1]}")
except Exception as e:
    print("Failed to connect to 127.0.0.1:5435:", e)

# Try localhost
print("Attempting connection to localhost:5435...")
try:
    engine = create_engine(
        "postgresql+psycopg://admin:password@localhost:5435/timewise",
        connect_args={"connect_timeout": 3}
    )
    with engine.connect() as conn:
        print("Successfully connected to localhost:5435!")
        res = conn.execute(text("SELECT id, name FROM academic_years"))
        for row in res:
            print(f"Year ID: {row[0]}, Name: {row[1]}")
except Exception as e:
    print("Failed to connect to localhost:5435:", e)

print("Script finished.")
