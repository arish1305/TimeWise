import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

LEARNING_DATA_PATH = os.path.join(os.path.dirname(__file__), "learning_data.jsonl")

def log_learning_event(event_type: str, timetable_id: int, payload: dict):
    """
    Logs details of generated, edited (moved, swapped), or approved timetables 
    for future analysis of slot preferences, subject patterns, and faculty habits.
    """
    event_record = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type, # e.g. "generated", "manual_edit", "accepted"
        "timetable_id": timetable_id,
        "payload": payload
    }
    
    try:
        with open(LEARNING_DATA_PATH, "a") as f:
            f.write(json.dumps(event_record) + "\n")
        logger.info(f"Learning Layer: Logged '{event_type}' event for Timetable ID {timetable_id}.")
    except Exception as e:
        logger.error(f"Learning Layer: Failed to log event: {e}")

def load_learning_data(limit: int = 100) -> list:
    """
    Loads the last `limit` logged events from the learning data file.
    """
    if not os.path.exists(LEARNING_DATA_PATH):
        return []
    events = []
    try:
        with open(LEARNING_DATA_PATH, "r") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line.strip()))
        return events[-limit:]
    except Exception as e:
        logger.error(f"Learning Layer: Failed to load events: {e}")
        return []

