import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
import sys
import importlib.util
from pathlib import Path
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) in sys.path:
    sys.path.remove(str(BACKEND_ROOT))
sys.path.insert(0, str(BACKEND_ROOT))

spec = importlib.util.spec_from_file_location("backend_main_for_tests", BACKEND_ROOT / "main.py")
backend_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend_main)
app = backend_main.app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to TimeWise AI Backend API"}

def test_health_check_non_existent():
    response = client.get("/non-existent")
    assert response.status_code == 404
