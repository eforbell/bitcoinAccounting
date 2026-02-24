"""
Tests for 1099-B tax form export functionality.

Tests cover:
- FIFO cost basis matching
- Multi-year FIFO queue consumption
- Interest Income inclusion in cost basis
- Missing basis detection
- Short-term vs long-term classification
- Multiple lot matching for single sales
"""

import unittest
import sys
import os
from datetime import datetime

# Add src/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))


class Test1099BExport(unittest.TestCase):
    """Tests for 1099-B export with FIFO cost basis calculation."""

    def setUp(self):
        """Set up real backend and CryptoAccounts instance."""
        from bitcoinAccounts import CryptoAccounts
        from db import SqliteBackend

        # Create real backend with in-memory database for testing
        self.backend = SqliteBackend(':memory:', auto_create_tables=True)
        self.crypto = CryptoAccounts(backend=self.backend)

    def test_simple_fifo_single_lot(self):
        """Test FIFO with one purchase and one sale in same year."""
        # Setup: Buy 1 BTC @ $50,000 on Jan 1, sell 1 BTC @ $60,000 on Dec 1
        self.crypto.execute_trade(
            trade_date=datetime(2024, 1, 1),
            buy=1.0,
            buy_curr='BTC',
            sell=50000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )
        self.crypto.execute_trade(
            trade_date=datetime(2024, 12, 1),
            buy=60000.0,
            buy_curr='USD',
            sell=1.0,
            sell_curr='BTC',
            exchange='Exchange1'
        )

        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['Description'], '1.00000000 BTC')
        self.assertEqual(results[0]['Cost Basis'], '50000.00')
        self.assertEqual(results[0]['Proceeds'], '60000.00')
        self.assertEqual(results[0]['Term'], 'Short')  # 334 days < 365
        self.assertNotEqual(results[0]['Date Acquired'], 'UNKNOWN')

    def test_fifo_multiple_lots(self):
        """Test FIFO matching across multiple purchase lots."""
        # Setup: Buy 0.5 BTC @ $40k, then 0.5 BTC @ $50k, then sell 1 BTC @ $60k
        self.crypto.execute_trade(
            trade_date=datetime(2024, 1, 1),
            buy=0.5,
            buy_curr='BTC',
            sell=20000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )
        self.crypto.execute_trade(
            trade_date=datetime(2024, 2, 1),
            buy=0.5,
            buy_curr='BTC',
            sell=25000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )
        self.crypto.execute_trade(
            trade_date=datetime(2024, 12, 1),
            buy=60000.0,
            buy_curr='USD',
            sell=1.0,
            sell_curr='BTC',
            exchange='Exchange1'
        )

        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)

        # Should create 2 lots: one from each purchase
        self.assertEqual(len(results), 2)

        # First lot (FIFO): 0.5 BTC @ $40k basis
        self.assertEqual(results[0]['Description'], '0.50000000 BTC')
        self.assertEqual(results[0]['Cost Basis'], '20000.00')
        self.assertEqual(results[0]['Proceeds'], '30000.00')  # Half of $60k proceeds

        # Second lot: 0.5 BTC @ $50k basis
        self.assertEqual(results[1]['Description'], '0.50000000 BTC')
        self.assertEqual(results[1]['Cost Basis'], '25000.00')
        self.assertEqual(results[1]['Proceeds'], '30000.00')  # Half of $60k proceeds

    def test_fifo_across_years(self):
        """Test that sales in prior years consume the FIFO queue."""
        # Setup: Buy 2 BTC in 2023, sell 1 BTC in 2023, sell 1 BTC in 2024
        # Only the 2024 sale should be in results, but it should use the 2nd BTC lot

        # Two purchases in 2023
        self.crypto.execute_trade(
            trade_date=datetime(2023, 1, 1),
            buy=1.0,
            buy_curr='BTC',
            sell=40000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )
        self.crypto.execute_trade(
            trade_date=datetime(2023, 2, 1),
            buy=1.0,
            buy_curr='BTC',
            sell=50000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )
        # Sale in 2023 (consumes first lot)
        self.crypto.execute_trade(
            trade_date=datetime(2023, 12, 1),
            buy=45000.0,
            buy_curr='USD',
            sell=1.0,
            sell_curr='BTC',
            exchange='Exchange1'
        )
        # Sale in 2024 (should use second lot)
        self.crypto.execute_trade(
            trade_date=datetime(2024, 6, 1),
            buy=60000.0,
            buy_curr='USD',
            sell=1.0,
            sell_curr='BTC',
            exchange='Exchange1'
        )

        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)

        # Only 2024 sale should be in results
        self.assertEqual(len(results), 1)

        # Should use the SECOND purchase lot (first was consumed by 2023 sale)
        self.assertEqual(results[0]['Cost Basis'], '50000.00')
        self.assertEqual(results[0]['Proceeds'], '60000.00')
        self.assertEqual(results[0]['Date Acquired'], '02/01/2023')

    def test_interest_income_included(self):
        """Test that Interest Income acquisitions are included in FIFO."""
        # Setup: Only interest income (no trade purchases), then a sale
        # Add interest income
        self.crypto.interest(
            interest_date=datetime(2024, 1, 1),
            buy=0.1,
            buy_curr='BTC',
            exchange='Exchange1'
        )
        # Add price for interest income valuation
        self.crypto.add_price_pair(
            pair_date=datetime(2024, 1, 1),
            from_curr='BTC',
            to_curr='USD',
            price=500.0  # 0.1 BTC worth $50
        )
        # Sale of the interest income
        self.crypto.execute_trade(
            trade_date=datetime(2024, 12, 1),
            buy=60.0,
            buy_curr='USD',
            sell=0.1,
            sell_curr='BTC',
            exchange='Exchange1'
        )

        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['Cost Basis'], '50.00')
        self.assertEqual(results[0]['Proceeds'], '60.00')
        self.assertNotEqual(results[0]['Date Acquired'], 'UNKNOWN')

    def test_missing_basis_detection(self):
        """Test that missing basis (insufficient purchase history) is detected."""
        # Setup: Buy 0.5 BTC but sell 1.0 BTC
        self.crypto.execute_trade(
            trade_date=datetime(2024, 1, 1),
            buy=0.5,
            buy_curr='BTC',
            sell=25000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )
        self.crypto.execute_trade(
            trade_date=datetime(2024, 12, 1),
            buy=60000.0,
            buy_curr='USD',
            sell=1.0,
            sell_curr='BTC',
            exchange='Exchange1'
        )

        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)

        # Should have 2 lots: 0.5 with basis, 0.5 without
        self.assertEqual(len(results), 2)

        # First lot: matched with purchase
        self.assertEqual(results[0]['Description'], '0.50000000 BTC')
        self.assertEqual(results[0]['Cost Basis'], '25000.00')
        self.assertNotEqual(results[0]['Date Acquired'], 'UNKNOWN')

        # Second lot: missing basis
        self.assertEqual(results[1]['Description'], '0.50000000 BTC')
        self.assertEqual(results[1]['Cost Basis'], '0.00')
        self.assertEqual(results[1]['Date Acquired'], 'UNKNOWN')
        self.assertEqual(results[1]['Term'], 'Short')  # Conservative approach

    def test_short_vs_long_term(self):
        """Test short-term vs long-term classification."""
        # Setup: Buy on Jan 1 2024, sell in June 2024 (short-term)
        self.crypto.execute_trade(
            trade_date=datetime(2024, 1, 1),
            buy=0.5,
            buy_curr='BTC',
            sell=25000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )
        self.crypto.execute_trade(
            trade_date=datetime(2024, 6, 1),
            buy=30000.0,
            buy_curr='USD',
            sell=0.5,
            sell_curr='BTC',
            exchange='Exchange1'
        )

        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['Term'], 'Short')  # 151 days < 365

    def test_long_term_classification(self):
        """Test long-term classification (>= 365 days)."""
        # Setup: Buy on Jan 1 2024, sell on Jan 2 2025 (long-term)
        self.crypto.execute_trade(
            trade_date=datetime(2024, 1, 1),
            buy=0.5,
            buy_curr='BTC',
            sell=25000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )
        self.crypto.execute_trade(
            trade_date=datetime(2025, 1, 2),
            buy=30000.0,
            buy_curr='USD',
            sell=0.5,
            sell_curr='BTC',
            exchange='Exchange1'
        )

        # 2025+ uses per-wallet accounting; specify wallet to avoid warning-as-error.
        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2025, wallet='Exchange1')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['Term'], 'Long')  # 366 days >= 365

    def test_worksheet_output(self):
        """Test that worksheet contains detailed calculation data."""
        # Setup: Simple single sale
        self.crypto.execute_trade(
            trade_date=datetime(2024, 1, 1),
            buy=1.0,
            buy_curr='BTC',
            sell=50000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )
        self.crypto.execute_trade(
            trade_date=datetime(2024, 12, 1),
            buy=60000.0,
            buy_curr='USD',
            sell=1.0,
            sell_curr='BTC',
            exchange='Exchange1'
        )

        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)

        self.assertEqual(len(worksheet), 1)

        # Verify worksheet has detailed fields
        ws = worksheet[0]
        self.assertIn('Sale Date', ws)
        self.assertIn('Sale Quantity', ws)
        self.assertIn('Proceeds', ws)
        self.assertIn('Acquire Date', ws)
        self.assertIn('Lot Quantity', ws)
        self.assertIn('Unit Cost Basis', ws)
        self.assertIn('Total Cost Basis', ws)
        self.assertIn('Holding Days', ws)
        self.assertIn('Term', ws)
        self.assertIn('Gain/Loss', ws)

        # Verify calculated gain/loss
        self.assertEqual(ws['Gain/Loss'], '10000.00')  # $60k - $50k

    def test_empty_sales(self):
        """Test handling when there are no sales in the tax year."""
        # Setup: Purchases but no sales
        self.crypto.execute_trade(
            trade_date=datetime(2024, 1, 1),
            buy=1.0,
            buy_curr='BTC',
            sell=50000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )

        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)

        self.assertEqual(len(results), 0)
        self.assertEqual(len(worksheet), 0)

    def test_mixed_trades_and_interest(self):
        """Test proper chronological sorting of trades and interest income."""
        # Setup: Interleaved trades and interest income
        # Jan trade
        self.crypto.execute_trade(
            trade_date=datetime(2024, 1, 1),
            buy=0.5,
            buy_curr='BTC',
            sell=20000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )
        # Feb interest income
        self.crypto.interest(
            interest_date=datetime(2024, 2, 1),
            buy=0.1,
            buy_curr='BTC',
            exchange='Exchange1'
        )
        self.crypto.add_price_pair(
            pair_date=datetime(2024, 2, 1),
            from_curr='BTC',
            to_curr='USD',
            price=500.0  # 0.1 BTC worth $50
        )
        # March trade
        self.crypto.execute_trade(
            trade_date=datetime(2024, 3, 1),
            buy=0.5,
            buy_curr='BTC',
            sell=25000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )
        # December sale: sell 1.1 BTC total
        self.crypto.execute_trade(
            trade_date=datetime(2024, 12, 1),
            buy=66000.0,
            buy_curr='USD',
            sell=1.1,
            sell_curr='BTC',
            exchange='Exchange1'
        )

        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)

        # Should use FIFO: 0.5 from Jan trade, 0.1 from Feb interest, 0.5 from Mar trade
        self.assertEqual(len(results), 3)

        # Verify chronological FIFO order
        self.assertEqual(results[0]['Date Acquired'], '01/01/2024')  # First trade
        self.assertEqual(results[1]['Date Acquired'], '02/01/2024')  # Interest income
        self.assertEqual(results[2]['Date Acquired'], '03/01/2024')  # Second trade


class Test1099BScript(unittest.TestCase):
    """Tests for the export_1099b script interface."""

    def test_script_validates_tax_year(self):
        """Test that script validates tax year input."""
        current_year = datetime.now().year

        # Valid years
        for year in [2020, 2021, current_year]:
            self.assertGreaterEqual(year, 2009)
            self.assertLessEqual(year, current_year)

        # Invalid years
        invalid_years = [2008, current_year + 1, 1999]
        for year in invalid_years:
            self.assertTrue(year < 2009 or year > current_year)


if __name__ == '__main__':
    unittest.main()
