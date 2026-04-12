import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Set up logging for the backend
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from routers import auth, admin, timetable
from database import engine, Base, wait_for_db

app = FastAPI(title="TimeWise AI Backend", version="0.1.0")

# Auto-seed on startup
from seed import seed
@app.on_event("startup")
def on_startup():
    try:
        wait_for_db()
        Base.metadata.create_all(bind=engine)
        seed()
    except Exception as e:
        logger.error(f"Startup error: {e}")

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
app.include_router(timetable.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to TimeWise AI Backend API"}
