from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from models import TimeSlot
import datetime

def fix_timeslots():
    db = SessionLocal()
    
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    # Standard slots (start, end, is_break, label)
    slot_template = [
        ("09:00:00", "10:00:00", False, "9.00-10.00am"),
        ("10:00:00", "11:00:00", False, "10.00-11.00am"),
        ("11:00:00", "11:15:00", True, "Break"),
        ("11:15:00", "12:15:00", True, "Lunch"), # Wait, logic for Lunch usually indicates a bigger break? Reference image shows Break vertical.
        # Image: 11.00-11.15 Break. 11.15-12.15 (Lunch? No, check image)
        # Image: 11.00-11.15 Break. 
        # Image: 11.15-12.15 is blank? Or a lecture? 
        # Column 4: 11.15-12.15. Column 5: 12.15-01.15pm. Column 6: 01.15-02.15. Column 7: 02.15-03.15.
        # Vertical text says "BREAK" between 11.00-11.15. 
        # Vertical text says "LUNCH" between 11.15-12.15. 
        # Ah! So 11.15-12.15 is LUNCH.
        
        # Let's align with image:
        ("11:15:00", "12:15:00", True, "Lunch"),
        ("12:15:00", "13:15:00", False, "12.15-1.15pm"),
        ("13:15:00", "14:15:00", False, "1.15-2.15pm"),
        ("14:15:00", "15:15:00", False, "2.15-3.15pm"),
    ]
    
    # Image also has "Monday SCSB1662" at 9.00-10.00.
    
    count_added = 0
    for day in days:
        for s in slot_template:
            start_t = datetime.datetime.strptime(s[0], "%H:%M:%S").time()
            end_t = datetime.datetime.strptime(s[1], "%H:%M:%S").time()
            
            exists = db.query(TimeSlot).filter(
                TimeSlot.day == day,
                TimeSlot.start_time == start_t
            ).first()
            
            if not exists:
                ts = TimeSlot(
                    day=day,
                    start_time=start_t,
                    end_time=end_t,
                    is_break=s[2],
                    label=s[3]
                )
                db.add(ts)
                count_added += 1
    
    db.commit()
    print(f"Added {count_added} missing time slots.")
    db.close()

if __name__ == "__main__":
    fix_timeslots()
