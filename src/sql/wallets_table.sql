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
    ('Vault', 'hardware', 'self-custodied', 'Cold storage hardware wallet (main seed)'),
    ('Ledger-2', 'hardware', 'self-custodied', 'Ledger hardware wallet (secondary seed)'),
    ('CC', 'software', 'self-custodied', 'Casa Connect wallet'),
    ('LN', 'lightning', 'self-custodied', 'Lightning Network node wallet'),
    ('Kraken', 'exchange', 'custodial', 'Kraken exchange account'),
    ('Coinbase Pro', 'exchange', 'custodial', 'Coinbase Pro trading account'),
    ('Swan Bitcoin', 'exchange', 'custodial', 'Swan Bitcoin DCA account'),
    ('Muun', 'software', 'self-custodied', 'Muun mobile wallet'),
    ('Bitkey', 'hardware', 'multisig', 'Bitkey 2-of-3 multisig wallet');

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.wallets TO "bitcoin_accounting";

-- Add comment
COMMENT ON TABLE public.wallets IS 'Metadata about each wallet/account tracked in the ledger. Helps clarify IRS "account" classification for per-wallet basis tracking (required 2025+).';
