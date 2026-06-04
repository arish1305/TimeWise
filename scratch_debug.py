import sys
import os

ai_path = os.path.abspath("ai_engine")
if ai_path not in sys.path:
    sys.path.append(ai_path)

from cp_sat_solver import CPSatSolver
from ortools.sat.python import cp_model
import logging

logging.basicConfig(level=logging.INFO)

# 25 timeslots (5 days x 5 slots per day)
days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
times = ["09:00:00", "10:00:00", "11:00:00", "12:00:00", "13:00:00"]
timeslots = []
slot_id = 1
for day in days:
    for t in times:
        timeslots.append({"id": slot_id, "day": day, "time": t})
        slot_id += 1

# Subjects matching the user's data
subjects = [
    {"id": 64, "name": "Project Work", "credits": 4, "continuous_hours": 4, "subject_type": "THEORY", "faculty_id": None},
    {"id": 63, "name": "Computer Vision Lab", "credits": 3, "continuous_hours": 2, "subject_type": "THEORY", "faculty_id": None},
    {"id": 58, "name": "Software Project Management", "credits": 5, "continuous_hours": 1, "subject_type": "THEORY", "faculty_id": None},
    {"id": 60, "name": "Cyber Digital Twin", "credits": 5, "continuous_hours": 1, "subject_type": "THEORY", "faculty_id": None},
    {"id": 59, "name": "Computer Vision", "credits": 5, "continuous_hours": 1, "subject_type": "THEORY", "faculty_id": None},
    {"id": 62, "name": "Hardware Interfaces", "credits": 3, "continuous_hours": 1, "subject_type": "THEORY", "faculty_id": None},
    {"id": 61, "name": "Malware Analysis", "credits": 3, "continuous_hours": 1, "subject_type": "THEORY", "faculty_id": None},
]

faculty = []

# 6 locked slots (3 for Hardware Interfaces, 3 for Malware Analysis)
locked_slots = [
    {"timeslot_id": 1, "subject_id": 62},
    {"timeslot_id": 2, "subject_id": 62},
    {"timeslot_id": 3, "subject_id": 62},
    {"timeslot_id": 6, "subject_id": 61},
    {"timeslot_id": 7, "subject_id": 61},
    {"timeslot_id": 8, "subject_id": 61},
]

constraints = {
    "rules": {
        "spread_subjects": True
    },
    "random_seed": 12345
}

solver = CPSatSolver(subjects, faculty, timeslots, constraints, locked_slots)

# We temporarily modify solve_single or print output manually to capture log search progress
print("Running solver...")
res = solver.solve_single(12345)
if res:
    print("SUCCESS: Schedule generated!")
    for item in sorted(res["schedule"], key=lambda k: k["timeslot_id"]):
        print(f"Slot {item['timeslot_id']}: Subject {item['subject_id']}")
else:
    print("FAILED: Model is infeasible.")
