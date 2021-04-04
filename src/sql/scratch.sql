
-- balances
select c.name "coin", get_balance(c.name) as balance from coins c 
where get_balance(c.name) is not null
order by balance desc;

-- num transactions
select c.name "coin", count(*) as num_transactions from coins c 
join ledger l on l.buy_curr = c."name" 
group by c.name;

-- add new coins
insert into coins (name, max_supply, circ_supply) values ('USDC', 10819032289, 10597903243);

-- add new price pair record
insert into pair_price (to_curr, price, from_curr, date) values ('ADA', 1.19,'USD', '2021-4-4');
insert into pair_price (to_curr, price, from_curr,date) values ('USD',177.65,'LTC','2021-03-24');

-- get raw trade data
select * from get_trades('XRP');

-- get cost in some currency from trade data 
select * from get_trade_cost('XRP','USD');


--SCRATCH

select * from ledger where trans_type = 'Trade' and (buy_curr = 'XRP' or sell_curr = 'XRP');
		
select trades.*,
'USD' as basis_curr,
case 
	when conv.price is not null then conv.price * trades.from_quantity
	else trades.price * trades.to_quantity
end as basis_cost,
conv.price as conversion_price,
conv.date as conversion_date
from get_trades('BTC') trades
left join pair_price conv on trades.from_curr != 'USD' and trades.from_curr = conv.from_curr  and conv.to_curr = 'USD' and date_trunc('day',trades.date) = conv."date"; 

select * from ledger where trans_type = 'Trade' and (sell_curr = 'BTC' or buy_curr = 'BTC') order by createddate;


