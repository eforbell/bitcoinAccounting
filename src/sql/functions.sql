CREATE OR REPLACE FUNCTION public.get_balance(coin character varying, OUT balance numeric)
 RETURNS numeric
 LANGUAGE plpgsql
AS $function$
BEGIN
     balance := (select sum(total) from
		(SELECT sum(buy) total
		FROM public.ledger
		where buy_curr = coin and trans_type != 'Stake'
		UNION
		select -sum(sell) total
		from public.ledger
		where sell_curr = coin 
		) total);
END; $function$
;

CREATE OR REPLACE FUNCTION public.get_sum_of_all_transfers(coin character varying, OUT balance numeric)
 RETURNS numeric
 LANGUAGE plpgsql
AS $function$
BEGIN
     balance :=     
(SELECT sum(total) from 
(select sum(buy) total
		FROM public.ledger
		where buy_curr = coin and (trans_type = 'Withdrawal' or trans_type = 'Deposit')
		UNION
select -sum(sell) total
		from public.ledger
		where sell_curr = coin and (trans_type = 'Withdrawal' or trans_type = 'Deposit')
		--UNION
--select -sum(fee) total
--		from public.ledger
--		where fee_curr = coin and (trans_type = 'Withdrawal' or trans_type = 'Deposit')
) transfers);
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

CREATE OR REPLACE FUNCTION public.get_interest_income(coin character varying, cost_currency character varying DEFAULT 'USD'::character varying)
 RETURNS TABLE(date timestamp without time zone, to_curr character varying, to_quantity double precision, cost_curr character varying, unit_cost double precision, total_cost double precision, cost_curr_quote_date timestamp without time zone)
 LANGUAGE plpgsql
AS $function$
begin
	return query 
	select
	l.createddate date, 
	coin as to_curr,
	l.buy as to_quantity, 
	cost_currency as cost_curr,
	case 
		when conv.price is not null then conv.price
		else null
	end as unit_cost,
	case 
		when conv.price is not null then l.buy*conv.price
		else null
	end as total_cost,
	case
		when conv.price is not null then conv.date 
		else null 
	end as cost_curr_quote_date
	from ledger l
	left join pair_price conv on conv.from_curr = 
				l.buy_curr and 
				conv.to_curr = cost_currency and
				(
				--find closest matching price quote
				(
					date_trunc('minute',l.createddate) = date_trunc('minute',conv."date") 
					or
					date_trunc('hour',l.createddate) = date_trunc('hour',conv."date") 
					or
					date_trunc('day',l.createddate) = date_trunc('day',conv."date") 
					
				)
				or 
					(conv.price is not null and conv.date is null)
				)
	where l.trans_type in ('Interest Income') and (l.buy_curr = coin or l.sell_curr = coin)
	order by createddate;
END; $function$
;

CREATE OR REPLACE FUNCTION public.get_trade_cost(coin character varying, cost_currency character varying DEFAULT 'USD'::character varying)
 RETURNS TABLE(date timestamp without time zone, curr character varying, quantity double precision, trade_curr character varying, trade_quantity double precision, cost_curr character varying, unit_cost double precision, total_cost double precision, cost_curr_quote_date timestamp without time zone)
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
			when conv.price is not null then trades.from_quantity*conv.price*sign(trades.to_quantity)/trades.to_quantity
			when trades.from_curr = cost_currency then trades.price
			else null
		end as unit_cost,
		case
			when conv.price is not null then trades.from_quantity*conv.price*sign(trades.to_quantity)
			when trades.from_curr = cost_currency then trades.price * trades.to_quantity
			else null
		end as total_cost,
		case
			when conv.price is not null then conv.date
			when trades.from_curr = cost_currency then trades.date
			else null
		end as cost_curr_quote_date
		from get_trades(coin) trades
		left join pair_price conv on conv.from_curr =
				trades.from_curr and
				conv.to_curr = cost_currency and get_price(conv.from_curr, cost_currency)
				--find closest matching price quote
					date_trunc('year',trades."date") = date_trunc('year',conv."date")
					and
					date_trunc('month',trades."date") = date_trunc('month',conv."date")
					and
					date_trunc('day',trades."date") = date_trunc('day',conv."date");
END; $function$
;

