
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
insert into pair_price (to_curr, price, from_curr,date) values ('USD',52774.26,'BTC','2021-03-24');
insert into pair_price (to_curr, price, from_curr,date) values ('USD',2.4582,'NEXO','2021-02-21');

insert into pair_price (to_curr, price, from_curr,date) values ('USD',4.82,'VBNB','2021-03-02');
insert into pair_price (to_curr, price, from_curr,date) values ('USD',4.63,'VBNB','2021-03-04');
insert into pair_price (to_curr, price, from_curr,date) values ('VAI',0.9916,'USD','2021-02-27');

2021-02-21 10:59:02
2021-02-21 11:01:30
2021-03-12 17:15:54
2021-03-25 21:09:51
2021-03-25 21:37:47


insert into pair_price (to_curr, price, from_curr,date) values ('USD',286.386,'BNB','2021-02-21');
insert into pair_price (to_curr, price, from_curr,date) values ('USD',266.844,'BNB','2021-03-12');
insert into pair_price (to_curr, price, from_curr,date) values ('USD',276.017,'BNB','2021-03-25');

select * from pair_price where from_curr = 'NEXO';

-- get raw trade data
select * from get_balance('NEXO');

-- get cost in some currency from trade data 
select * from get_trades('NEXO');
select * from get_trade_cost('XRP','USD');

select get_avg_purchase_price('NEXO', 'USD'); 

select sum(quantity) unrealized_quantity, sum(quantity)*get_avg_purchase_price('NEXO','USD')-sum(total_cost) realized_gains from get_trade_cost('NEXO','USD');
--2.4331
--2.46998
--SCRATCH

select * from ledger where trans_type = 'Trade' and (buy_curr = 'NEXO' or sell_curr = 'NEXO') order by createddate;
		
select trades.*,
'USD' as basis_curr,
case 
	when conv.price is not null then conv.price * trades.from_quantity
	else trades.price * trades.to_quantity
end as basis_cost,
conv.price as conversion_price,
conv.date as conversion_date
from get_trades('NEXO') trades
left join pair_price conv on trades.from_curr != 'USD' and trades.from_curr = conv.from_curr  and conv.to_curr = 'USD' and date_trunc('day',trades.date) = conv."date"; 

select * from ledger where (sell_curr = 'NEXO' or buy_curr = 'NEXO') order by createddate;

insert into ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, exchange, "group") values ('2021-03-25 21:09:51','Trade',40,'NEXO',0.4146296,'BNB','Ledger','Binance DEX');

select get_price('USD','XRP','2021-1-21');


select * from pair_price pp where from_curr = 'NEXO';
select 
	trade_cost.*,
    case 
    	when trade_curr = 'USD' then unit_cost
 		else get_price(curr, 'USD', date_trunc('day',trade_cost."date"))
 	end as trade_price
 	from get_trade_cost('NEXO', 'USD') trade_cost
 where trade_cost.quantity > 0; -- purchase trade only
     
