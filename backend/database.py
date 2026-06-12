from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@localhost:5432/timewise")

engine = create_engine(DATABASE_URL)


import time
import logging
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

def wait_for_db(retries=10, delay=2):
    for i in range(retries):
        try:
            # Try to connect
            with engine.connect() as conn:
                logger.info("Database connection successful!")
                return
        except OperationalError:
            logger.warning(f"Database unavailable, waiting {delay}s... ({i+1}/{retries})")
            time.sleep(delay)
    logger.error("Could not connect to database after several retries.")

def migrate_subject_code_uniqueness():
    if engine.dialect.name != "postgresql":
        return

    constraint_column_query = """
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN unnest(c.conkey) WITH ORDINALITY AS u(attnum, ord) ON true
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = u.attnum
        WHERE t.relname = 'subjects' AND c.contype = 'u'
        GROUP BY c.oid, c.conname
        HAVING string_agg(a.attname, ',' ORDER BY u.ord) = :columns
    """

    unique_index_query = """
        SELECT i.relname
        FROM pg_index ix
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN unnest(ix.indkey) WITH ORDINALITY AS u(attnum, ord) ON true
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = u.attnum
        LEFT JOIN pg_constraint c ON c.conindid = i.oid
        WHERE t.relname = 'subjects' AND ix.indisunique AND c.oid IS NULL
        GROUP BY i.oid, i.relname
        HAVING string_agg(a.attname, ',' ORDER BY u.ord) = :columns
    """

    with engine.begin() as conn:
        preparer = conn.dialect.identifier_preparer

        code_constraints = conn.execute(
            text(constraint_column_query),
            {"columns": "code"},
        ).scalars().all()
        for constraint_name in code_constraints:
            conn.execute(text(f"ALTER TABLE subjects DROP CONSTRAINT IF EXISTS {preparer.quote(constraint_name)}"))

        code_indexes = conn.execute(
            text(unique_index_query),
            {"columns": "code"},
        ).scalars().all()
        for index_name in code_indexes:
            conn.execute(text(f"DROP INDEX IF EXISTS {preparer.quote(index_name)}"))

        has_department_code_constraint = conn.execute(
            text("""
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'subjects'::regclass
                  AND conname = 'uq_subject_department_code'
                  AND contype = 'u'
            """)
        ).scalar()

        if not has_department_code_constraint:
            conn.execute(text(
                "ALTER TABLE subjects "
                "ADD CONSTRAINT uq_subject_department_code UNIQUE (department_id, code)"
            ))

def migrate_timeslot_departments():
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        has_department_id = conn.execute(text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'timeslots'
              AND column_name = 'department_id'
        """)).scalar()

        if not has_department_id:
            conn.execute(text("ALTER TABLE timeslots ADD COLUMN department_id INTEGER"))

        has_foreign_key = conn.execute(text("""
            SELECT 1
            FROM pg_constraint c
            JOIN unnest(c.conkey) WITH ORDINALITY AS u(attnum, ord) ON true
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = u.attnum
            WHERE c.conrelid = 'timeslots'::regclass
              AND c.confrelid = 'departments'::regclass
              AND c.contype = 'f'
            GROUP BY c.oid
            HAVING string_agg(a.attname, ',' ORDER BY u.ord) = 'department_id'
        """)).scalar()

        if not has_foreign_key:
            conn.execute(text(
                "ALTER TABLE timeslots "
                "ADD CONSTRAINT fk_timeslots_department_id "
                "FOREIGN KEY (department_id) REFERENCES departments(id)"
            ))


def migrate_section_v2_fields():
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        has_section_name = conn.execute(text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'sections'
              AND column_name = 'section_name'
        """)).scalar()
        if not has_section_name:
            conn.execute(text("ALTER TABLE sections ADD COLUMN section_name VARCHAR"))

        has_year = conn.execute(text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'sections'
              AND column_name = 'year'
        """)).scalar()
        if not has_year:
            conn.execute(text("ALTER TABLE sections ADD COLUMN year INTEGER"))

        has_independent_schedule = conn.execute(text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'sections'
              AND column_name = 'independent_schedule'
        """)).scalar()
        if not has_independent_schedule:
            conn.execute(text("ALTER TABLE sections ADD COLUMN independent_schedule BOOLEAN DEFAULT TRUE"))

        conn.execute(text("UPDATE sections SET section_name = name WHERE section_name IS NULL"))
        conn.execute(text("""
            UPDATE sections s
            SET year = ay.level
            FROM academic_years ay
            WHERE s.academic_year_id = ay.id
              AND s.year IS NULL
        """))
        conn.execute(text("UPDATE sections SET independent_schedule = TRUE WHERE independent_schedule IS NULL"))
        conn.execute(text("ALTER TABLE sections ALTER COLUMN independent_schedule SET NOT NULL"))


