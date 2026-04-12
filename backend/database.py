from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@localhost:5432/timewise")

engine = create_engine(DATABASE_URL)


import time
import logging
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

def wait_for_db(retries=10, delay=2):
    for i in range(retries):
        try:
            # Try to connect
            with engine.connect() as conn:
                logger.info("Database connection successful!")
                return
        except OperationalError:
            logger.warning(f"Database unavailable, waiting {delay}s... ({i+1}/{retries})")
            time.sleep(delay)
    logger.error("Could not connect to database after several retries.")

# The call to wait_for_db should be done within the application startup

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
