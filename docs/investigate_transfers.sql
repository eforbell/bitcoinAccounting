-- SQL queries to investigate unmatched transfers
-- Use these to review and understand your transfer history

-- 1. View all BTC withdrawals with details
SELECT 
    id,
    createddate,
    sell as amount,
    sell_curr as currency,
    fee,
    fee_curr,
    exchange as from_wallet,
    comment,
    transactionid
FROM ledger
WHERE trans_type = 'Withdrawal' 
    AND sell_curr = 'BTC'
ORDER BY createddate DESC;

-- 2. View all BTC deposits with details
SELECT 
    id,
    createddate,
    buy as amount,
    buy_curr as currency,
    exchange as to_wallet,
    comment,
    transactionid
FROM ledger
WHERE trans_type = 'Deposit'
    AND buy_curr = 'BTC'
ORDER BY createddate DESC;

-- 3. Find potential matching pairs (same date, similar amounts)
WITH withdrawals AS (
    SELECT 
        id as w_id,
        createddate as w_date,
        sell as w_amount,
        fee as w_fee,
        exchange as w_exchange,
        comment as w_comment
    FROM ledger
    WHERE trans_type = 'Withdrawal' AND sell_curr = 'BTC'
),
deposits AS (
    SELECT 
        id as d_id,
        createddate as d_date,
        buy as d_amount,
        exchange as d_exchange,
        comment as d_comment
    FROM ledger
    WHERE trans_type = 'Deposit' AND buy_curr = 'BTC'
)
SELECT 
    w.w_date::date as date,
    w.w_exchange as from_wallet,
    w.w_amount as withdrawn,
    w.w_fee as fee,
    d.d_exchange as to_wallet,
    d.d_amount as deposited,
    (w.w_amount - d.d_amount) as difference,
    w.w_id,
    d.d_id
FROM withdrawals w
JOIN deposits d 
    ON d.d_date::date = w.w_date::date
    AND d.d_exchange != w.w_exchange
    AND ABS(d.d_amount - w.w_amount) < 0.01  -- Within 0.01 BTC
ORDER BY w.w_date DESC;

-- 4. Find large withdrawals without obvious matches (> 0.1 BTC)
SELECT 
    w.createddate,
    w.exchange as from_wallet,
    w.sell as amount,
    w.fee,
    w.comment,
    w.id,
    -- Check if there's a deposit within 7 days
    (SELECT COUNT(*) 
     FROM ledger d 
     WHERE d.trans_type = 'Deposit' 
         AND d.buy_curr = 'BTC'
         AND d.createddate BETWEEN w.createddate - INTERVAL '1 day' 
             AND w.createddate + INTERVAL '7 days'
         AND ABS(d.buy - w.sell) < 0.01
    ) as potential_matches
FROM ledger w
WHERE w.trans_type = 'Withdrawal' 
    AND w.sell_curr = 'BTC'
    AND w.sell > 0.1  -- Large amounts only
ORDER BY w.createddate DESC;

-- 5. View transfer pairs grouped by date (to spot patterns)
SELECT 
    createddate::date as date,
    trans_type,
    exchange as wallet,
    COALESCE(buy, -sell) as net_amount,
    fee,
    comment
FROM ledger
WHERE (trans_type = 'Withdrawal' OR trans_type = 'Deposit')
    AND (buy_curr = 'BTC' OR sell_curr = 'BTC')
ORDER BY createddate::date DESC, createddate;

-- 6. Identify specific unmatched withdrawals (customize dates as needed)
SELECT 
    'WITHDRAWAL' as type,
    id,
    createddate,
    exchange,
    sell as amount,
    fee,
    comment
FROM ledger
WHERE trans_type = 'Withdrawal' 
    AND sell_curr = 'BTC'
    AND id NOT IN (
        -- Withdrawals that have matching deposits
        SELECT DISTINCT w.id
        FROM ledger w
        JOIN ledger d ON d.trans_type = 'Deposit'
            AND d.buy_curr = 'BTC'
            AND d.createddate BETWEEN w.createddate - INTERVAL '1 day' 
                AND w.createddate + INTERVAL '7 days'
            AND ABS(d.buy - w.sell) < 0.02
            AND d.exchange != w.exchange
        WHERE w.trans_type = 'Withdrawal' AND w.sell_curr = 'BTC'
    )
ORDER BY createddate DESC;
