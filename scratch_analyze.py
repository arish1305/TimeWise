import sys
import os

# Define the data matching scratch_debug.py
days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
times = ["09:00:00", "10:00:00", "11:00:00", "12:00:00", "13:00:00"]
timeslots = []
slot_id = 1
for day in days:
    for t in times:
        timeslots.append({"id": slot_id, "day": day, "time": t})
        slot_id += 1

subjects = [
    {"id": 64, "name": "Project Work", "credits": 4, "continuous_hours": 4, "subject_type": "THEORY"},
    {"id": 63, "name": "Computer Vision Lab", "credits": 3, "continuous_hours": 2, "subject_type": "THEORY"},
    {"id": 58, "name": "Software Project Management", "credits": 5, "continuous_hours": 1, "subject_type": "THEORY"},
    {"id": 60, "name": "Cyber Digital Twin", "credits": 5, "continuous_hours": 1, "subject_type": "THEORY"},
    {"id": 59, "name": "Computer Vision", "credits": 5, "continuous_hours": 1, "subject_type": "THEORY"},
    {"id": 62, "name": "Hardware Interfaces", "credits": 3, "continuous_hours": 1, "subject_type": "THEORY"},
    {"id": 61, "name": "Malware Analysis", "credits": 3, "continuous_hours": 1, "subject_type": "THEORY"},
]

locked_slots = [
    {"timeslot_id": 1, "subject_id": 62},
    {"timeslot_id": 2, "subject_id": 62},
    {"timeslot_id": 3, "subject_id": 62},
    {"timeslot_id": 6, "subject_id": 61},
    {"timeslot_id": 7, "subject_id": 61},
    {"timeslot_id": 8, "subject_id": 61},
]

# Track domain of each variable: key is (subject_id, timeslot_id), value is set of possible values {0, 1}
domains = {}
for s in subjects:
    for t in timeslots:
        domains[(s["id"], t["id"])] = {0, 1}

# Trace constraints applied to each variable
constraints_applied = {}
for s in subjects:
    for t in timeslots:
        constraints_applied[(s["id"], t["id"])] = []

def add_fixed_constraint(sid, tid, val, reason):
    key = (sid, tid)
    constraints_applied[key].append(f"Fixed to {val} because: {reason}")
    domains[key] = domains[key].intersection({val})
    if not domains[key]:
        print(f"!!! DIRECT CONTRADICTION DETECTED on variable x_{sid}_{tid} !!!")
        print(f"Constraints applied:")
        for c in constraints_applied[key]:
            print(f"  - {c}")
        sys.exit(1)

# 1. Enforce locked slots
locked_slots_by_tid = {}
for locked in locked_slots:
    tid = locked["timeslot_id"]
    sid = locked["subject_id"]
    locked_slots_by_tid.setdefault(tid, []).append(sid)

for tid, sids in locked_slots_by_tid.items():
    for sid in sids:
        add_fixed_constraint(sid, tid, 1, f"Locked Slot Constraint: Subject {sid} is locked at timeslot {tid}")
    for s in subjects:
        if s["id"] not in sids:
            add_fixed_constraint(s["id"], tid, 0, f"Locked Slot Exclusion: Timeslot {tid} is locked for subject(s) {sids}")

# 2. Break Slots (none in scratch_debug, but let's keep logic)
for t in timeslots:
    if t.get("is_break", False):
        for s in subjects:
            add_fixed_constraint(s["id"], t["id"], 0, f"Break Slot Constraint: Teaching not allowed in slot {t['id']}")

# Identify non-locked teaching slots
non_locked_teaching_slot_ids = [t["id"] for t in timeslots if t["id"] not in locked_slots_by_tid and not t.get("is_break", False)]
print(f"Non-locked teaching timeslots ({len(non_locked_teaching_slot_ids)}): {non_locked_teaching_slot_ids}")

# 3. Weekly Hours
subject_sessions = {}
locked_subject_hours = {}
for locked in locked_slots:
    sid = locked["subject_id"]
    locked_subject_hours[sid] = locked_subject_hours.get(sid, 0) + 1

for s in subjects:
    sid = s["id"]
    weekly_hours = s["credits"] # computed as credits in scratch_debug
    locked_h = locked_subject_hours.get(sid, 0)
    needed = max(0, weekly_hours - locked_h)
    subject_sessions[sid] = needed
    print(f"Subject {sid} ({s['name']}): weekly_hours={weekly_hours}, locked_hours={locked_h}, sessions_needed={needed}")

