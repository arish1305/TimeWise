import logging
from typing import Any, Dict, Iterable, List, Optional


logger = logging.getLogger("timewise.backend.timetable_diagnostics")


def _slot_label(slot_id: Any, timeslots_by_id: Dict[Any, Dict[str, Any]]) -> str:
    slot = timeslots_by_id.get(slot_id) or {}
    day = slot.get("day") or "Unknown"
    start = slot.get("time") or slot.get("start_time") or "Unknown"
    return f"{day}-{start} [slot_id={slot_id}]"


def _slot_list(slot_ids: Iterable[Any], timeslots_by_id: Dict[Any, Dict[str, Any]]) -> str:
    values = [_slot_label(slot_id, timeslots_by_id) for slot_id in (slot_ids or [])]
    return ", ".join(values) if values else "None"


def log_generation_payload_diagnostics(
    *,
    section: Dict[str, Any],
    department: Dict[str, Any],
    semester: Any,
    subjects: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]],
    locked_slots: List[Dict[str, Any]],
    constraints: Dict[str, Any],
    database_subject_ids: Iterable[Any],
    database_faculty_ids: Iterable[Any],
) -> None:
    """Log a read-only backend snapshot immediately before the AI-engine call."""
    timeslots_by_id = {slot.get("id"): slot for slot in timeslots}
    faculty_by_id = {row.get("id"): row for row in faculty}
    locked_by_subject: Dict[Any, List[Dict[str, Any]]] = {}
    for locked in locked_slots:
        locked_by_subject.setdefault(locked.get("subject_id"), []).append(locked)

    required_hours = sum(int(subject.get("weekly_hours") or 0) for subject in subjects)
    locked_hours = {
        subject_id: len(entries)
        for subject_id, entries in locked_by_subject.items()
    }
    net_required_hours = sum(
        max(0, int(subject.get("weekly_hours") or 0) - locked_hours.get(subject.get("id"), 0))
        for subject in subjects
    )
    teaching_slots = [slot for slot in timeslots if not slot.get("is_break", False)]
    locked_subject_count = sum(1 for subject in subjects if locked_by_subject.get(subject.get("id")))
    section_override_count = sum(1 for subject in subjects if subject.get("section_override_applied"))
    cbcs_count = sum(1 for subject in subjects if subject.get("is_cbcs_shared"))
    elective_count = sum(1 for subject in subjects if subject.get("is_elective"))
    multi_faculty_count = sum(1 for subject in subjects if len(subject.get("faculty_ids") or []) > 1)

    logger.info(
        "\n"
        "================ BACKEND TIMETABLE GENERATION SUMMARY ================\n"
        "Section: %s [section_id=%s]\n"
        "Department: %s [department_id=%s]\n"
        "Semester: %s\n"
        "Subjects: %s\n"
        "Faculty: %s\n"
        "Locked Subjects: %s\n"
        "Section Overrides: %s\n"
        "CBCS Subjects: %s\n"
        "Electives: %s\n"
        "Multi-Faculty Subjects: %s\n"
        "Teaching Slots: %s\n"
        "Required Weekly Hours: %s\n"
        "Net Required Hours: %s\n"
        "======================================================================",
        section.get("name"),
        section.get("id"),
        department.get("name"),
        department.get("id"),
        semester,
        len(subjects),
        len(faculty),
        locked_subject_count,
        section_override_count,
        cbcs_count,
        elective_count,
        multi_faculty_count,
        len(teaching_slots),
        required_hours,
        net_required_hours,
    )

    for subject in subjects:
        subject_id = subject.get("id")
        faculty_ids = list(subject.get("faculty_ids") or [])
        faculty_names = [
            (faculty_by_id.get(faculty_id) or {}).get("name") or "Unknown"
            for faculty_id in faculty_ids
        ]
        resolved_locked = [
            entry.get("timeslot_id")
            for entry in locked_by_subject.get(subject_id, [])
        ]
        logger.info(
            "\n"
            "---------------- SUBJECT DIAGNOSTIC ----------------\n"
            "Subject: %s\n"
            "Subject ID: %s\n"
            "Weekly Hours: %s\n"
            "Continuous Hours: %s\n"
            "Faculty IDs: %s\n"
            "Faculty Names: %s\n"
            "Assigned Faculty Count: %s\n"
            "Department Locked Slots: %s\n"
            "Section Override Slots: %s\n"
            "Final Resolved Locked Slots: %s\n"
            "Lock Source: %s\n"
            "Weekly Hours Remaining After Locked Slots: %s\n"
            "----------------------------------------------------",
            subject.get("name"),
            subject_id,
            subject.get("weekly_hours"),
            subject.get("continuous_hours", 1),
            faculty_ids or "None",
            faculty_names or "None",
            len(faculty_ids),
            _slot_list(subject.get("department_locked_slots") or [], timeslots_by_id),
            _slot_list(subject.get("section_override_slots") or [], timeslots_by_id),
            _slot_list(resolved_locked, timeslots_by_id),
            subject.get("lock_source") or "None",
            max(0, int(subject.get("weekly_hours") or 0) - len(resolved_locked)),
        )

    faculty_availability = constraints.get("faculty_availability", {}) or {}
    prior_commitments = constraints.get("prior_commitments", {}) or {}
    prior_entries = constraints.get("prior_commitment_entries", {}) or {}
    approved_commitments = constraints.get("approved_commitments", {}) or {}
    cbcs_subject_ids = {
        subject.get("id")
        for subject in subjects
        if subject.get("is_cbcs_shared")
    }

    def mapping_value(mapping: Dict[Any, Any], faculty_id: Any, key: Optional[str] = None) -> List[Any]:
        value = mapping.get(faculty_id)
        if value is None:
            value = mapping.get(str(faculty_id))
        if isinstance(value, dict):
            return list(value.get(key or "occupied_slots", []) or [])
        return list(value or [])

    for faculty_row in faculty:
        faculty_id = faculty_row.get("id")
        availability = (
            faculty_availability.get(faculty_id)
            or faculty_availability.get(str(faculty_id))
            or {}
        )
        unavailable = list(availability.get("unavailable_slots", []) or [])
        preferred = list(availability.get("preferred_slots", []) or [])
        existing = mapping_value(prior_commitments, faculty_id)
        approved = mapping_value(approved_commitments, faculty_id)
        entries = mapping_value(prior_entries, faculty_id)
        combined = [
            entry.get("timeslot_id")
            for entry in entries
            if isinstance(entry, dict) and entry.get("subject_id") in cbcs_subject_ids
        ]
        total_busy = set(unavailable) | set(existing) | set(approved)
        logger.info(
            "\n"
            "---------------- FACULTY DIAGNOSTIC ----------------\n"
            "Faculty: %s\n"
            "Faculty ID: %s\n"
            "Unavailable Slots: %s\n"
            "Preferred Slots: %s\n"
            "Existing Commitments: %s\n"
            "Existing Timetable Entries: %s\n"
            "Approved Commitments: %s\n"
            "Combined Class Commitments: %s\n"
            "Total Busy Slots: %s\n"
            "----------------------------------------------------",
            faculty_row.get("name"),
            faculty_id,
            _slot_list(unavailable, timeslots_by_id),
            _slot_list(preferred, timeslots_by_id),
            _slot_list(existing, timeslots_by_id),
            len(entries),
            _slot_list(approved, timeslots_by_id),
            _slot_list(combined, timeslots_by_id),
            len(total_busy),
        )

    payload_subject_ids = {subject.get("id") for subject in subjects}
    payload_faculty_ids = {row.get("id") for row in faculty}
    subject_faculty_ids = {
        faculty_id
        for subject in subjects
        for faculty_id in (subject.get("faculty_ids") or [])
    }
    database_subject_ids = set(database_subject_ids)
    database_faculty_ids = set(database_faculty_ids)
    verification_errors = []
    if payload_subject_ids != database_subject_ids:
        verification_errors.append(
            f"subject IDs differ: payload={sorted(payload_subject_ids)}, database={sorted(database_subject_ids)}"
        )
    if payload_faculty_ids != database_faculty_ids:
        verification_errors.append(
            f"faculty IDs differ: payload={sorted(payload_faculty_ids)}, database={sorted(database_faculty_ids)}"
        )
    missing_faculty_rows = subject_faculty_ids - payload_faculty_ids
    if missing_faculty_rows:
        verification_errors.append(
            f"subject faculty IDs missing from faculty payload: {sorted(missing_faculty_rows)}"
        )

    manual_locks = [row for row in locked_slots if row.get("lock_source") == "Manual Lock"]
    section_overrides = [row for row in locked_slots if row.get("lock_source") == "Section Override"]
    logger.info(
        "\n"
        "================ AI PAYLOAD VERIFICATION ================\n"
        "Payload Subject Count: %s\n"
        "Payload Faculty Count: %s\n"
        "Timeslot Count: %s\n"
        "Teaching Slot Count: %s\n"
        "Faculty IDs Per Subject: %s\n"
        "Locked Slots Per Subject: %s\n"
        "Section Overrides Applied: %s\n"
        "Manual Locks Applied: %s\n"
        "Database Match: %s\n"
        "=========================================================",
        len(subjects),
        len(faculty),
        len(timeslots),
        len(teaching_slots),
        {
            subject.get("id"): list(subject.get("faculty_ids") or [])
            for subject in subjects
        },
        {
            subject_id: [entry.get("timeslot_id") for entry in entries]
            for subject_id, entries in locked_by_subject.items()
        },
        len(section_overrides),
        len(manual_locks),
        "NO - " + "; ".join(verification_errors) if verification_errors else "YES",
    )

