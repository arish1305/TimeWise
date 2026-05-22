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

# The call to wait_for_db should be done within the application startup

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