# 4. Continuous block exclusions (e.g. for Lab subjects)
# Group slots by day
slots_by_day = {}
for t in timeslots:
    day = t["day"].lower()
    slots_by_day.setdefault(day, []).append(t)

for s in subjects:
    sid = s["id"]
    continuous_hours = s.get("continuous_hours", 1)
    if continuous_hours > 1:
        needed = subject_sessions[sid]
        blocks_needed = 1 if needed >= continuous_hours else 0
        remainder = needed - continuous_hours if needed >= continuous_hours else needed
        
        # Calculate covering block starts
        if blocks_needed > 0:
            block_starts_by_slot = {tid: [] for tid in non_locked_teaching_slot_ids}
            day_index = 0
            all_block_starts = []
            for day, day_slots in slots_by_day.items():
                k = continuous_hours
                if len(day_slots) >= k:
                    for j in range(len(day_slots) - k + 1):
                        block_slot_ids = [day_slots[j + offset]["id"] for offset in range(k)]
                        if any(slot_id not in non_locked_teaching_slot_ids for slot_id in block_slot_ids):
                            continue
                        # Valid candidate block start
                        block_name = f"b_{sid}_d{day_index}_j{j}"
                        all_block_starts.append(block_name)
                        for slot_id in block_slot_ids:
                            block_starts_by_slot[slot_id].append(block_name)
                day_index += 1
            
            # Constraint: x[sid][slot] <= sum(covering_starts) + remainder_var
            # If no starts cover it and remainder is not allowed/zero: x[sid][slot] == 0
            for slot_id in non_locked_teaching_slot_ids:
                covering = block_starts_by_slot.get(slot_id, [])
                if not covering and remainder == 0:
                    add_fixed_constraint(sid, slot_id, 0, f"Continuous Block Exclusion: No valid block of size {continuous_hours} can cover slot {slot_id} and remainder is 0")

print("\n--- Domain status after basic bounds propagation ---")
for key, domain in sorted(domains.items()):
    if len(domain) == 1:
        val = list(domain)[0]
        print(f"Variable x_{key[0]}_{key[1]} is forced to {val}")

# Check Section Non-Overlap and Weekly Hours
# For each subject, the sum of variables in non-locked slots must be exactly sessions_needed
# Let's count how many variables are STILL allowed to be 1 for each subject
print("\n--- Weekly Hours Feasibility Check ---")
total_min_needed = 0
total_max_allowed = 0
for s in subjects:
    sid = s["id"]
    needed = subject_sessions[sid]
    allowed_slots = [tid for tid in non_locked_teaching_slot_ids if 1 in domains[(sid, tid)]]
    print(f"Subject {sid} ({s['name']}): needs {needed} non-locked slots. Active candidate slots: {allowed_slots} (count={len(allowed_slots)})")
    if len(allowed_slots) < needed:
        print(f"!!! INFEASIBILITY DETECTED: Subject {sid} needs {needed} slots but only has {len(allowed_slots)} candidate slots available!")
        print(f"Constraints preventing allocation:")
        for tid in non_locked_teaching_slot_ids:
            if 1 not in domains[(sid, tid)]:
                print(f"  Timeslot {tid}: {constraints_applied[(sid, tid)]}")
        sys.exit(1)

# Pigeonhole principle check:
# Total sessions needed for all active subjects in non_locked_teaching_slot_ids
active_subjects = [s for s in subjects if subject_sessions[s["id"]] > 0]
sum_needed = sum(subject_sessions[s["id"]] for s in active_subjects)
num_slots = len(non_locked_teaching_slot_ids)
print(f"\nTotal sessions needed across all subjects in non-locked slots: {sum_needed}")
print(f"Total non-locked teaching slots available: {num_slots}")
if sum_needed > num_slots:
    print(f"!!! INFEASIBILITY DETECTED (Section Overlap & Capacity Conflict) !!!")
    print(f"Pigeonhole Principle Violated: The sum of weekly hours required ({sum_needed}) exceeds the number of available timeslots ({num_slots}).")
    print(f"Under Section Non-Overlap, at most 1 subject can be scheduled in any timeslot.")
    print(f"Therefore, total scheduled slots cannot exceed {num_slots}, but weekly hours demand is {sum_needed}.")
    sys.exit(1)

print("\nFeasible under basic checks.")
