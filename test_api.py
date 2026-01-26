import requests
import json

BASE_URL = "http://localhost:8000/admin"

def test_create_department():
    print("Testing Create Department...")
    payload = {
        "name": "Test Dept",
        "code": "TEST"
    }
    try:
        response = requests.post(f"{BASE_URL}/departments", json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("SUCCESS: Department created.")
            return True
        else:
            print("FAILURE: Could not create department.")
            return False
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return False

if __name__ == "__main__":
    test_create_department()
