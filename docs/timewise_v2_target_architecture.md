# TimeWise AI v2 Target Architecture

## Design Principles
- Preserve all existing features and API compatibility where possible.
- Keep frontend focused on CRUD, visualization, manual editing, and validation display.
- Keep business rules and scheduling decisions in backend + scheduler service.
- Prefer simple modules over layered abstractions.

## v2 Responsibilities

### Frontend (React)
- CRUD for master data.
- Timetable generation triggers and result display.
- Manual lock operations and export operations.
- No scheduling algorithms in UI.

### Backend (FastAPI)
- Master data APIs.
- Rule loading from DB (`scheduling_rules.rules` JSONB).
- Generation orchestration pipeline.
- Versioning, validation, and repair hooks.

### Database (PostgreSQL)
- Core entities: departments, sections, faculty, subjects, timeslots, timetables, timetable_entries.
- New: `scheduling_rules` (JSONB rule profiles).
- New section metadata: `section_name`, `year`, `independent_schedule`.

### Scheduler Service
- Constraint satisfaction + repair-style scheduling.
- Inputs: subjects, faculty, timeslots, locked slots, prior commitments, rules.
- Output: conflict-free candidate schedule.

## Generation Pipeline (v2)
1. Load section + master data.
2. Load effective rules (department-specific, fallback to global default).
3. Load committed schedules and faculty commitments.
4. Apply locked slots and manual constraints.
5. Generate section timetable candidate.
6. Validate hard constraints.
7. Run repair (if enabled) for soft issues.
8. Commit new timetable version.

## Hard Constraints
- Faculty overlap prevention.
- Section overlap prevention.
- Section uniqueness within same year/semester.
- Invalid assignment prevention.

## Soft Constraints
- Subject spread quality.
- Faculty daily load balancing.
- Distribution quality warnings.

## Migration Strategy
1. Add v2 section fields and backfill from existing rows.
2. Add scheduling rules table with a default global rule record.
3. Keep existing APIs; incrementally route read/write through v2 structures.
4. Keep rollback path by non-destructive additive migrations.

