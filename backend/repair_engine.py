import logging
from sqlalchemy.orm import Session
from routers.timetable import validate_timetable_internal, _query_department_timeslots
from human_score_engine import score_timetable
import models

logger = logging.getLogger(__name__)

def repair_timetable(timetable: models.Timetable, db: Session, rules: dict = None, threshold: float = 80.0, max_iterations: int = 50) -> dict:
    """
    Tries to repair/optimize a timetable to meet a target human score threshold.
    Applies swaps and moves of non-locked entries and checks if the human score improves,
    while guaranteeing that hard validation constraints are NEVER violated.
    """
    if rules is None:
        rules = {}

    # Calculate initial score
    score_res = score_timetable(timetable, db, rules)
    current_score = score_res["total_score"]
    
    logger.info(f"Starting repair for Timetable ID {timetable.id}. Initial Human Score: {current_score} (target: {threshold})")
    
    if current_score >= threshold:
        logger.info("Timetable already meets or exceeds target threshold. No repair needed.")
        return {
            "success": True,
            "initial_score": current_score,
            "final_score": current_score,
            "iterations": 0,
            "issues": score_res["issues"]
        }

    # Fetch all department timeslots (excluding breaks)
    dept_id = None
    if timetable.section and timetable.section.academic_year:
        dept_id = timetable.section.academic_year.department_id
    
    all_slots = []
    if dept_id:
        all_slots = _query_department_timeslots(db, dept_id, include_breaks=False).all()
    slot_ids = [ts.id for ts in all_slots]
    slots_map = {ts.id: ts for ts in all_slots}

    iteration = 0
    improved = True

    while iteration < max_iterations and current_score < threshold and improved:
        improved = False
        iteration += 1
        
        # Get current issues and candidates
        score_res = score_timetable(timetable, db, rules)
        current_score = score_res["total_score"]
        candidates = score_res["repair_candidates"]
        
        if not candidates:
            # No candidates to repair but score is still below threshold (e.g. general balance issue)
            # We can use all non-locked entries as candidates
            candidates = [
                {
                    "entry_id": e.id,
                    "timeslot_id": e.timeslot_id,
                    "issue_type": "general"
                }
                for e in timetable.entries
                if not e.is_locked
            ]

        for cand in candidates:
            entry_id = cand["entry_id"]
            # Fetch fresh entry from DB
            entry = db.query(models.TimetableEntry).filter(models.TimetableEntry.id == entry_id).first()
            if not entry or entry.is_locked:
                continue

            orig_slot = entry.timeslot
            orig_slot_id = entry.timeslot_id
            
            # --- Try Move Strategy (Move to an empty timeslot) ---
            # Find which slots are completely empty for this section in the timetable
            occupied_slots = {e.timeslot_id for e in timetable.entries}
            empty_slots = [sid for sid in slot_ids if sid not in occupied_slots]
            
            for target_slot_id in empty_slots:
                # Apply move temporarily via relationship
                target_slot = slots_map.get(target_slot_id)
                if not target_slot:
                    continue
                entry.timeslot = target_slot
                db.flush()
                
                # Check hard constraints
                val_res = validate_timetable_internal(timetable, db, rules=rules)
                if val_res["status"] == "PASS":
                    # Evaluate new score
                    new_score_res = score_timetable(timetable, db, rules)
                    new_score = new_score_res["total_score"]
                    if new_score > current_score:
                        logger.info(f"[Repair Iter {iteration}] Moved entry {entry_id} from slot {orig_slot_id} to empty slot {target_slot_id}. Score: {current_score} -> {new_score}")
                        current_score = new_score
                        improved = True
                        break
                
                # Revert if it failed hard constraints or didn't improve
                entry.timeslot = orig_slot
                db.flush()

            if improved:
                break  # Go to next iteration

            # --- Try Swap Strategy (Swap slots with another non-locked entry) ---
            other_entries = [
                e for e in timetable.entries
                if e.id != entry_id and not e.is_locked
            ]
            
            # Try to swap with someone
            for peer in other_entries:
                peer_orig_slot = peer.timeslot
                peer_orig_slot_id = peer.timeslot_id
                
                # Apply swap temporarily
                entry.timeslot = peer_orig_slot
                peer.timeslot = orig_slot
                db.flush()
                
                # Check hard constraints
                val_res = validate_timetable_internal(timetable, db, rules=rules)
                if val_res["status"] == "PASS":
                    # Evaluate new score
                    new_score_res = score_timetable(timetable, db, rules)
                    new_score = new_score_res["total_score"]
                    if new_score > current_score:
                        logger.info(f"[Repair Iter {iteration}] Swapped entry {entry_id} (slot {orig_slot_id}) with peer {peer.id} (slot {peer_orig_slot_id}). Score: {current_score} -> {new_score}")
                        current_score = new_score
                        improved = True
                        break
                
                # Revert if it failed hard constraints or didn't improve
                entry.timeslot = orig_slot
                peer.timeslot = peer_orig_slot
                db.flush()
                
            if improved:
                break  # Go to next iteration

    # Final evaluation
    final_score_res = score_timetable(timetable, db, rules)
    final_score = final_score_res["total_score"]
    logger.info(f"Finished repair for Timetable ID {timetable.id}. Final Score: {final_score} after {iteration} iterations.")
    
    return {
        "success": final_score >= threshold,
        "initial_score": round(score_res["total_score"], 2) if iteration > 0 else current_score,
        "final_score": round(final_score, 2),
        "iterations": iteration,
        "issues": final_score_res["issues"]
    }
