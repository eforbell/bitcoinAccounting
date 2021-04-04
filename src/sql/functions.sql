CREATE OR REPLACE FUNCTION public.get_balance(coin character varying, OUT balance numeric)
 RETURNS numeric
 LANGUAGE plpgsql
AS $function$
BEGIN
     balance := (select sum(total) from
		(SELECT sum(buy) total
		FROM public.ledger
		where buy_curr = coin
		UNION
		select -sum(sell) total
		from public.ledger
		where sell_curr = coin
		UNION
		select -sum(fee) total
		from public.ledger
		where fee_curr = coin
		) total);
END; $function$
;

CREATE OR REPLACE FUNCTION public.get_trades(coin character varying)
 RETURNS TABLE(date timestamp, quantity double precision, cost double precision, currency character varying)
 LANGUAGE plpgsql
AS $function$
begin
	return query 
	select
	l.createddate date, 
	case 
		when l.buy_curr = coin then l.buy
		when l.sell_curr = coin then -l.sell 
	end as quantity, 
	case 
		when l.buy_curr = coin then l.sell/l.buy
		when l.sell_curr = coin then l.buy/l.sell 
	end as basis, 
	case 
		when l.buy_curr = coin then l.sell_curr
		when l.sell_curr = coin then l.buy_curr
	end as basis 
	from ledger l
	where l.trans_type = 'Trade' and (l.buy_curr = coin or l.sell_curr = coin)
	order by createddate;
END; $function$
;

CREATE OR REPLACE FUNCTION public.get_trades(coin character varying)
 RETURNS TABLE(date timestamp without time zone, to_curr character varying, to_quantity double precision, price double precision, from_curr character varying, from_quantity double precision)
 LANGUAGE plpgsql
AS $function$
begin
	return query 
	select
	l.createddate date, 
	coin as to_curr,
	case 
		when l.buy_curr = coin then l.buy
		when l.sell_curr = coin then -l.sell 
	end as to_quantity, 
	case 
		when l.buy_curr = coin then l.sell/l.buy
		when l.sell_curr = coin then l.buy/l.sell 
	end as price, 
	case 
		when l.buy_curr = coin then l.sell_curr
		when l.sell_curr = coin then l.buy_curr
	end as from_curr,
	case 
		when l.buy_curr = coin then l.sell
		when l.sell_curr = coin then l.buy
	end as from_quantity 
	from ledger l
	where l.trans_type = 'Trade' and (l.buy_curr = coin or l.sell_curr = coin)
	order by createddate;
END; $function$
;

CREATE OR REPLACE FUNCTION public.get_trade_cost(coin character varying, cost_currency character varying default 'USD')
 RETURNS TABLE(date timestamp without time zone, curr character varying, quantity double precision, trade_curr character varying, trade_quantity double precision, cost_curr character varying, unit_cost double precision, total_cost double precision)
 LANGUAGE plpgsql
AS $function$
begin
	return query 
	select 
		trades.date as "date",
		coin as trade_curr,
		trades.to_quantity as quantity,
		trades.from_curr as trade_curr,
		trades.from_quantity as trade_quantity,
		cost_currency as cost_curr,
		case 
			when conv.price is not null then conv.price
			else trades.price
		end as unit_cost,
		case 
			when conv.price is not null then trades.from_quantity*conv.price*sign(trades.to_quantity)
			else trades.price * trades.to_quantity
		end as total_cost
		from get_trades(coin) trades
		left join pair_price conv on conv.from_curr = trades.from_curr and conv.to_curr = cost_currency and (date_trunc('day',trades.date) = date_trunc('day',conv."date"));
END; $function$
;



CREATE OR REPLACE FUNCTION public.get_price(from_coin character varying, to_coin character varying default 'USD', day date default now(), OUT out_price numeric)
 RETURNS numeric
 LANGUAGE plpgsql
AS $function$
BEGIN
     out_price := (select price from pair_price where from_curr = from_coin and to_curr = to_coin);
END; $function$
;