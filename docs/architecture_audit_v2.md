# TimeWise AI v2 Architecture Audit

## Scope
- Backend: `backend/routers/admin.py`, `backend/routers/timetable.py`, `backend/models.py`, `backend/schemas.py`
- Scheduler service: `ai_engine/main.py`, `ai_engine/scheduler.py`
- Frontend: `frontend/src/pages/Departments.tsx`, `frontend/src/pages/Timetables.tsx`

## Findings

### Duplicate scheduling logic
- `backend/routers/timetable.py` contains `_solve_timetable_locally(...)`.
- `ai_engine/scheduler.py` also contains a full scheduler implementation.
- Result: scheduling behavior differs based on code path and fallback conditions.

### Multiple ownership of scheduling decisions
- Backend orchestrator decides locked slots, CBCS, manual locks, back-to-back reservation, validation.
- AI engine also decides subject spread and faculty/load constraints independently.
- Frontend passes scheduling-influencing metadata (`manual_timeslot_ids`, back-to-back controls), but should remain CRUD-focused only.

### Overloaded router modules
- `admin.py` contains CRUD, bulk import parser, XLSX template generation, department schedule builder, and timeslot APIs in one file.
- `timetable.py` contains generation, validation, conflict checks, versioning behavior, and faculty timetable projection in one file.

### Dead/unused paths and components
- `frontend/src/pages/TimeSlots.tsx` is present but not routed in `frontend/src/App.tsx`.
- Legacy timeslot CRUD APIs remain active though department schedule builder is now primary.

### Data model shape issues
- Section identity split between `AcademicYear` + `Section.name`; no explicit independent-schedule field existed.
- Rules were hardcoded in code; no DB-backed rule profile for per-department behavior.

## Components To Keep
- FastAPI + SQLAlchemy + PostgreSQL core stack.
- Current admin CRUD APIs for departments/faculty/subjects/sections.
- Timetable versioning behavior (`ARCHIVED`, `DRAFT`, `ACTIVE`).
- Department day schedule builder endpoint.
- Manual locks and CBCS/elective overlap rules.
- Existing frontend screens and export flows.

## Components To Merge
- Merge scheduling decision ownership behind one backend orchestration contract.
- Merge rule constants into DB-backed rule profiles (`scheduling_rules.rules` JSONB).
- Merge section identity into explicit section metadata (`section_name`, `year`, `independent_schedule`) while keeping old fields for compatibility.

## Components To Remove (after deprecation window)
- Local scheduler copy in backend once scheduler service path is fully deterministic and feature-equal.
- Unrouted frontend `TimeSlots.tsx`.
- Generic `/admin/timeslots` mutation workflow after all departments migrate to schedule builder.

## Immediate Risk Areas
- Timetable uniqueness across sections in same year/semester was not hard-failed previously.
- Fallback path differences can cause drift in spread/load behavior.
- Rule changes required code edits before v2 rule storage.

