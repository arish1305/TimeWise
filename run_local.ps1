Write-Host "Starting TimeWise AI Locally..."

# 1. Install Python Dependencies
Write-Host "Installing Backend Dependencies..."
pip install -r backend/requirements.txt
Write-Host "Installing AI Engine Dependencies..."
pip install -r ai_engine/requirements.txt

# 2. Configure Environment for SQLite
$env:DATABASE_URL = "sqlite:///./timewise.db"
$env:AI_ENGINE_URL = "http://localhost:8001"
$env:PYTHONPATH = "."

# 3. Seed Database
Write-Host "Seeding Database..."
python backend/seed.py

# 4. Start Services
Write-Host "Starting Backend (Port 8000)..."
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

Write-Host "Starting AI Engine (Port 8001)..."
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-m uvicorn ai_engine.main:app --host 0.0.0.0 --port 8001 --reload"

Write-Host "Starting Frontend (Port 3000)..."
Set-Location frontend
$env:VITE_API_URL = "http://localhost:8000"
npm run dev
