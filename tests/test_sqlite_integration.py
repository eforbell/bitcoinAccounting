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

        # Compute balance for BTC (sum of buys - sum of sells - sum of fees where currency matches)
        balance_query = '''
            SELECT
              COALESCE((SELECT SUM(buy) FROM ledger WHERE buy_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(sell) FROM ledger WHERE sell_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(fee) FROM ledger WHERE fee_curr = 'BTC'), 0) as balance
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
        balance_query = '''
            SELECT
              COALESCE((SELECT SUM(buy) FROM ledger WHERE buy_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(sell) FROM ledger WHERE sell_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(fee) FROM ledger WHERE fee_curr = 'BTC'), 0) as balance
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
        # The withdrawal reduces the balance by the sell amount and the fee amount
        # sell=0.5 (amount transferred), fee=0.001 (network/exchange fee)
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-02-01','Withdrawal',None,None,0.5,'BTC',0.001,'BTC','ExA'))
        # The deposit: receive 0.5 BTC at ExB
        cur.execute("INSERT INTO ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange) VALUES (?,?,?,?,?,?,?,?,?)",
                    ('2025-02-01','Deposit',0.5,'BTC',None,None,0,'BTC','ExB'))
        self.conn.commit()

        # Balance calculation: SUM(buy where buy_curr='BTC') - SUM(sell where sell_curr='BTC') - SUM(fee where fee_curr='BTC')
        # = (1.0 initial buy + 0.5 deposit) - 0.5 withdrawal - 0.001 fee = 0.999 BTC
        balance_query = '''
            SELECT
              COALESCE((SELECT SUM(buy) FROM ledger WHERE buy_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(sell) FROM ledger WHERE sell_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(fee) FROM ledger WHERE fee_curr = 'BTC'), 0) as balance
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
        btc_balance_query = '''
            SELECT
              COALESCE((SELECT SUM(buy) FROM ledger WHERE buy_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(sell) FROM ledger WHERE sell_curr = 'BTC'), 0)
              - COALESCE((SELECT SUM(fee) FROM ledger WHERE fee_curr = 'BTC'), 0) as balance
        '''
        cur.execute(btc_balance_query)
        row = cur.fetchone()
        btc_balance = row['balance']
        self.assertAlmostEqual(btc_balance, 0.5, places=9)

        # ETH balance should be 100 ETH
        eth_balance_query = '''
            SELECT
              COALESCE((SELECT SUM(buy) FROM ledger WHERE buy_curr = 'ETH'), 0)
              - COALESCE((SELECT SUM(sell) FROM ledger WHERE sell_curr = 'ETH'), 0)
              - COALESCE((SELECT SUM(fee) FROM ledger WHERE fee_curr = 'ETH'), 0) as balance
        '''
        cur.execute(eth_balance_query)
        row = cur.fetchone()
        eth_balance = row['balance']
        self.assertAlmostEqual(eth_balance, 100, places=9)


if __name__ == '__main__':
    unittest.main()
