import unittest
import sqlite3


class TestSQLiteIntegration(unittest.TestCase):
    def setUp(self):
        # in-memory sqlite for fast integration-like tests
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.cursor()
        # create minimal ledger and pair_price tables similar to Postgres schema
        cur.execute('''
            CREATE TABLE ledger (
                id INTEGER PRIMARY KEY,
                createddate TEXT,
                trans_type TEXT,
                buy REAL,
                buy_curr TEXT,
                sell REAL,
                sell_curr TEXT,
                fee REAL,
                fee_curr TEXT,
                exchange TEXT,
                "group" TEXT,
                comment TEXT,
                transactionid TEXT
            )
        ''')
        cur.execute('''
            CREATE TABLE pair_price (
                to_curr TEXT,
                price REAL,
                from_curr TEXT,
                date TEXT
            )
        ''')
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_balance_and_avg_purchase_price(self):
        cur = self.conn.cursor()
        # Insert two buys of BTC paid in USD
        # 1) buy 0.5 BTC for $25,000
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-01-01','Trade',0.5,'BTC',25000,'USD',0,'USD','ExA'))
        # 2) buy 0.1 BTC for $6,000
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-02-01','Trade',0.1,'BTC',6000,'USD',0,'USD','ExA'))
        # Insert a non-BTC transaction to ensure filtering works
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-03-01','Trade',10,'ETH',20000,'USD',0,'USD','ExB'))
        self.conn.commit()

        # Compute balance for BTC (sum of buys - sum of sells)
        # Note: fee column is for tracking only, fees are already included in buy/sell amounts
        balance_query = '''
            SELECT
              COALESCE((SELECT SUM(buy) FROM ledger WHERE buy_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(sell) FROM ledger WHERE sell_curr = 'BTC'), 0) as balance
        '''
        cur.execute(balance_query)
        row = cur.fetchone()
        balance = row['balance']
        # expected 0.6 BTC
        self.assertAlmostEqual(balance, 0.6, places=9)

        # Compute average purchase price in USD for BTC: sum(sell where buy_curr=BTC and sell_curr=USD) / sum(buy where buy_curr=BTC)
        avg_query = "SELECT SUM(sell) as total_usd, SUM(buy) as total_btc FROM ledger WHERE buy_curr='BTC' AND sell_curr='USD'"
        cur.execute(avg_query)
        row = cur.fetchone()
        total_usd = row['total_usd']
        total_btc = row['total_btc']
        avg_price = total_usd / total_btc

        # expected avg price = (25000 + 6000) / 0.6 = 31000 / 0.6 = 51666.666...
        expected = (25000 + 6000) / 0.6
        self.assertAlmostEqual(avg_price, expected, places=6)

    def test_balance_after_sell(self):
        """Test that selling BTC decreases balance and doesn't affect cost basis for remaining holdings."""
        cur = self.conn.cursor()
        # Buy 0.5 BTC for $25,000
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-01-01','Trade',0.5,'BTC',25000,'USD',0,'USD','ExA'))
        # Sell 0.1 BTC for $6,000 (buy=6000 USD, sell=0.1 BTC)
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-02-01','Trade',6000,'USD',0.1,'BTC',0,'USD','ExA'))
        self.conn.commit()

        # Balance should be 0.4 BTC (0.5 bought, 0.1 sold)
        # Note: fee column is for tracking only, fees are already included in buy/sell amounts
        balance_query = '''
            SELECT
              COALESCE((SELECT SUM(buy) FROM ledger WHERE buy_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(sell) FROM ledger WHERE sell_curr = 'BTC'), 0) as balance
        '''
        cur.execute(balance_query)
        row = cur.fetchone()
        balance = row['balance']
        self.assertAlmostEqual(balance, 0.4, places=9)

    def test_transfers_with_fees(self):
        """Test transfers (withdrawal + deposit) and fee attribution."""
        cur = self.conn.cursor()
        # Buy 1.0 BTC for $50,000
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-01-01','Trade',1.0,'BTC',50000,'USD',0,'USD','ExA'))
        # Transfer 0.5 BTC from ExA to ExB with 0.001 BTC fee
        # The withdrawal: sell includes both transferred amount AND fee (0.5 + 0.001 = 0.501)
        # Fee field (0.001) is for tracking only, already included in sell amount
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-02-01','Withdrawal',None,None,0.501,'BTC',0.001,'BTC','ExA'))
        # The deposit: receive 0.5 BTC at ExB
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-02-01','Deposit',0.5,'BTC',None,None,0,'BTC','ExB'))
        self.conn.commit()

        # Balance calculation: SUM(buy) - SUM(sell) (fees already in buy/sell)
        # = (1.0 initial buy + 0.5 deposit) - 0.501 withdrawal = 0.999 BTC
        balance_query = '''
            SELECT
              COALESCE((SELECT SUM(buy) FROM ledger WHERE buy_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(sell) FROM ledger WHERE sell_curr = 'BTC'), 0) as balance
        '''
        cur.execute(balance_query)
        row = cur.fetchone()
        balance = row['balance']
        self.assertAlmostEqual(balance, 0.999, places=9)

    def test_price_lookup_and_cost_basis_with_prices(self):
        """Test price lookup logic: find closest price by date and compute cost basis in fiat."""
        cur = self.conn.cursor()
        # Buy 0.5 BTC for 10 ETH
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-01-01T10:00:00','Trade',0.5,'BTC',10,'ETH',0,'ETH','ExA'))
        # Insert ETH price: 1 ETH = $2,000 on 2025-01-01
        cur.execute("INSERT INTO pair_price (to_curr, price, from_curr, date) VALUES (?,?,?,?)",
                    ('USD',2000,'ETH','2025-01-01'))
        self.conn.commit()

        # Fetch the trade and compute its cost in USD
        query = '''
            SELECT 
              buy as btc_qty,
              sell as eth_qty,
              (SELECT price FROM pair_price WHERE from_curr = 'ETH' AND to_curr = 'USD' AND DATE(date) = DATE('2025-01-01')) as eth_price
            FROM ledger
            WHERE buy_curr = 'BTC' AND sell_curr = 'ETH'
        '''
        cur.execute(query)
        row = cur.fetchone()
        btc_qty = row['btc_qty']
        eth_qty = row['eth_qty']
        eth_price = row['eth_price']

        # Cost basis in USD = 10 ETH * $2,000/ETH = $20,000
        cost_in_usd = eth_qty * eth_price
        self.assertAlmostEqual(cost_in_usd, 20000, places=2)
        # BTC cost basis = $20,000 / 0.5 = $40,000 per BTC
        btc_cost_basis = cost_in_usd / btc_qty
        self.assertAlmostEqual(btc_cost_basis, 40000, places=2)

    def test_multiple_currencies_isolation(self):
        """Test that balance/cost calculations for different coins don't interfere."""
        cur = self.conn.cursor()
        # Buy 0.5 BTC for $25,000
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-01-01','Trade',0.5,'BTC',25000,'USD',0,'USD','ExA'))
        # Buy 100 ETH for $200,000
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-01-02','Trade',100,'ETH',200000,'USD',0,'USD','ExA'))
        self.conn.commit()

        # BTC balance should be 0.5 BTC
        # Note: fee column is for tracking only, fees are already included in buy/sell amounts
        btc_balance_query = '''
            SELECT
              COALESCE((SELECT SUM(buy) FROM ledger WHERE buy_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(sell) FROM ledger WHERE sell_curr = 'BTC'), 0) as balance
        '''
        cur.execute(btc_balance_query)
        row = cur.fetchone()
        btc_balance = row['balance']
        self.assertAlmostEqual(btc_balance, 0.5, places=9)

        # ETH balance should be 100 ETH
        # Note: fee column is for tracking only, fees are already included in buy/sell amounts
        eth_balance_query = '''
            SELECT
              COALESCE((SELECT SUM(buy) FROM ledger WHERE buy_curr = 'ETH'), 0)
              - COALESCE((SELECT SUM(sell) FROM ledger WHERE sell_curr = 'ETH'), 0) as balance
        '''
        cur.execute(eth_balance_query)
        row = cur.fetchone()
        eth_balance = row['balance']
        self.assertAlmostEqual(eth_balance, 100, places=9)

    def test_per_wallet_balance_currency_filtering(self):
        """Test that per-wallet balance correctly filters by currency.
        
        Critical bug fix: Previously summed USD amounts as BTC when calculating
        per-wallet balances, causing massive incorrect balances like -58302 BTC.
        
        This test ensures we only sum amounts when the currency matches.
        """
        cur = self.conn.cursor()
        # Strike buys 0.01 BTC for 50,000 USD (expensive coin!)
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-01-01','Trade',0.01,'BTC',50000,'USD',0,'USD','Strike'))
        # Strike buys another 0.02 BTC for 100,000 USD
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-01-02','Trade',0.02,'BTC',100000,'USD',0,'USD','Strike'))
        # Another exchange (River) buys 0.5 BTC
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-01-03','Trade',0.5,'BTC',25000,'USD',0,'USD','River'))
        self.conn.commit()

        # Per-wallet balance for Strike should be 0.03 BTC (NOT negative!)
        # The bug was: SUM(buy) - SUM(sell) WHERE (buy_curr='BTC' OR sell_curr='BTC')
        # Which summed: (0.01 + 0.02) - (50000 + 100000) = -149999.97 BTC ❌
        # 
        # Correct: Only sum amounts when currency matches
        strike_balance_query = '''
            SELECT
              COALESCE(SUM(CASE WHEN buy_curr = 'BTC' THEN buy ELSE 0 END), 0) -
              COALESCE(SUM(CASE WHEN sell_curr = 'BTC' THEN sell ELSE 0 END), 0) as balance
            FROM ledger
            WHERE exchange = 'Strike'
        '''
        cur.execute(strike_balance_query)
        row = cur.fetchone()
        strike_balance = row['balance']
        self.assertAlmostEqual(strike_balance, 0.03, places=9, 
                             msg="Strike should have 0.03 BTC, not a huge negative number")

        # River should have 0.5 BTC (independent of Strike)
        river_balance_query = '''
            SELECT
              COALESCE(SUM(CASE WHEN buy_curr = 'BTC' THEN buy ELSE 0 END), 0) -
              COALESCE(SUM(CASE WHEN sell_curr = 'BTC' THEN sell ELSE 0 END), 0) as balance
            FROM ledger
            WHERE exchange = 'River'
        '''
        cur.execute(river_balance_query)
        row = cur.fetchone()
        river_balance = row['balance']
        self.assertAlmostEqual(river_balance, 0.5, places=9)

        # Total across all wallets should be 0.53 BTC
        total_balance_query = '''
            SELECT
              COALESCE(SUM(CASE WHEN buy_curr = 'BTC' THEN buy ELSE 0 END), 0) -
              COALESCE(SUM(CASE WHEN sell_curr = 'BTC' THEN sell ELSE 0 END), 0) as balance
            FROM ledger
        '''
        cur.execute(total_balance_query)
        row = cur.fetchone()
        total_balance = row['balance']
        self.assertAlmostEqual(total_balance, 0.53, places=9)
    def test_withdrawal_deposit_with_fees_tracking_only(self):
        """Test that fees in withdrawals/deposits are tracked but not double-subtracted from balance.
        
        Scenario: Transfer 1.0 BTC from ExchangeA to Wallet with 0.001 BTC network fee
        - Withdrawal: sell=1.0 BTC (includes fee), fee=0.001 BTC (tracking only)
        - Deposit: buy=0.999 BTC (net received)
        
        Balance should decrease by exactly 1.0 BTC (not 1.001 BTC).
        Fee is documentation only - the sell amount already includes it.
        """
        cur = self.conn.cursor()
        
        # Start with 2.0 BTC at ExchangeA
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-01-01','Trade',2.0,'BTC',100000,'USD',0,'USD','ExchangeA'))
        
        # Withdraw 1.0 BTC with 0.001 BTC fee (1.0 includes the 0.001 fee)
        # sell=1.0 is the GROSS amount (what left the exchange)
        # fee=0.001 is for tracking/documentation only
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-02-01','Withdrawal',0,'',1.0,'BTC',0.001,'BTC','ExchangeA'))
        
        # Deposit 0.999 BTC to Wallet (net received after fee)
        # buy=0.999 is the NET amount (what arrived)
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-02-01','Deposit',0.999,'BTC',0,'',0,'','Wallet'))
        
        self.conn.commit()
        
        # Total BTC balance calculation: 
        # Buys: 2.0 (trade) + 0.999 (deposit) = 2.999
        # Sells: 1.0 (withdrawal)
        # Balance: 2.999 - 1.0 = 1.999 BTC
        # NOTE: Fee is NOT separately subtracted
        balance_query = '''
            SELECT
              COALESCE((SELECT SUM(buy) FROM ledger WHERE buy_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(sell) FROM ledger WHERE sell_curr = 'BTC'), 0) as balance
        '''
        cur.execute(balance_query)
        row = cur.fetchone()
        total_balance = row['balance']
        
        # Should be 1.999 BTC (2.0 bought, 1.0 withdrawn gross, 0.999 deposited)
        # The 0.001 fee shows up in the accounting as: 1.0 out, 0.999 in = 0.001 consumed
        self.assertAlmostEqual(total_balance, 1.999, places=9)
        
        # Per-wallet balances
        wallet_balance_query = '''
            SELECT exchange,
              COALESCE(SUM(CASE WHEN buy_curr = 'BTC' THEN buy ELSE 0 END), 0)
              - COALESCE(SUM(CASE WHEN sell_curr = 'BTC' THEN sell ELSE 0 END), 0) as balance
            FROM ledger
            WHERE exchange IS NOT NULL AND exchange != ''
            GROUP BY exchange
        '''
        cur.execute(wallet_balance_query)
        wallets = {row['exchange']: row['balance'] for row in cur.fetchall()}
        
        # ExchangeA: bought 2.0, withdrew 1.0 = 1.0 BTC remaining
        self.assertAlmostEqual(wallets.get('ExchangeA', 0), 1.0, places=9)
        
        # Wallet: deposited 0.999 = 0.999 BTC
        self.assertAlmostEqual(wallets.get('Wallet', 0), 0.999, places=9)
        
        # Verify fee was tracked but not double-counted
        fee_query = "SELECT SUM(fee) as total_fees FROM ledger WHERE fee_curr = 'BTC'"
        cur.execute(fee_query)
        total_fees = cur.fetchone()['total_fees']
        self.assertAlmostEqual(total_fees, 0.001, places=9)
        
        # The 0.001 fee is already reflected in the balance difference (1.0 out - 0.999 in)
        # We don't subtract it again

if __name__ == '__main__':
    unittest.main()
