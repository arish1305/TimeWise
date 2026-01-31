import requests
import json

API_URL = "http://localhost:8000/admin/timeslots"

# 1. Create a Time Slot
print("Creating Time Slot...")
payload = {
    "day": "Monday",
    "start_time": "09:00:00",
    "end_time": "10:00:00",
    "is_break": False,
    "label": "Morning Lecture"
}

try:
    response = requests.post(API_URL, json=payload)
    if response.status_code == 200:
        print("Success:", response.json())
    else:
        print("Failed:", response.status_code, response.text)

    # 2. List Time Slots
    print("\nListing Time Slots...")
    response = requests.get(API_URL)
    if response.status_code == 200:
        slots = response.json()
        print(f"Found {len(slots)} slots.")
        for s in slots:
            print(s)
    else:
        print("Failed to list:", response.status_code)

except Exception as e:
    print("Error:", e)
