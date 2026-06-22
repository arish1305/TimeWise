import logging
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .faculty_pool import subject_faculty_ids


logger = logging.getLogger("timewise.ai_engine.deep_diagnostics")


def _normalize_id(value: Any) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _slot_values(mapping: Any, faculty_id: Any, key: str) -> Set[Any]:
    normalized_faculty_id = _normalize_id(faculty_id)
    if isinstance(mapping, dict):
        value = mapping.get(normalized_faculty_id)
        if value is None:
            value = mapping.get(str(normalized_faculty_id))
        if isinstance(value, dict):
            value = value.get(key, []) or value.get("occupied_slots", []) or []
        return {_normalize_id(slot_id) for slot_id in (value or [])}

    values = set()
    if isinstance(mapping, list):
        for item in mapping:
            if not isinstance(item, dict):
                continue
            if _normalize_id(item.get("faculty_id")) != normalized_faculty_id:
                continue
            if item.get("timeslot_id") is not None:
                values.add(_normalize_id(item.get("timeslot_id")))
            else:
                values.update(
                    _normalize_id(slot_id)
                    for slot_id in (item.get(key, []) or item.get("occupied_slots", []) or [])
                )
    return values


class DeepDiagnosticAnalyzer:
    """Read-only mirror of hard-constraint filtering for human diagnostics."""

    def __init__(
        self,
        subjects: List[Dict[str, Any]],
        faculty: List[Dict[str, Any]],
        timeslots: List[Dict[str, Any]],
        constraints: Optional[Dict[str, Any]] = None,
        locked_slots: Optional[List[Dict[str, Any]]] = None,
    ):
        self.subjects = subjects
        self.faculty = faculty
        self.timeslots = timeslots
        self.constraints = constraints or {}
        self.locked_slots = locked_slots or []
        self.subjects_by_id = {subject.get("id"): subject for subject in subjects}
        self.faculty_by_id = {
            _normalize_id(row.get("id")): row
            for row in faculty
        }
        self.timeslots_by_id = {
            _normalize_id(slot.get("id")): slot
            for slot in timeslots
        }
        self.all_slot_ids = set(self.timeslots_by_id)
        self.break_slot_ids = {
            slot_id
            for slot_id, slot in self.timeslots_by_id.items()
            if slot.get("is_break", False)
        }
        self.teaching_slot_ids = self.all_slot_ids - self.break_slot_ids
        self.locked_by_slot: Dict[Any, List[Dict[str, Any]]] = {}
        self.locked_by_subject: Dict[Any, List[Dict[str, Any]]] = {}
        for locked in self.locked_slots:
            slot_id = _normalize_id(locked.get("timeslot_id"))
            subject_id = locked.get("subject_id")
            self.locked_by_slot.setdefault(slot_id, []).append(locked)
            self.locked_by_subject.setdefault(subject_id, []).append(locked)
        self.analysis = self._analyze()

    def _slot_label(self, slot_id: Any) -> str:
        slot = self.timeslots_by_id.get(slot_id) or {}
        return (
            f"{slot.get('day') or 'Unknown'}-"
            f"{slot.get('time') or slot.get('start_time') or 'Unknown'} "
            f"[slot_id={slot_id}]"
        )

    def _faculty_unavailable(self, faculty_id: Any) -> Set[Any]:
        return _slot_values(
            self.constraints.get("faculty_availability", {}) or {},
            faculty_id,
            "unavailable_slots",
        )

    def _faculty_preferred(self, faculty_id: Any) -> Set[Any]:
        return _slot_values(
            self.constraints.get("faculty_availability", {}) or {},
            faculty_id,
            "preferred_slots",
        )

    def _faculty_prior(self, faculty_id: Any) -> Set[Any]:
        return _slot_values(
            self.constraints.get("prior_commitments", {}) or {},
            faculty_id,
            "occupied_slots",
        )

    def _faculty_approved(self, faculty_id: Any) -> Set[Any]:
        return _slot_values(
            self.constraints.get("approved_commitments", {}) or {},
            faculty_id,
            "occupied_slots",
        )

    def _prior_entries(self, faculty_id: Any, slot_id: Any) -> List[Dict[str, Any]]:
        mapping = self.constraints.get("prior_commitment_entries", {}) or {}
        entries = mapping.get(_normalize_id(faculty_id))
        if entries is None:
            entries = mapping.get(str(_normalize_id(faculty_id)))
        return [
            entry
            for entry in (entries or [])
            if _normalize_id(entry.get("timeslot_id")) == _normalize_id(slot_id)
        ]

    def _is_shared_commitment(
        self,
        subject: Dict[str, Any],
        faculty_id: Any,
        slot_id: Any,
    ) -> bool:
        if not subject.get("is_cbcs_shared"):
            return False
        for entry in self._prior_entries(faculty_id, slot_id):
            if entry.get("subject_id") == subject.get("id"):
                return True
        return False

    def _commitment_conflicts(
        self,
        subject: Dict[str, Any],
        faculty_id: Any,
    ) -> Set[Any]:
        conflicts = set()
        for slot_id in self._faculty_prior(faculty_id) | self._faculty_approved(faculty_id):
            if not self._is_shared_commitment(subject, faculty_id, slot_id):
                conflicts.add(slot_id)
        return conflicts

    def _locked_conflicts(self, subject: Dict[str, Any]) -> Set[Any]:
        # The production model removes every locked timeslot from the remaining-hours
        # decision pool. Subjects already locked there are counted separately.
        return set(self.locked_by_slot)

    def _slots_by_day(self) -> Dict[str, List[Dict[str, Any]]]:
        rows: Dict[str, List[Dict[str, Any]]] = {}
        for slot in self.timeslots:
            rows.setdefault(str(slot.get("day") or "Unknown"), []).append(slot)
        for slots in rows.values():
            slots.sort(key=lambda row: row.get("time") or row.get("start_time") or "")
        return rows

    def _block_analysis(
        self,
        subject: Dict[str, Any],
        allowed_slots: Set[Any],
    ) -> Tuple[List[List[Any]], List[Dict[str, Any]]]:
        continuous_hours = _safe_int(subject.get("continuous_hours", 1) or 1, 1)
        if continuous_hours <= 1:
            return [], []

        valid_blocks: List[List[Any]] = []
        rejected_blocks: List[Dict[str, Any]] = []
        faculty_ids = subject_faculty_ids(subject)
        locked_conflicts = self._locked_conflicts(subject)
        unavailable_by_faculty = {
            faculty_id: self._faculty_unavailable(faculty_id)
            for faculty_id in faculty_ids
        }
        commitments_by_faculty = {
            faculty_id: self._commitment_conflicts(subject, faculty_id)
            for faculty_id in faculty_ids
        }

        for day, day_slots in self._slots_by_day().items():
            for start in range(max(0, len(day_slots) - continuous_hours + 1)):
                block = [
                    _normalize_id(day_slots[start + offset].get("id"))
                    for offset in range(continuous_hours)
                ]
                reasons = []
                if any(slot_id in self.break_slot_ids for slot_id in block):
                    reasons.append("Break")
                if any(slot_id in locked_conflicts for slot_id in block):
                    reasons.append("Locked Slot / Section Clash")
                unavailable_faculty = [
                    faculty_id
                    for faculty_id, slots in unavailable_by_faculty.items()
                    if any(slot_id in slots for slot_id in block)
                ]
                if unavailable_faculty:
                    reasons.append(f"Faculty Unavailable {unavailable_faculty}")
                busy_faculty = [
                    faculty_id
                    for faculty_id, slots in commitments_by_faculty.items()
                    if any(slot_id in slots for slot_id in block)
                ]
                if busy_faculty:
                    reasons.append(f"Faculty Commitments {busy_faculty}")
                if any(slot_id not in allowed_slots for slot_id in block) and not reasons:
                    reasons.append("Filtered by another hard constraint")

                if reasons:
                    rejected_blocks.append({
                        "day": day,
                        "slots": block,
                        "reason": "; ".join(reasons),
                    })
                else:
                    valid_blocks.append(block)
        return valid_blocks, rejected_blocks

    def _analyze_subject(self, subject: Dict[str, Any]) -> Dict[str, Any]:
        subject_id = subject.get("id")
        faculty_ids = subject_faculty_ids(subject)
        weekly_hours = _safe_int(subject.get("weekly_hours") or subject.get("credits") or 0)
        locked_hours = len(self.locked_by_subject.get(subject_id, []))
        remaining_hours = max(0, weekly_hours - locked_hours)

        current = set(self.all_slot_ids)
        stages = [{"constraint": "Initial Slots", "remaining": len(current), "removed": []}]

        removed = current & self.break_slot_ids
        current -= removed
        stages.append({
            "constraint": "Break Removal",
            "remaining": len(current),
            "removed": sorted(removed),
        })

        locked_conflicts = self._locked_conflicts(subject)
        removed = current & locked_conflicts
        current -= removed
        stages.append({
            "constraint": "Locked Slot Rules",
            "remaining": len(current),
            "removed": sorted(removed),
        })

        unavailable = set()
        for faculty_id in faculty_ids:
            unavailable.update(self._faculty_unavailable(faculty_id))
        removed = current & unavailable
        current -= removed
        stages.append({
            "constraint": "Faculty Unavailability",
            "remaining": len(current),
            "removed": sorted(removed),
        })

        commitments = set()
        for faculty_id in faculty_ids:
            commitments.update(self._commitment_conflicts(subject, faculty_id))
        removed = current & commitments
        current -= removed
        stages.append({
            "constraint": "Faculty Commitments",
            "remaining": len(current),
            "removed": sorted(removed),
        })

        stages.append({
            "constraint": "Section Clashes",
            "remaining": len(current),
            "removed": [],
            "note": "Dynamic section non-overlap is enforced pairwise by CP-SAT.",
        })

        valid_blocks, rejected_blocks = self._block_analysis(subject, current)
        continuous_hours = _safe_int(subject.get("continuous_hours", 1) or 1, 1)
        requires_block = continuous_hours > 1 and remaining_hours >= continuous_hours
        blocking_reasons = []
        if remaining_hours > 0 and not current:
            blocking_reasons.append(stages[-2]["constraint"])
        if requires_block and not valid_blocks:
            blocking_reasons.append("Continuous Block Rules")
        stages.append({
            "constraint": "Continuous Block Rules",
            "remaining": len(current),
            "candidate_blocks": len(valid_blocks),
        })
        first_zero_stage = next(
            (
                stage["constraint"]
                for stage in stages[1:]
                if stage["remaining"] == 0
            ),
            None,
        )
        if remaining_hours > 0 and first_zero_stage:
            blocking_reasons = [first_zero_stage]
            if requires_block and not valid_blocks and first_zero_stage != "Continuous Block Rules":
                blocking_reasons.append("Continuous Block Rules")

        return {
            "subject_id": subject_id,
            "name": subject.get("name"),
            "weekly_hours": weekly_hours,
            "continuous_hours": continuous_hours,
            "faculty_ids": faculty_ids,
            "locked_slots": [
                _normalize_id(entry.get("timeslot_id"))
                for entry in self.locked_by_subject.get(subject_id, [])
            ],
            "remaining_hours": remaining_hours,
            "stages": stages,
            "final_candidate_slots": sorted(current),
            "valid_blocks": valid_blocks,
            "rejected_blocks": rejected_blocks,
            "blocking_reasons": blocking_reasons,
        }

    def _locked_slot_checks(self) -> List[Dict[str, Any]]:
        checks = []
        for locked in self.locked_slots:
            subject = self.subjects_by_id.get(locked.get("subject_id")) or {}
            slot_id = _normalize_id(locked.get("timeslot_id"))
            faculty_ids = subject_faculty_ids(subject)
            unavailable_faculty = [
                faculty_id
                for faculty_id in faculty_ids
                if slot_id in self._faculty_unavailable(faculty_id)
            ]
            busy_faculty = [
                faculty_id
                for faculty_id in faculty_ids
                if slot_id in self._commitment_conflicts(subject, faculty_id)
            ]
            other_locked = [
                entry.get("subject_id")
                for entry in self.locked_by_slot.get(slot_id, [])
                if entry.get("subject_id") != subject.get("id")
            ]
            subject_group = str(subject.get("elective_group_id") or "").strip()
            can_share_with_other_locks = bool(other_locked and subject.get("is_elective") and subject_group)
            if can_share_with_other_locks:
                for other_subject_id in other_locked:
                    other = self.subjects_by_id.get(other_subject_id) or {}
                    other_group = str(other.get("elective_group_id") or "").strip()
                    if not (
                        other.get("is_elective")
                        and other_group
                        and other_group == subject_group
                    ):
                        can_share_with_other_locks = False
                        break
            reasons = []
            if slot_id in self.break_slot_ids:
                reasons.append("Break slot forces the variable FALSE")
            if unavailable_faculty:
                reasons.append(f"Faculty unavailable: {unavailable_faculty}")
            if busy_faculty:
                reasons.append(f"Faculty commitment conflict: {busy_faculty}")
            if other_locked and not can_share_with_other_locks:
                reasons.append(f"Section slot also locked for subjects {other_locked}")
            checks.append({
                "subject_id": subject.get("id"),
                "subject_name": subject.get("name"),
                "timeslot_id": slot_id,
                "lock_source": locked.get("lock_source") or "Unknown",
                "faculty_available": not unavailable_faculty and not busy_faculty,
                "section_free": not other_locked or can_share_with_other_locks,
                "continuous_valid": slot_id not in self.break_slot_ids,
                "reasons": reasons,
            })
        return checks

    def _faculty_conflicts(self) -> List[Dict[str, Any]]:
        conflicts = []
        for subject in self.subjects:
            for faculty_id in subject_faculty_ids(subject):
                for slot_id in sorted(self._faculty_unavailable(faculty_id)):
                    conflicts.append({
                        "faculty_id": faculty_id,
                        "faculty_name": (self.faculty_by_id.get(faculty_id) or {}).get("name"),
                        "current_subject": subject.get("name"),
                        "current_subject_id": subject.get("id"),
                        "conflicting_subject_id": None,
                        "conflicting_section": None,
                        "timeslot_id": slot_id,
                        "conflict_type": "Faculty Unavailability",
                    })
                for slot_id in sorted(self._commitment_conflicts(subject, faculty_id)):
                    entries = self._prior_entries(faculty_id, slot_id)
                    if entries:
                        for entry in entries:
                            conflicts.append({
                                "faculty_id": faculty_id,
                                "faculty_name": (self.faculty_by_id.get(faculty_id) or {}).get("name"),
                                "current_subject": subject.get("name"),
                                "current_subject_id": subject.get("id"),
                                "conflicting_subject_id": entry.get("subject_id"),
                                "conflicting_section": entry.get("section_name"),
                                "timeslot_id": slot_id,
                                "conflict_type": "Existing Timetable Commitment",
                            })
                    else:
                        conflicts.append({
                            "faculty_id": faculty_id,
                            "faculty_name": (self.faculty_by_id.get(faculty_id) or {}).get("name"),
                            "current_subject": subject.get("name"),
                            "current_subject_id": subject.get("id"),
                            "conflicting_subject_id": None,
                            "conflicting_section": None,
                            "timeslot_id": slot_id,
                            "conflict_type": "Approved Commitment",
                        })
        return conflicts

    def _multi_faculty(self) -> List[Dict[str, Any]]:
        rows = []
        for subject in self.subjects:
            faculty_ids = subject_faculty_ids(subject)
            if len(faculty_ids) <= 1:
                continue
            availability = {}
            common = set(self.teaching_slot_ids)
            shared_busy = set()
            for faculty_id in faculty_ids:
                busy = (
                    self._faculty_unavailable(faculty_id)
                    | self._commitment_conflicts(subject, faculty_id)
                )
                available = self.teaching_slot_ids - busy - self._locked_conflicts(subject)
                availability[faculty_id] = {
                    "available_slots": sorted(available),
                    "unavailable_slots": sorted(self._faculty_unavailable(faculty_id)),
                    "commitment_slots": sorted(self._commitment_conflicts(subject, faculty_id)),
                }
                common &= available
                shared_busy |= busy
            rows.append({
                "subject_id": subject.get("id"),
                "subject_name": subject.get("name"),
                "faculty_ids": faculty_ids,
                "faculty_availability": availability,
                "shared_busy_slots": sorted(shared_busy),
                "common_available_slots": sorted(common),
            })
        return rows

    def _analyze(self) -> Dict[str, Any]:
        subject_rows = [self._analyze_subject(subject) for subject in self.subjects]
        locked_checks = self._locked_slot_checks()
        contradictions = [
            {
                "subject_id": check["subject_id"],
                "subject_name": check["subject_name"],
                "timeslot_id": check["timeslot_id"],
                "forced_true_by": check["lock_source"],
                "forced_false_by": check["reasons"],
            }
            for check in locked_checks
            if check["reasons"]
        ]
        return {
            "summary": {
                "subjects": len(self.subjects),
                "faculty": len(self.faculty),
                "teaching_slots": len(self.teaching_slot_ids),
                "break_slots": len(self.break_slot_ids),
                "locked_slots": len(self.locked_slots),
                "available_slots": max(0, len(self.teaching_slot_ids) - len(self.locked_by_slot)),
                "coverage_mode": self.constraints.get("coverage_mode") or "strict",
                "continuous_subjects": sum(
                    1 for subject in self.subjects
                    if _safe_int(subject.get("continuous_hours", 1) or 1, 1) > 1
                ),
                "multi_faculty_subjects": sum(
                    1 for subject in self.subjects
                    if len(subject_faculty_ids(subject)) > 1
                ),
                "cbcs_subjects": sum(1 for subject in self.subjects if subject.get("is_cbcs_shared")),
                "elective_subjects": sum(1 for subject in self.subjects if subject.get("is_elective")),
                "section_override_subjects": sum(
                    1 for subject in self.subjects
                    if subject.get("section_override_applied")
                ),
            },
            "subjects": subject_rows,
            "locked_checks": locked_checks,
            "contradictions": contradictions,
            "faculty_conflicts": self._faculty_conflicts(),
            "multi_faculty": self._multi_faculty(),
        }

    def log_input_report(self) -> None:
        summary = self.analysis["summary"]
        logger.info(
            "\n"
            "================ AI ENGINE SOLVER INPUT SUMMARY ================\n"
            "Total Subjects: %(subjects)s\n"
            "Total Faculty: %(faculty)s\n"
            "Teaching Slots: %(teaching_slots)s\n"
            "Break Slots: %(break_slots)s\n"
            "Locked Slots: %(locked_slots)s\n"
            "Available Slots: %(available_slots)s\n"
            "Coverage Mode: %(coverage_mode)s\n"
            "Continuous Subjects: %(continuous_subjects)s\n"
            "Multi-Faculty Subjects: %(multi_faculty_subjects)s\n"
            "CBCS Subjects: %(cbcs_subjects)s\n"
            "Elective Subjects: %(elective_subjects)s\n"
            "Section Override Subjects: %(section_override_subjects)s\n"
            "================================================================",
            summary,
        )

        for row in self.analysis["subjects"]:
            stage_lines = []
            for stage in row["stages"]:
                stage_lines.append(
                    f"{stage['constraint']}: {stage['remaining']} candidates"
                    + (
                        f" (removed slot_ids={stage.get('removed')})"
                        if stage.get("removed")
                        else ""
                    )
                    + (
                        f" (candidate_blocks={stage.get('candidate_blocks')})"
                        if stage.get("candidate_blocks") is not None
                        else ""
                    )
                )
            logger.info(
                "\n"
                "---------------- SUBJECT CONSTRAINT REPORT ----------------\n"
                "Subject: %s [subject_id=%s]\n"
                "Weekly Hours: %s\n"
                "Continuous Hours: %s\n"
                "Faculty IDs: %s\n"
                "Locked Slots: %s\n"
                "Possible Slots Before Constraints: %s\n"
                "%s\n"
                "Final Candidate Slots: %s\n"
                "Final Candidate Blocks: %s\n"
                "-----------------------------------------------------------",
                row["name"],
                row["subject_id"],
                row["weekly_hours"],
                row["continuous_hours"],
                row["faculty_ids"] or "None",
                [self._slot_label(slot_id) for slot_id in row["locked_slots"]] or "None",
                row["stages"][0]["remaining"],
                "\n".join(stage_lines),
                [self._slot_label(slot_id) for slot_id in row["final_candidate_slots"]] or "None",
                [
                    [self._slot_label(slot_id) for slot_id in block]
                    for block in row["valid_blocks"]
                ] or "None",
            )

            if row["continuous_hours"] > 1:
                rejected = [
                    {
                        "slots": [self._slot_label(slot_id) for slot_id in block["slots"]],
                        "reason": block["reason"],
                    }
                    for block in row["rejected_blocks"]
                ]
                logger.info(
                    "Continuous Block Analysis: subject=%s [subject_id=%s], required_block=%s, "
                    "accepted_blocks=%s, rejected_blocks=%s%s",
                    row["name"],
                    row["subject_id"],
                    row["continuous_hours"],
                    len(row["valid_blocks"]),
                    rejected,
                    " - No legal consecutive block exists." if not row["valid_blocks"] else "",
                )

            if row["blocking_reasons"]:
                logger.warning(
                    "Subject became unschedulable: subject=%s [subject_id=%s], "
                    "constraint=%s, remaining_slots=%s, remaining_blocks=%s",
                    row["name"],
                    row["subject_id"],
                    row["blocking_reasons"],
                    len(row["final_candidate_slots"]),
                    len(row["valid_blocks"]),
                )

        for row in self.analysis["multi_faculty"]:
            logger.info(
                "Multi-Faculty Diagnostic: subject=%s [subject_id=%s], faculty_ids=%s, "
                "faculty_availability=%s, shared_busy_slots=%s, common_available_slots=%s%s",
                row["subject_name"],
                row["subject_id"],
                row["faculty_ids"],
                {
                    faculty_id: {
                        "available_count": len(details["available_slots"]),
                        "unavailable_slots": details["unavailable_slots"],
                        "commitment_slots": details["commitment_slots"],
                    }
                    for faculty_id, details in row["faculty_availability"].items()
                },
                row["shared_busy_slots"],
                row["common_available_slots"],
                (
                    " - Subject cannot be scheduled because no common availability exists "
                    "among assigned faculty."
                    if not row["common_available_slots"]
                    else ""
                ),
            )

        for check in self.analysis["locked_checks"]:
            logger.info(
                "Locked Slot Verification: subject=%s [subject_id=%s], slot=%s, reason=%s, "
                "faculty_available=%s, section_free=%s, continuous_block_valid=%s%s",
                check["subject_name"],
                check["subject_id"],
                self._slot_label(check["timeslot_id"]),
                check["lock_source"],
                "YES" if check["faculty_available"] else "NO",
                "YES" if check["section_free"] else "NO",
                "YES" if check["continuous_valid"] else "NO",
                f", failed_conditions={check['reasons']}" if check["reasons"] else "",
            )

        for conflict in self.analysis["faculty_conflicts"]:
            logger.info(
                "Faculty Conflict: faculty=%s [faculty_id=%s], current_subject=%s "
                "[subject_id=%s], conflicting_subject_id=%s, conflicting_section=%s, "
                "timeslot=%s, conflict_type=%s",
                conflict["faculty_name"],
                conflict["faculty_id"],
                conflict["current_subject"],
                conflict["current_subject_id"],
                conflict["conflicting_subject_id"],
                conflict["conflicting_section"],
                self._slot_label(conflict["timeslot_id"]),
                conflict["conflict_type"],
            )

        for contradiction in self.analysis["contradictions"]:
            logger.error(
                "Contradiction Detected: variable=x(%s,%s), subject_id=%s, timeslot_id=%s, "
                "forced TRUE by=%s, forced FALSE by=%s, result=Impossible",
                contradiction["subject_name"],
                self._slot_label(contradiction["timeslot_id"]),
                contradiction["subject_id"],
                contradiction["timeslot_id"],
                contradiction["forced_true_by"],
                contradiction["forced_false_by"],
            )

    def log_failure_summary(
        self,
        core_reasons: Optional[Iterable[str]] = None,
        seed: Optional[int] = None,
    ) -> None:
        unschedulable = [
            row
            for row in self.analysis["subjects"]
            if row["blocking_reasons"]
        ]
        responsible = sorted({
            reason
            for row in unschedulable
            for reason in row["blocking_reasons"]
        })
        faculty_ids = sorted({
            faculty_id
            for row in unschedulable
            for faculty_id in row["faculty_ids"]
        })
        core_reasons = list(core_reasons or [])
        suggested = (
            f"Inspect faculty commitments and availability for Faculty {faculty_ids[0]}."
            if faculty_ids
            else "Inspect locked slots, section capacity, weekly-hour coverage, and elective links."
        )
        rows = [
            {
                "subject": row["name"],
                "subject_id": row["subject_id"],
                "candidate_slots": len(row["final_candidate_slots"]),
                "candidate_blocks": len(row["valid_blocks"]),
                "faculty_ids": row["faculty_ids"],
                "locked_slots": row["locked_slots"],
                "reason": row["blocking_reasons"],
            }
            for row in (unschedulable or self.analysis["subjects"])
        ]
        logger.error(
            "\n"
            "================ CP-SAT FAILURE SUMMARY ================\n"
            "Seed: %s\n"
            "Unschedulable Subject Report: %s\n"
            "Constraint Responsible: %s\n"
            "Faculty Causing Rejection: %s\n"
            "Locked Slot Conflict: %s\n"
            "Variable-Level Contradictions: %s\n"
            "Unsat Core Reasons: %s\n"
            "Suggested Investigation: %s\n"
            "========================================================",
            seed,
            rows,
            responsible or "No zero-candidate constraint found; inspect unsat core.",
            faculty_ids or "None identified",
            "YES" if self.analysis["contradictions"] else "NO",
            self.analysis["contradictions"] or "None",
            core_reasons or "No core reason returned.",
            suggested,
        )
