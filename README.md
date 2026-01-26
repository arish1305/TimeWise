# TimeWise AI

## Setup & Run

1.  **Prerequisites**: Docker & Docker Compose installed.
2.  **Start Services**:
    ```bash
    docker-compose up --build
    ```
3.  **Access Application**:
    -   Frontend: [http://localhost:3000](http://localhost:3000)
    -   Backend API: [http://localhost:8000/docs](http://localhost:8000/docs)
    -   AI Engine: [http://localhost:8001/docs](http://localhost:8001/docs)

## Default Credentials
-   **Username**: `admin`
-   **Password**: `admin123`

## Features
-   **Admin Dashboard**: Manage resources and trigger AI scheduling.
-   **AI Engine**: Constraint-based timetable optimization.
-   **Authentication**: JWT-based secure login.

## Seed Data
The system will start with empty data. To seed initial data (Admin user, etc.):
1.  Enter the backend container: `docker exec -it timewise_backend bash`
2.  Run seed script: `python seed.py`
