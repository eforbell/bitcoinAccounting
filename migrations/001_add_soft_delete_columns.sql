-- Migration: Add soft-delete columns to ledger table
-- Run as table owner or superuser:
--   psql -U <owner> -d <database> -f migrations/001_add_soft_delete_columns.sql
--
-- This is idempotent - safe to run multiple times.

ALTER TABLE ledger ADD COLUMN IF NOT EXISTS deleted INTEGER DEFAULT 0;
ALTER TABLE ledger ADD COLUMN IF NOT EXISTS deleted_date TEXT;

-- Verify
DO $$
BEGIN
    RAISE NOTICE 'Migration complete. Columns added:';
    RAISE NOTICE '  deleted INTEGER DEFAULT 0';
    RAISE NOTICE '  deleted_date TEXT';
END $$;
