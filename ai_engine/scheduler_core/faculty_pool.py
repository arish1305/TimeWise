from typing import Any, Dict, List


def subject_faculty_ids(subject: Dict[str, Any]) -> List[Any]:
    """Return the ordered, de-duplicated faculty pool for a subject."""
    raw_ids = subject.get("faculty_ids")
    if raw_ids is None:
        raw_ids = [subject.get("faculty_id")]
    elif not isinstance(raw_ids, (list, tuple, set)):
        raw_ids = [raw_ids]

    faculty_ids = []
    seen = set()
    for faculty_id in raw_ids:
        if faculty_id is None:
            continue
        try:
            normalized = int(faculty_id)
        except (TypeError, ValueError):
            normalized = faculty_id
        if normalized in seen:
            continue
        seen.add(normalized)
        faculty_ids.append(normalized)

    legacy_faculty_id = subject.get("faculty_id")
    if legacy_faculty_id is not None:
        try:
            legacy_faculty_id = int(legacy_faculty_id)
        except (TypeError, ValueError):
            pass
        if legacy_faculty_id not in seen:
            faculty_ids.insert(0, legacy_faculty_id)

    return faculty_ids
