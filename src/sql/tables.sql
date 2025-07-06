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


GRANT DELETE, UPDATE, SELECT, INSERT ON TABLE public.coins TO "bitcoin_accounting";
GRANT UPDATE, SELECT, INSERT ON TABLE public.ledger TO "bitcoin_accounting";
GRANT SELECT, USAGE ON SEQUENCE public.ledger_id_seq TO "bitcoin_accounting";
GRANT DELETE, UPDATE, SELECT, INSERT ON TABLE public.pair_price TO "bitcoin_accounting";