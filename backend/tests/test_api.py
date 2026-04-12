import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to TimeWise AI Backend API"}

def test_health_check_non_existent():
    response = client.get("/non-existent")
    assert response.status_code == 404