CREATE OR REPLACE FUNCTION public.get_trade_cost_new(coin character varying, cost_currency character varying DEFAULT 'USD'::character varying)
 RETURNS TABLE(date timestamp without time zone, curr character varying, quantity double precision, trade_curr character varying, trade_quantity double precision, cost_curr character varying, unit_cost double precision, total_cost double precision, cost_curr_quote_date timestamp without time zone)
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
			when trades.from_curr = cost_currency then trades.price
			else trades.from_quantity * get_price(trades.from_curr, cost_currency,trades.date)*sign(trades.to_quantity)/trades.to_quantity
		end as unit_cost,
		case
			when trades.from_curr = cost_currency then trades.price * trades.to_quantity
			else trades.from_quantity * get_price(trades.from_curr, cost_currency,trades.date)*sign(trades.to_quantity)
		end as total_cost,
		case
			when trades.from_curr = cost_currency then trades.date
			else get_price_date(trades.from_curr, cost_currency, trades.date)
		end as cost_curr_quote_date
		from get_trades(coin) trades;
END; $function$
;




CREATE OR REPLACE FUNCTION public.get_price(from_coin character varying, to_coin character varying DEFAULT 'USD'::character varying, price_date timestamp without time zone DEFAULT now(), OUT out_price numeric)
 RETURNS numeric
 LANGUAGE plpgsql
AS $function$
BEGIN
     out_price := (


     select price from pair_price
    	where from_curr = from_coin and to_curr = to_coin and
    	extract('year' from date) = extract('year' from price_date)
		and
		extract('month' from date) = extract('month' from price_date)
		and
		extract('day' from date) = extract('day' from price_date)
     order by
     abs( (DATE_PART('day', date - price_date) * 24 +
               DATE_PART('hour', date - price_date)) * 60 +
               DATE_PART('minute', date - price_date)) limit 1);
END; $function$
;

CREATE OR REPLACE FUNCTION public.get_price_date(from_coin character varying, to_coin character varying DEFAULT 'USD'::character varying, price_date timestamp DEFAULT now(), OUT out_price_date timestamp)
 RETURNS timestamp
 LANGUAGE plpgsql
AS $function$
BEGIN
     out_price_date := (

     select date from pair_price
    	where from_curr = from_coin and to_curr = to_coin and
    	extract('year' from date) = extract('year' from price_date)
		and
		extract('month' from date) = extract('month' from price_date)
		and
		extract('day' from date) = extract('day' from price_date)
     order by
     abs( (DATE_PART('day', date - price_date) * 24 +
               DATE_PART('hour', date - price_date)) * 60 +
               DATE_PART('minute', date - price_date)) limit 1);
END; $function$
;

CREATE OR REPLACE FUNCTION public.get_avg_purchase_price(curr character varying, cost_currency character varying DEFAULT 'USD'::character varying, OUT out_price double precision)
 RETURNS double precision
 LANGUAGE plpgsql
AS $function$
BEGIN
     out_price :=
     (select sum(
        case
        	when trade_curr = cost_currency then unit_cost * quantity
     		else get_price(trade_cost.curr, cost_currency, date_trunc('day',"date")) * quantity
     	end
     ) / sum(quantity)
     	from get_trade_cost(curr, cost_currency) trade_cost
     where quantity > 0 -- purchase trade only
     );
END; $function$
;

CREATE OR REPLACE FUNCTION public.get_dividend_cost(coin character varying, cost_currency character varying DEFAULT 'USD'::character varying)
 RETURNS TABLE(date timestamp without time zone, curr character varying, quantity double precision, cost_curr character varying, unit_cost numeric, total_cost double precision, cost_curr_quote_date timestamp without time zone)
 LANGUAGE plpgsql
AS $function$
begin
	return query
	select
		dividends.date as "date",
		coin as dividend_curr,
		dividends.to_quantity as quantity,
		cost_currency as cost_curr,
		get_price(coin, cost_currency,dividends.date) as unit_cost,
		dividends.to_quantity * get_price(coin, cost_currency,dividends.date) as total_cost,
		get_price_date(coin, cost_currency,dividends.date) as cost_curr_quote_date
		from (select createddate as "date", buy as to_quantity, buy_curr as to_curr from ledger l
		where l.trans_type in ('Interest Income') and l.buy_curr = coin
		order by createddate) as dividends;
END; $function$
;

CREATE OR REPLACE FUNCTION public.get_avg_purchase_price_new(curr character varying, cost_currency character varying DEFAULT 'USD'::character varying, OUT out_price double precision)
 RETURNS double precision
 LANGUAGE plpgsql
AS $function$
BEGIN
     out_price := 
     (select sum(unit_cost*quantity)/sum(quantity)
        from get_trade_cost_new(curr, cost_currency)
		where quantity > 0 -- purchase trade only
     );
END; $function$
;
