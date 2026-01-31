from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@localhost:5432/timewise")

engine = create_engine(DATABASE_URL)


import time
from sqlalchemy.exc import OperationalError

def wait_for_db(retries=10, delay=2):
    for i in range(retries):
        try:
            # Try to connect
            with engine.connect() as conn:
                print("Database connection successful!")
                return
        except OperationalError:
            print(f"Database unavailable, waiting {delay}s... ({i+1}/{retries})")
            time.sleep(delay)
    print("Could not connect to database after several retries.")

# Attempt connection before creating session/metadata
wait_for_db()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
