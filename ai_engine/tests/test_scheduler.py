import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_unoptimized_request():
    # Submit an invalid request to test Error handling
    payload = {}
    response = client.post("/optimize", json=payload)
    # Pydantic validation error should be 422
    assert response.status_code == 422

def test_health_check_non_existent():
    response = client.get("/non-existent")
    assert response.status_code == 404
