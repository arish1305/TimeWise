import logging

logger = logging.getLogger(__name__)

def _get_val(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def _is_cbcs(subject) -> bool:
    if not subject:
        return False
    allowed_depts = _get_val(subject, "allowed_department_ids")
    if allowed_depts:
        return True
    if _get_val(subject, "is_cbcs_shared") or _get_val(subject, "is_cbcs"):
        return True
    return False

def _is_elective(subject) -> bool:
    if not subject:
        return False
    return bool(_get_val(subject, "is_elective"))

def _get_manual_slots(subject) -> list:
    if not subject:
        return []
    slots = _get_val(subject, "manual_timeslot_ids") or []
    return [int(s) for s in slots if s is not None]

def is_combined_class(subject) -> bool:
    if not subject:
        return False
    is_cbcs_val = _is_cbcs(subject)
    is_elective_val = _is_elective(subject)
    manual_slots = _get_manual_slots(subject)
    return (is_cbcs_val or is_elective_val) and len(manual_slots) > 0

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
    conflict_section: str = "Unknown"
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
    slots_str = "\n".join(str(s) for s in manual_slots)
    log_msg = (
        f"Combined Shared Lecture Accepted\n\n"
        f"Faculty:\n{faculty_name}\n\n"
        f"Subject:\n{subject_code}\n\n"
        f"Subject Name:\n{subject_name}\n\n"
        f"Sections:\n{current_section}\n{conflict_section}\n\n"
        f"Locked Slots:\n{slots_str}\n\n"
        f"Current Slot:\n{slot_id}\n\n"
        f"Decision:\nFaculty conflict ignored\n\n"
        f"Reason:\nCombined CBCS/Elective locked lecture\n\n"
        f"Decision Source:\nis_shared_combined_class()"
    )
    logger.info(log_msg)
    return True
