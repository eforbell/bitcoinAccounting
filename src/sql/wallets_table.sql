-- ============================================================================
-- DEPRECATED: This file has been consolidated into tables.sql
-- ============================================================================
--
-- The wallets table is now included in tables.sql along with the other
-- core tables (coins, ledger, pair_price).
--
-- For new PostgreSQL setup, use:
--   psql -U admin -d crypto -f src/sql/tables.sql
--
-- This file is kept temporarily for reference but will be removed in a future
-- cleanup. Do NOT apply this file separately - it will cause duplicate table
-- errors since wallets is already in tables.sql.
-- ============================================================================

-- Wallet metadata table to clarify what each "exchange" label represents
-- This helps distinguish between custodial accounts, self-custodied wallets, etc.

CREATE TABLE public.wallets (
    wallet_id varchar(32) PRIMARY KEY,  -- Matches ledger.exchange field
    wallet_type varchar(20) NOT NULL,   -- 'exchange', 'hardware', 'software', 'lightning', 'pool'
    custody varchar(20) NOT NULL,       -- 'custodial', 'self-custodied', 'multisig'
    description varchar(500),           -- Human-readable description
    seed_info varchar(500),             -- Optional: xpub or seed reference (encrypted/hashed)
    active boolean DEFAULT true,        -- Whether still in use
    created_date timestamp DEFAULT CURRENT_TIMESTAMP,
    notes text                          -- Additional notes
);

-- Example data
INSERT INTO public.wallets (wallet_id, wallet_type, custody, description) VALUES
    ('Strike', 'exchange', 'custodial', 'Strike account - custodial exchange wallet'),
    ('River', 'exchange', 'custodial', 'River Financial account - custodial exchange wallet'),

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.wallets TO "bitcoin_accounting";

-- Add comment
COMMENT ON TABLE public.wallets IS 'Metadata about each wallet/account tracked in the ledger. Helps clarify IRS "account" classification for per-wallet basis tracking (required 2025+).';
