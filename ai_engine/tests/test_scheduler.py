import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_unoptimized_request():
    payload = {}
    response = client.post("/optimize", json=payload)
    assert response.status_code == 422

def test_health_check_non_existent():
    response = client.get("/non-existent")
    assert response.status_code == 404

def _build_test_payload():
    # 5 days, 5 slots per day
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    times = [
        ("09:00:00", "10:00:00"),
        ("10:00:00", "11:00:00"),
        ("11:00:00", "12:00:00"),
        ("12:00:00", "13:00:00"),
        ("13:00:00", "14:00:00")
    ]
    
    timeslots = []
    slot_id = 1
    for day in days:
        for t_start, t_end in times:
            timeslots.append({
                "id": slot_id,
                "day": day,
                "time": t_start,
                "end_time": t_end
            })
            slot_id += 1
            
    subjects = [
        {"id": 1, "name": "DBMS", "credits": 3, "faculty_id": 10, "is_elective": False},
        {"id": 2, "name": "OS", "credits": 3, "faculty_id": 11, "is_elective": False},
        {"id": 3, "name": "Networks", "credits": 4, "faculty_id": 10, "is_elective": False},
        {"id": 4, "name": "Compilers", "credits": 4, "faculty_id": 12, "is_elective": False}
    ]
    
    faculty = [
        {"id": 10, "name": "Dr. Alan Turing"},
        {"id": 11, "name": "Dr. Grace Hopper"},
        {"id": 12, "name": "Dr. Edsger Dijkstra"}
    ]
    
    return {
        "semester": 1,
        "subjects": subjects,
        "faculty": faculty,
        "timeslots": timeslots,
        "constraints": {
            "random_seed": 42,
            "prior_commitments": {},
            "prior_commitment_entries": {},
            "faculty_preferences": {
                "10": {"max_hours": 16},
                "11": {"max_hours": 16},
                "12": {"max_hours": 16}
            },
            "rules": {"spread_subjects": True}
        },
        "locked_slots": []
    }

def test_determinism():
    payload = _build_test_payload()
    
    # Generate schedule 1
    response1 = client.post("/optimize", json=payload)
    assert response1.status_code == 200
    res1 = response1.json()
    
    # Generate schedule 2
    response2 = client.post("/optimize", json=payload)
    assert response2.status_code == 200
    res2 = response2.json()
    
    # They must be exactly identical
    assert res1["schedule"] == res2["schedule"]

def test_section_diversity():
    payload1 = _build_test_payload()
    payload2 = _build_test_payload()
    
    # Set different seeds to represent different sections (e.g. CSE A vs CSE B)
    payload1["constraints"]["random_seed"] = 1001
    payload2["constraints"]["random_seed"] = 2002
    
    response1 = client.post("/optimize", json=payload1)
    res1 = response1.json()
    
    response2 = client.post("/optimize", json=payload2)
    res2 = response2.json()
    
    # Schedule outputs should be different
    assert res1["schedule"] != res2["schedule"]

def test_subject_spread():
    payload = _build_test_payload()
    response = client.post("/optimize", json=payload)
    assert response.status_code == 200
    schedule = response.json()["schedule"]
    
    # Group by subject
    subject_slots = {}
    timeslots_map = {t["id"]: t for t in payload["timeslots"]}
    for entry in schedule:
        sid = entry["subject_id"]
        tid = entry["timeslot_id"]
        slot = timeslots_map[tid]
        subject_slots.setdefault(sid, []).append(slot)
        
    for sid, slots in subject_slots.items():
        # Assert that the subject's sessions are spread out (no clustering in same day if slots permit)
        days_scheduled = [s["day"] for s in slots]
        # Since credits <= 4 and there are 5 days, they should be scheduled on unique days
        assert len(days_scheduled) == len(set(days_scheduled)), f"Subject {sid} scheduled multiple times on the same day: {days_scheduled}"

def test_period_diversity():
    payload = _build_test_payload()
    response = client.post("/optimize", json=payload)
    schedule = response.json()["schedule"]
    
    subject_slots = {}
    timeslots_map = {t["id"]: t for t in payload["timeslots"]}
    for entry in schedule:
        sid = entry["subject_id"]
        tid = entry["timeslot_id"]
        slot = timeslots_map[tid]
        subject_slots.setdefault(sid, []).append(slot)
        
    for sid, slots in subject_slots.items():
        # Os/DBMS etc. should not be scheduled at the exact same hour/period on all days
        times_scheduled = [s["time"] for s in slots]
        unique_times = set(times_scheduled)
        # We prefer maximum unique times; with credits = 3 or 4, they shouldn't all have the same time key
        assert len(unique_times) > 1, f"Subject {sid} scheduled at the same time: {times_scheduled}"

def test_faculty_comfort():
    payload = _build_test_payload()
    response = client.post("/optimize", json=payload)
    schedule = response.json()["schedule"]
    
    faculty_slots = {}
    timeslots_map = {t["id"]: t for t in payload["timeslots"]}
    for entry in schedule:
        fid = entry["faculty_id"]
        if fid:
            tid = entry["timeslot_id"]
            slot = timeslots_map[tid]
            faculty_slots.setdefault(fid, []).append(slot)
            
    for fid, slots in faculty_slots.items():
        # Group faculty slots by day
        slots_by_day = {}
        for s in slots:
            slots_by_day.setdefault(s["day"], []).append(s)
            
        for day, day_slots in slots_by_day.items():
            # Check for continuous teaching overloads (no more than 2 consecutive classes)
            # Sort slots by time
            day_slots.sort(key=lambda s: s["time"])
            for i in range(len(day_slots) - 2):
                s1, s2, s3 = day_slots[i], day_slots[i+1], day_slots[i+2]
                # Check if consecutive: s1.end_time == s2.time AND s2.end_time == s3.time
                is_consecutive = (s1["end_time"] == s2["time"]) and (s2["end_time"] == s3["time"])
                assert not is_consecutive, f"Faculty {fid} has consecutive teaching overload on {day}: {s1['time']}-{s2['time']}-{s3['time']}"
