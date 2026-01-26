# TimeWise AI

TimeWise is an intelligent timetable management system designed to streamline academic scheduling. It features a modern, responsive UI and a powerful conflict-resolution algorithm.

## 🚀 Quick Start

### 1. Database Setup (Docker)
The project uses PostgreSQL running in a Docker container.
```bash
# Start the database container
docker-compose up -d db

# (First Time Only) Initialize the database schema
# The backend will automatically create tables on startup.
```

### 2. Backend Setup (FastAPI)
Navigate to the backend directory and start the server.
```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
-   **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

### 3. Frontend Setup (React + Vite)
Navigate to the frontend directory and start the development server.
```bash
cd frontend

# Install dependencies (if not already installed)
npm install

# Run the dev server
npm run dev
```
-   **App URL**: [http://localhost:3000](http://localhost:3000) (or 5173)

---

## 🔑 Default Credentials
-   **Username**: `admin`
-   **Password**: `admin123`

---

## ✨ Features implemented
### Phase 1: Master Data Management
-   [x] **Department Management**: Add/Edit departments.
-   [x] **Faculty Management**: Manage faculty profiles and workload constraints.
-   [x] **Subject Allocation**: Assign subjects to departments and semesters.
-   [x] **Room Management**: Configure classrooms and labs.
-   [x] **Time Slot Configuration**: Define daily schedules and break times.

### Phase 2: Timetable Generation
-   [x] **Conflict-Free Algorithm**: Automatically generates schedules that respect:
    -   Faculty availability (no double booking).
    -   Room capacity and type (Lecture/Lab).
    -   Lunch/Break slots (vertical text indicators).
-   [x] **Modern UI**:
    -   clean, card-based interface using native CSS variables.
    -   Smooth animations with `framer-motion`.
    -   Interactive filtering by Department, Year, and Section.

---

## 🛠 Tech Stack
-   **Frontend**: React, Vite, Framer Motion, Lucide Icons.
-   **Backend**: Python, FastAPI, SQLAlchemy, Pydantic.
-   **Database**: PostgreSQL.
