from typing import Dict, Any, List, Set
from ortools.sat.python import cp_model
import logging
import sys
import os

# Insert the workspace root to sys.path to allow importing from the common package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from common.combined_class import is_combined_class, is_shared_combined_class
from .faculty_pool import subject_faculty_ids

logger = logging.getLogger(__name__)

def register_hard_constraints(
    model: cp_model.CpModel,
    x: Dict[int, Dict[int, cp_model.IntVar]],
    subjects: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]],
    constraints: Dict[str, Any],
    locked_slots: List[Dict[str, Any]],
    elective_groups: Dict[str, List[int]]
):
    """
    Registers all hard scheduling constraints (weekly hours, non-overlap, faculty availability,
    locked slots, CBCS parallel placement, and continuous lab blocks).
    """
    timeslots_by_id = {t["id"]: t for t in timeslots}
    subjects_by_id = {s["id"]: s for s in subjects}
    
    # Sort timeslots by day and start time to group them by day
    # Normalize day to lowercase for consistent grouping
    slots_by_day = {}
    for t in timeslots:
        day = t.get("day", "Unknown").lower()
        slots_by_day.setdefault(day, []).append(t)
    for day in slots_by_day:
        slots_by_day[day].sort(key=lambda t: t.get("time") or "")

    num_days = len(slots_by_day)
    all_slot_ids = [t["id"] for t in timeslots]

    # Group subjects by faculty
    faculty_subjects = {}
    for s in subjects:
        for fid in subject_faculty_ids(s):
            faculty_subjects.setdefault(fid, []).append(s["id"])

    # 1. Locked Slots Constraints
    locked_slots_by_tid = {}
    locked_subject_hours = {}
    for locked in locked_slots:
        tid = locked.get("timeslot_id")
        sid = locked.get("subject_id")
        if tid is not None:
            locked_slots_by_tid.setdefault(tid, set())
            if sid:
                locked_slots_by_tid[tid].add(sid)
                locked_subject_hours[sid] = locked_subject_hours.get(sid, 0) + 1

    # Enforce locked slots
    for tid, locked_sids in locked_slots_by_tid.items():
        if tid in timeslots_by_id:
            for sid in locked_sids:
                if sid in subjects_by_id:
                    model.Add(x[sid][tid] == 1)
            for other_sid in subjects_by_id:
                if other_sid not in locked_sids:
                    model.Add(x[other_sid][tid] == 0)

    # 1b. Break Timeslots Constraints (Teaching not allowed in break slots)
    for t in timeslots:
        if t.get("is_break", False):
            tid = t["id"]
            for sid in subjects_by_id:
                model.Add(x[sid][tid] == 0)

    non_locked_slot_ids = [t["id"] for t in timeslots if t["id"] not in locked_slots_by_tid]
    non_locked_teaching_slot_ids = [
        t["id"]
        for t in timeslots
        if t["id"] not in locked_slots_by_tid and not t.get("is_break", False)
    ]
    available_capacity = len(non_locked_teaching_slot_ids)

    # 2. Weekly Hours Complete Constraint
    subject_sessions = {}
    total_demand = 0
    for s in subjects:
        sid = s["id"]
        # Use weekly_hours as primary and only scheduling demand
        weekly_hours = int(s.get("weekly_hours") or s.get("credits"))
        locked_hours = locked_subject_hours.get(sid, 0)
        needed = max(0, weekly_hours - locked_hours)
        subject_sessions[sid] = needed
        total_demand += needed

    coverage_mode = str(constraints.get("coverage_mode") or "").lower()
    allow_partial_schedule = bool(
        constraints.get("allow_partial_schedule", False)
        or coverage_mode in {"partial", "relaxed", "fill_remaining", "repair"}
    )
    strict_coverage = bool(constraints.get("strict_coverage", False))
    use_relaxed_weekly_hours = allow_partial_schedule and not strict_coverage
    logger.info(
        "Coverage constraints: mode=%s, relation=%s, demand=%s, available_non_locked_teaching_slots=%s, locked_entries=%s, unique_locked_slots=%s",
        coverage_mode or ("partial" if use_relaxed_weekly_hours else "strict"),
        "<= weekly_hours" if use_relaxed_weekly_hours else "== weekly_hours",
        total_demand,
        available_capacity,
        sum(len(sids) for sids in locked_slots_by_tid.values()),
        len(locked_slots_by_tid),
    )
    if use_relaxed_weekly_hours:
        logger.warning(
            "RELAXED COVERAGE MODE: locked slots, breaks, section clashes, faculty clashes, "
            "and continuous block rules remain hard; remaining weekly hours use <= and the objective maximizes fill."
        )

    for s in subjects:
        sid = s["id"]
        sessions_needed = subject_sessions[sid]
        
        if non_locked_teaching_slot_ids:
            non_locked_sum = sum(x[sid][tid] for tid in non_locked_teaching_slot_ids)
            if sessions_needed > 0:
                if use_relaxed_weekly_hours:
                    model.Add(non_locked_sum <= sessions_needed)
                else:
                    model.Add(non_locked_sum == sessions_needed)
            else:
                model.Add(non_locked_sum == 0)

    # 3. Section Non-Overlap Constraint
    elective_representatives = {}
    for group_id, sids in elective_groups.items():
        if sids:
            elective_representatives[group_id] = sids[0]

    for t in timeslots:
        tid = t["id"]
        overlap_terms = []
        for s in subjects:
            sid = s["id"]
            is_group_elective = any(sid in sids for sids in elective_groups.values())
            if not is_group_elective:
                overlap_terms.append(x[sid][tid])
                
        for group_rep in elective_representatives.values():
            overlap_terms.append(x[group_rep][tid])
            
        if overlap_terms:
            model.Add(sum(overlap_terms) <= 1)

    # 3b. Distinct Section Timetable Constraint
    # Peer entries are regular/non-CBCS/non-elective subjects supplied by the backend.
    # CBCS/elective/manual locks are intentionally excluded because they may be required
    # to be identical across sections.
    if constraints.get("enforce_distinct_sections", True):
        peer_timetables = constraints.get("peer_timetables", []) or []
        distinct_constraints = 0
        for peer in peer_timetables:
            peer_terms = []
            seen_pairs = set()
            for peer_entry in peer.get("entries", []) or []:
                sid = peer_entry.get("subject_id")
                tid = peer_entry.get("timeslot_id")
                pair = (sid, tid)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                if sid in x and tid in x[sid]:
                    peer_terms.append(x[sid][tid])

            if peer_terms:
                model.Add(sum(peer_terms) <= len(peer_terms) - 1)
                distinct_constraints += 1

        if distinct_constraints:
            logger.info(
                "Section diversity hard constraints added: peers=%s, constraints=%s",
                len(peer_timetables),
                distinct_constraints,
            )

    # 4. Faculty Non-Overlap & Prior Commitments Constraints
    prior_commitments = constraints.get("prior_commitments", {}) or {}
    prior_commitment_entries = constraints.get("prior_commitment_entries", {}) or {}
    approved_commitments = constraints.get("approved_commitments", {}) or {}
    faculty_availability = constraints.get("faculty_availability", {}) or {}
    
    def parse_fid(f_id):
        try:
            return int(f_id)
        except (ValueError, TypeError):
            return f_id

    def parse_slot_id(slot_id):
        try:
            return int(slot_id)
        except (ValueError, TypeError):
            return slot_id

    def iter_faculty_slot_mapping(mapping, slot_key):
        if isinstance(mapping, list):
            for item in mapping:
                if not isinstance(item, dict):
                    continue
                fid = item.get("faculty_id")
                if fid is None:
                    continue
                if "timeslot_id" in item:
                    yield fid, [item.get("timeslot_id")]
                else:
                    yield fid, item.get(slot_key, []) or item.get("occupied_slots", []) or []
            return

        if isinstance(mapping, dict):
            for fid, value in mapping.items():
                if isinstance(value, dict):
                    yield fid, value.get(slot_key, []) or value.get("occupied_slots", []) or []
                else:
                    yield fid, value or []

    fac_prior_slots = {}
    for fid, slots in iter_faculty_slot_mapping(prior_commitments, "occupied_slots"):
        pfid = parse_fid(fid)
        fac_prior_slots.setdefault(pfid, set()).update(parse_slot_id(slot) for slot in (slots or []))
    for fid, slots in iter_faculty_slot_mapping(approved_commitments, "occupied_slots"):
        pfid = parse_fid(fid)
        fac_prior_slots.setdefault(pfid, set()).update(parse_slot_id(slot) for slot in (slots or []))

    fac_prior_subjects = {}
    fac_prior_section_names = {}
    for fid, entries in prior_commitment_entries.items():
        pfid = parse_fid(fid)
        for entry in entries or []:
            ts_id = entry.get("timeslot_id")
            sub_id = entry.get("subject_id")
            sec_name = entry.get("section_name") or "Unknown"
            if ts_id is not None and sub_id is not None:
                fac_prior_subjects.setdefault(pfid, {}).setdefault(ts_id, []).append(sub_id)
                fac_prior_section_names.setdefault(pfid, {}).setdefault(ts_id, {})[sub_id] = sec_name

    fac_unavailable_slots = {}
    for fid, slots in iter_faculty_slot_mapping(faculty_availability, "unavailable_slots"):
        pfid = parse_fid(fid)
        fac_unavailable_slots.setdefault(pfid, set()).update(parse_slot_id(slot) for slot in (slots or []))

    faculty_prefs = constraints.get("faculty_preferences", {}) or {}

    for f in faculty:
        fid = f["id"]
        pfid = parse_fid(fid)
        sids = faculty_subjects.get(fid, [])
        if not sids:
            continue
            
        prefs = faculty_prefs.get(str(fid)) or faculty_prefs.get(fid) or {}
        max_hours = int(prefs.get("max_hours", 18) or 18)
        model.Add(sum(x[sid][tid] for sid in sids for tid in all_slot_ids) <= max_hours)

        for t in timeslots:
            tid = t["id"]
            if tid in fac_unavailable_slots.get(pfid, set()):
                for sid in sids:
                    model.Add(x[sid][tid] == 0)
                continue

            has_prior = tid in fac_prior_slots.get(pfid, set())
            
            if has_prior:
                prior_sids = fac_prior_subjects.get(pfid, {}).get(tid, [])
                cbcs_sid = None
                for sid in sids:
                    subj = subjects_by_id[sid]
                    
                    is_bypassed = False
                    for prior_sid in prior_sids:
                        prior_subj = subjects_by_id.get(prior_sid)
                        if prior_subj:
                            conflict_sec = fac_prior_section_names.get(pfid, {}).get(tid, {}).get(prior_sid, "Unknown")
                            
                            # Resolve slot names for logger
                            slot_names = []
                            subj_slots = subj.get("resolved_manual_timeslot_ids")
                            if subj_slots is None:
                                subj_slots = subj.get("manual_timeslot_ids") or []
                            subj_slots = [int(s) for s in subj_slots if s is not None]
                            if subj_slots:
                                DAY_ORDER_LIST = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                                matched_slots = [timeslots_by_id[s_id] for s_id in subj_slots if s_id in timeslots_by_id]
                                matched_slots.sort(key=lambda t: (
                                    DAY_ORDER_LIST.index(t.get("day", "").capitalize()) if t.get("day", "").capitalize() in DAY_ORDER_LIST else 99,
                                    t.get("time") or ""
                                ))
                                slot_names = [t.get("day", "")[:3].capitalize() if t.get("day") else str(t["id"]) for t in matched_slots]

                            is_bypassed = is_shared_combined_class(
                                subject=subj,
                                conflict_subject=prior_subj,
                                slot_id=tid,
                                faculty_id=pfid,
                                conflict_faculty_id=pfid,
                                conflict_slot_id=tid,
                                is_different_section=True,
                                faculty_name=f.get("name") or str(pfid),
                                subject_code=subj.get("code") or str(subj["id"]),
                                subject_name=subj.get("name") or "Unknown",
                                current_section=constraints.get("section_name") or "Unknown",
                                conflict_section=conflict_sec,
                                slot_names=slot_names
                            )
                            if is_bypassed:
                                break
                    
                    if is_bypassed:
                        cbcs_sid = sid
                        break
                        
                if cbcs_sid is not None:
                    model.Add(x[cbcs_sid][tid] == 1)
                    for sid in sids:
                        if sid != cbcs_sid:
                            model.Add(x[sid][tid] == 0)
                else:
                    for sid in sids:
                        model.Add(x[sid][tid] == 0)
            else:
                model.Add(sum(x[sid][tid] for sid in sids) <= 1)

    # 5. Continuous Blocks & Daily Limits
    for s in subjects:
        sid = s["id"]
        continuous_hours = int(s.get("continuous_hours", 1) or 1)
        weekly_hours = int(s.get("weekly_hours") or s.get("credits"))
        
        if continuous_hours > 1:
            # --- Continuous Block Subject (Lab / Project Work / etc.) ---
            locked_hours = locked_subject_hours.get(sid, 0)
            sessions_needed = max(0, weekly_hours - locked_hours)
            
            if sessions_needed >= continuous_hours:
                blocks_needed = 1
                remainder = sessions_needed - continuous_hours
            else:
                blocks_needed = 0
                remainder = sessions_needed
            logger.info(
                "Subject: %s\nWeekly Hours: %s\nContinuous Hours: %s\nScheduling Pattern:\n%s mandatory %s-hour block\n%s independent hours",
                s.get("name"), weekly_hours, continuous_hours, blocks_needed, continuous_hours, remainder
            )
            
            if blocks_needed > 0:
                all_block_starts = []
                block_starts_by_slot = {tid: [] for tid in non_locked_teaching_slot_ids}
                day_index = 0
                for day, day_slots in slots_by_day.items():
                    k = continuous_hours
                    
                    day_block_starts = []
                    if len(day_slots) >= k:
                        for j in range(len(day_slots) - k + 1):
                            block_slot_ids = [day_slots[j + offset]["id"] for offset in range(k)]
                            if any(slot_id not in non_locked_teaching_slot_ids for slot_id in block_slot_ids):
                                continue

                            b_var = model.NewBoolVar(f"lab_start_{sid}_d{day_index}_j{j}")
                            day_block_starts.append(b_var)
                            all_block_starts.append(b_var)
                            
                            for slot_id in block_slot_ids:
                                model.Add(x[sid][slot_id] >= b_var)
                                block_starts_by_slot[slot_id].append(b_var)
                                
                    if day_block_starts:
                        model.Add(sum(day_block_starts) <= 1)
                    
                    day_index += 1

                remainder_by_slot = {}
                if remainder > 0:
                    remainder_vars = []
                    for slot_id in non_locked_teaching_slot_ids:
                        r_var = model.NewBoolVar(f"block_remainder_{sid}_{slot_id}")
                        remainder_by_slot[slot_id] = r_var
                        remainder_vars.append(r_var)
                        model.Add(r_var <= x[sid][slot_id])
                        for b_var in block_starts_by_slot.get(slot_id, []):
                            model.Add(r_var + b_var <= 1)

                    if use_relaxed_weekly_hours:
                        model.Add(sum(remainder_vars) <= remainder)
                    else:
                        model.Add(sum(remainder_vars) == remainder)
                        
                if all_block_starts:
                    if use_relaxed_weekly_hours:
                        model.Add(sum(all_block_starts) <= blocks_needed)
                    else:
                        model.Add(sum(all_block_starts) == blocks_needed)
                    
                    total_needed = blocks_needed * continuous_hours + remainder
                    if non_locked_teaching_slot_ids:
                        non_locked_block_sum = sum(x[sid][tid] for tid in non_locked_teaching_slot_ids)
                        if use_relaxed_weekly_hours:
                            model.Add(non_locked_block_sum <= total_needed)
                        else:
                            model.Add(non_locked_block_sum == total_needed)

                    for slot_id in non_locked_teaching_slot_ids:
                        covering_starts = block_starts_by_slot.get(slot_id, [])
                        allowed_terms = list(covering_starts)
                        if slot_id in remainder_by_slot:
                            allowed_terms.append(remainder_by_slot[slot_id])
                        if allowed_terms:
                            model.Add(x[sid][slot_id] <= sum(allowed_terms))
                        else:
                            model.Add(x[sid][slot_id] == 0)
                else:
                    for slot_id in non_locked_teaching_slot_ids:
                        if slot_id in remainder_by_slot:
                            model.Add(x[sid][slot_id] <= remainder_by_slot[slot_id])
                        else:
                            model.Add(x[sid][slot_id] == 0)
                    logger.warning(
                        "Continuous block subject cannot be placed: subject_id=%s, continuous_hours=%s, sessions_needed=%s, valid_block_starts=0",
                        sid,
                        continuous_hours,
                        sessions_needed,
                    )
            
            # Daily limit for block subjects: allow up to continuous_hours per day
            for day, day_slots in slots_by_day.items():
                model.Add(sum(x[sid][t["id"]] for t in day_slots) <= continuous_hours)
        else:
            # --- Theory / single-hour subject ---
            for day, day_slots in slots_by_day.items():
                model.Add(sum(x[sid][t["id"]] for t in day_slots) <= len(day_slots))
