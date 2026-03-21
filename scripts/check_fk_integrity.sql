-- FK integrity validation script (ops condition C3).
-- Run after `alembic upgrade head` to verify all foreign key constraints
-- are present and valid in the migrated schema.
--
-- Usage:
--   psql "$DATABASE_URL" -f scripts/check_fk_integrity.sql
--
-- Exit code is non-zero if any expected FK constraint is missing.

\set ON_ERROR_STOP on

DO $$
DECLARE
    expected_constraints TEXT[][] := ARRAY[
        ARRAY['jobs', 'jobs_worker_id_fkey', 'worker_status', 'worker_id']
    ];
    rec TEXT[];
    found_count INTEGER;
    failed INTEGER := 0;
BEGIN
    FOREACH rec SLICE 1 IN ARRAY expected_constraints
    LOOP
        SELECT COUNT(*) INTO found_count
        FROM information_schema.referential_constraints rc
        JOIN information_schema.key_column_usage kcu
            ON kcu.constraint_name = rc.constraint_name
           AND kcu.constraint_schema = rc.constraint_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = rc.unique_constraint_name
           AND ccu.constraint_schema = rc.unique_constraint_schema
        WHERE kcu.table_name  = rec[1]   -- source table
          AND rc.constraint_name = rec[2] -- constraint name
          AND ccu.table_name  = rec[3]   -- referenced table
          AND ccu.column_name = rec[4];  -- referenced column

        IF found_count = 0 THEN
            RAISE WARNING 'MISSING FK: %.% -> %.%',
                rec[1], rec[2], rec[3], rec[4];
            failed := failed + 1;
        ELSE
            RAISE NOTICE 'OK: FK %.% -> %.%',
                rec[1], rec[2], rec[3], rec[4];
        END IF;
    END LOOP;

    IF failed > 0 THEN
        RAISE EXCEPTION 'FK integrity check failed: % constraint(s) missing', failed;
    END IF;

    RAISE NOTICE 'FK integrity check passed (% constraint(s) verified)',
        array_length(expected_constraints, 1);
END;
$$;
