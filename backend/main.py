from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import auth, admin, timetable
from database import engine, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="TimeWise AI Backend", version="0.1.0")

# Auto-seed on startup
from seed import seed
@app.on_event("startup")
def on_startup():
    seed()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