def migrate_scheduling_rules():
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scheduling_rules (
                id SERIAL PRIMARY KEY,
                department_id INTEGER NULL REFERENCES departments(id),
                name VARCHAR NOT NULL DEFAULT 'default',
                rules JSONB NOT NULL DEFAULT '{}'::jsonb,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_scheduling_rules_department_active
            ON scheduling_rules(department_id, is_active)
        """))

        has_global_default = conn.execute(text("""
            SELECT 1
            FROM scheduling_rules
            WHERE department_id IS NULL
              AND name = 'default'
              AND is_active = TRUE
            LIMIT 1
        """)).scalar()

        if not has_global_default:
            conn.execute(text("""
                INSERT INTO scheduling_rules (department_id, name, rules, is_active)
                VALUES (
                    NULL,
                    'default',
                    '{"max_daily_subjects": 5, "spread_subjects": true, "allow_saturday": false, "max_lab_per_day": 1}'::jsonb,
                    TRUE
                )
            """))


def migrate_timetable_editing_v2():
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        # Add additive columns on timetable_entries
        for column_name, ddl in [
            ("room_id", "ALTER TABLE timetable_entries ADD COLUMN room_id INTEGER"),
            ("position_x", "ALTER TABLE timetable_entries ADD COLUMN position_x INTEGER"),
            ("position_y", "ALTER TABLE timetable_entries ADD COLUMN position_y INTEGER"),
            ("is_manual", "ALTER TABLE timetable_entries ADD COLUMN is_manual BOOLEAN DEFAULT FALSE"),
            ("edited_by", "ALTER TABLE timetable_entries ADD COLUMN edited_by INTEGER"),
            ("version", "ALTER TABLE timetable_entries ADD COLUMN version INTEGER DEFAULT 1"),
        ]:
            exists = conn.execute(text("""
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'timetable_entries'
                  AND column_name = :column_name
            """), {"column_name": column_name}).scalar()
            if not exists:
                conn.execute(text(ddl))

        has_editor_fk = conn.execute(text("""
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'fk_timetable_entries_edited_by_user'
              AND conrelid = 'timetable_entries'::regclass
        """)).scalar()
        if not has_editor_fk:
            conn.execute(text("""
                ALTER TABLE timetable_entries
                ADD CONSTRAINT fk_timetable_entries_edited_by_user
                FOREIGN KEY (edited_by) REFERENCES users(id)
            """))

        conn.execute(text("UPDATE timetable_entries SET is_manual = FALSE WHERE is_manual IS NULL"))
        conn.execute(text("UPDATE timetable_entries SET version = 1 WHERE version IS NULL"))

        # Event history table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS timetable_edit_events (
                id SERIAL PRIMARY KEY,
                timetable_id INTEGER NOT NULL REFERENCES timetables(id),
                entry_id INTEGER NULL REFERENCES timetable_entries(id),
                event_type VARCHAR NOT NULL,
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                edited_by INTEGER NULL REFERENCES users(id),
                version INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_timetable_edit_events_timetable
            ON timetable_edit_events(timetable_id, created_at DESC)
        """))

def migrate_timetable_versions():
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        for column_name, ddl in [
            ("generated_version", "ALTER TABLE timetables ADD COLUMN generated_version INTEGER DEFAULT 0"),
            ("edited_version", "ALTER TABLE timetables ADD COLUMN edited_version INTEGER DEFAULT 0"),
            ("approved_version", "ALTER TABLE timetables ADD COLUMN approved_version INTEGER DEFAULT 0"),
        ]:
            exists = conn.execute(text("""
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'timetables'
                  AND column_name = :column_name
            """), {"column_name": column_name}).scalar()
            if not exists:
                conn.execute(text(ddl))

        conn.execute(text("UPDATE timetables SET generated_version = 0 WHERE generated_version IS NULL"))
        conn.execute(text("UPDATE timetables SET edited_version = 0 WHERE edited_version IS NULL"))
        conn.execute(text("UPDATE timetables SET approved_version = 0 WHERE approved_version IS NULL"))


def migrate_faculty_availability():
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS faculty_availability (
                id SERIAL PRIMARY KEY,
                faculty_id INTEGER NOT NULL REFERENCES faculty(id),
                timeslot_id INTEGER NOT NULL REFERENCES timeslots(id),
                status VARCHAR NOT NULL DEFAULT 'AVAILABLE',
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_faculty_availability_faculty_timeslot UNIQUE (faculty_id, timeslot_id)
            )
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_faculty_availability_faculty_id
            ON faculty_availability(faculty_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_faculty_availability_timeslot_id
            ON faculty_availability(timeslot_id)
        """))

# The call to wait_for_db should be done within the application startup

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
