# TimeWise AI: Intelligent Academic Scheduling System

TimeWise AI is a sophisticated, full-stack timetable management platform designed to automate and optimize academic scheduling. It combines a modern React-based user interface with a robust Python/FastAPI backend and a specialized AI scheduling engine to solve complex constraint-satisfaction problems in real-time.

---

## 🏗 System Architecture

```mermaid
graph TD
    User((User)) <--> Frontend[React/Vite Frontend]
    Frontend <--> Backend[FastAPI Backend]
    Backend <--> Postgres[(PostgreSQL DB)]
    Backend <--> AI_Engine[FastAPI AI Scheduler]
    AI_Engine --- Solver[CSP Conflict Solver]
```

---

## ✨ Features

### 📅 Advanced Scheduling
- **AI-Powered Generation**: Automatically generates conflict-free schedules respecting faculty, room, and time constraints.
- **CBCS (Choice Based Credit System)**: Supports elective subjects with parallel scheduling (multiple subjects in the same slot using different rooms).
- **Hybrid Scheduling**: Allows administrators to manually "lock" specific slots that the AI scheduler must respect.
- **Batch Generation**: Generates timetables for all sections/semesters across the entire department in one click.

### 🏫 Institutional Management
- **Departmental Hierarchy**: Manage Departments -> Academic Years -> Sections.
- **Master Data**: Centralized management of Faculty, Subjects, Rooms, and Timeslots.
- **Workload Balancing**: Automatically tracks and enforces faculty weekly hour limits.

### 🎨 User Experience
- **Premium UI**: Clean, card-based interface built with Vanilla CSS and modern typography.
- **Smooth Animations**: High-performance interactions powered by `framer-motion`.
- **Responsive Grid**: Interactive timetable grid with support for multi-subject (Elective) display.

---

## 🛠 Tech Stack

| Component | Technologies |
| :--- | :--- |
| **Frontend** | React 19, Vite, Framer Motion, Lucide Icons, Axios |
| **Backend** | Python 3.11, FastAPI, SQLAlchemy, Pydantic v2, JWT |
| **AI Engine** | Python 3.11, FastAPI, Custom CSP Solver Logic |
| **Database** | PostgreSQL 15 |
| **DevOps** | Docker, Docker Compose |

---

## 🚀 Getting Started

The recommended way to run TimeWise is using **Docker Compose**.

### Prerequisite: Environment Setup
Create a `.env` file in the `backend/` directory:
```env
DATABASE_URL="postgresql://admin:password@localhost:5435/timewise"
SECRET_KEY="your_secret_key"
ALGORITHM="HS256"
AI_ENGINE_URL="http://localhost:8001"
```

### Path A: Docker Setup (Recommended)
```bash
# Clone the repository
git clone <repository-url>
cd TimeWise

# Start all services (Database, Backend, AI Engine, Frontend)
docker-compose up --build
```
- **App URL**: [http://localhost:3000](http://localhost:3000)
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **AI Docs**: [http://localhost:8001/docs](http://localhost:8001/docs)

### Path B: Manual Development Setup

#### 1. Database
```bash
docker-compose up -d db
```

#### 2. AI Engine
```bash
cd ai_engine
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

#### 3. Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

#### 4. Frontend
```bash
cd frontend
npm install
npm run dev
```

---

## 🔑 Access
- **Default Admin Username**: `admin`
- **Default Admin Password**: `admin123`

---

## 📂 Project Structure
- `frontend/`: React source code, styles, and components.
- `backend/`: FastAPI application, SQL models, and business logic.
- `ai_engine/`: Specialized scheduling algorithms and solver service.
- `docker-compose.yml`: Multi-container orchestration config.
