-- public.coins definition

-- Drop table

-- DROP TABLE public.coins;

CREATE TABLE public.coins (
	"name" varchar(40) NOT NULL,
	max_supply int8 NULL,
	circ_supply int8 NULL,
	CONSTRAINT coins_pkey PRIMARY KEY (name)
);

-- public.ledger definition

-- Drop table

-- DROP TABLE public.ledger;

CREATE TABLE public.ledger (
	createddate timestamp(0) NOT NULL,
	trans_type varchar(32) NULL,
	buy float8 NULL,
	buy_curr varchar(40) NULL,
	sell float8 NULL,
	sell_curr varchar(40) NULL,
	fee float8 NULL,
	fee_curr varchar(40) NULL,
	exchange varchar(32) NULL,
	"group" varchar(32) NULL,
	"comment" varchar(5000) NULL,
	transactionid varchar(5000) NULL,
	id serial4 NOT NULL,
	deleted int4 DEFAULT 0,
	deleted_date text NULL,
	CONSTRAINT ledger_pkey PRIMARY KEY (id)
);
-- public.pair_price definition

-- Drop table

-- DROP TABLE public.pair_price;

CREATE TABLE public.pair_price (
	to_curr varchar(40) NOT NULL,
	price numeric NOT NULL,
	from_curr varchar(40) NOT NULL,
	"date" date NULL
);

-- public.wallets definition

-- Drop table

-- DROP TABLE public.wallets;

CREATE TABLE public.wallets (
	wallet_id varchar(32) NOT NULL,
	wallet_type varchar(20) NOT NULL,
	custody varchar(20) NOT NULL,
	description varchar(500) NULL,
	seed_info varchar(500) NULL,
	active bool DEFAULT true,
	created_date timestamp DEFAULT CURRENT_TIMESTAMP,
	notes text NULL,
	CONSTRAINT wallets_pkey PRIMARY KEY (wallet_id)
);

COMMENT ON TABLE public.wallets IS 'Metadata about each wallet/account tracked in the ledger. Helps clarify IRS "account" classification for per-wallet basis tracking (required 2025+).';

-- Example wallet data (uncomment and customize for your setup):
-- INSERT INTO public.wallets (wallet_id, wallet_type, custody, description) VALUES
--     ('Strike', 'exchange', 'custodial', 'Strike account - custodial exchange wallet'),
--     ('River', 'exchange', 'custodial', 'River Financial account - custodial exchange wallet'),
--     ('ColdCard', 'hardware', 'self-custodied', 'Hardware wallet - cold storage'),
--     ('Phoenix', 'lightning', 'self-custodied', 'Phoenix Lightning wallet');


GRANT DELETE, UPDATE, SELECT, INSERT ON TABLE public.coins TO "bitcoin_accounting";
GRANT UPDATE, SELECT, INSERT ON TABLE public.ledger TO "bitcoin_accounting";
GRANT SELECT, USAGE ON SEQUENCE public.ledger_id_seq TO "bitcoin_accounting";
GRANT DELETE, UPDATE, SELECT, INSERT ON TABLE public.pair_price TO "bitcoin_accounting";
GRANT DELETE, UPDATE, SELECT, INSERT ON TABLE public.wallets TO "bitcoin_accounting";