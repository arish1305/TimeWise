import logging

logger = logging.getLogger(__name__)

def _get_val(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def _get_manual_slots(subject) -> list:
    if not subject:
        return []
    resolved = _get_val(subject, "resolved_manual_timeslot_ids")
    if resolved is not None:
        return [int(s) for s in resolved if s is not None]
    slots = _get_val(subject, "manual_timeslot_ids") or []
    return [int(s) for s in slots if s is not None]
 
def is_combined_class(subject) -> bool:
    if not subject:
        return False
    manual_slots = _get_manual_slots(subject)
    return len(manual_slots) > 0
 
def is_shared_combined_class(
    subject,
    conflict_subject,
    slot_id,
    faculty_id,
    conflict_faculty_id,
    conflict_slot_id,
    is_different_section: bool = True,
    faculty_name: str = "Unknown",
    subject_code: str = "Unknown",
    subject_name: str = "Unknown",
    current_section: str = "Unknown",
    conflict_section: str = "Unknown",
    slot_names: list = None
) -> bool:
    # 1. Check if both are combined classes
    if not is_combined_class(subject) or not is_combined_class(conflict_subject):
        return False
 
    # 2. Same faculty
    if faculty_id is None or faculty_id != conflict_faculty_id:
        return False
 
    # 3. Same subject ID
    subject_id = _get_val(subject, "id")
    conflict_subject_id = _get_val(conflict_subject, "id")
    if subject_id is None or subject_id != conflict_subject_id:
        return False
 
    # 4. Same slot ID
    if slot_id != conflict_slot_id:
        return False
 
    # 5. Different participating sections
    if not is_different_section:
        return False
 
    # 6. Verify complete manual locked slot configurations are identical
    manual_slots = sorted(_get_manual_slots(subject))
    conflict_manual_slots = sorted(_get_manual_slots(conflict_subject))
    if manual_slots != conflict_manual_slots:
        return False
 
    # 7. Check current slot is in manual locked slots
    if slot_id not in manual_slots:
        return False
 
    # Log successful bypass
    if not slot_names:
        slot_names = [str(s) for s in manual_slots]
    slots_str = "\n".join(slot_names)
    
    log_msg = (
        f"Shared Combined Lecture Accepted\n\n"
        f"Faculty:\n{faculty_name}\n\n"
        f"Subject:\n{subject_name}\n\n"
        f"Sections:\n{current_section}\n{conflict_section}\n\n"
        f"Locked Slots:\n{slots_str}\n\n"
        f"Reason:\n\n"
        f"Identical faculty assignment\n\n"
        f"Identical subject\n\n"
        f"Identical locked schedule\n\n"
        f"Different sections\n\n"
        f"Faculty conflict ignored."
    )
    logger.info(log_msg)
    return True
