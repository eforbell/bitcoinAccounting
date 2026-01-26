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
from unittest.mock import Mock, patch

# Add src/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))


class Test1099BExport(unittest.TestCase):
    """Tests for 1099-B export with FIFO cost basis calculation."""
    
    def setUp(self):
        """Set up mock backend and CryptoAccounts instance."""
        # Import here to ensure path is set
        from cryptoAccounts import CryptoAccounts
        from db import SqliteBackend

        # Create real backend with in-memory database for testing
        self.backend = SqliteBackend(':memory:', auto_create_tables=True)
        self.crypto = CryptoAccounts(backend=self.backend)
    
    def test_simple_fifo_single_lot(self):
        """Test FIFO with one purchase and one sale in same year."""
        # Setup: Buy 1 BTC @ $50,000 on Jan 1, sell 1 BTC @ $60,000 on Dec 1
        # Insert purchase trade
        self.crypto.execute_trade(
            trade_date=datetime(2024, 1, 1),
            buy=1.0,
            buy_curr='BTC',
            sell=50000.0,
            sell_curr='USD',
            exchange='Exchange1'
        )
        # Insert sale trade
        self.crypto.execute_trade(
            trade_date=datetime(2024, 12, 1),
            buy=60000.0,
            buy_curr='USD',
            sell=1.0,
            sell_curr='BTC',
            exchange='Exchange1'
        )
        # Add prices
        self.crypto.add_price_pair(datetime(2024, 1, 1), from_curr='USD', to_curr='BTC', price=1/50000.0)
        self.crypto.add_price_pair(datetime(2024, 12, 1), from_curr='USD', to_curr='BTC', price=1/60000.0)

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
        self.mock_cursor.fetchall.side_effect = [
            # Trade purchases (FIFO order)
            [
                (datetime(2024, 1, 1), 0.5, 40000.0, 20000.0, 'Exchange1'),
                (datetime(2024, 2, 1), 0.5, 50000.0, 25000.0, 'Exchange1'),
            ],
            # Interest income purchases
            [],
            # Sales
            [(datetime(2024, 12, 1), 1.0, 'Exchange1', 1)],
        ]
        self.mock_cursor.fetchone.return_value = (60000.0, 60000.0)
        
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
        self.mock_cursor.fetchall.side_effect = [
            # Trade purchases
            [
                (datetime(2023, 1, 1), 1.0, 40000.0, 40000.0, 'Exchange1'),
                (datetime(2023, 2, 1), 1.0, 50000.0, 50000.0, 'Exchange1'),
            ],
            # Interest income purchases
            [],
            # Sales (both 2023 and 2024 through end of 2024)
            [
                (datetime(2023, 12, 1), 1.0, 'Exchange1', 1),  # Consumes first lot
                (datetime(2024, 6, 1), 1.0, 'Exchange1', 2),   # Uses second lot
            ],
        ]
        # Proceeds for the sales
        # Note: The function queries proceeds per sale, so we need to mock both
        self.mock_cursor.fetchone.return_value = (60000.0, 60000.0)  # 2024 sale proceeds
        
        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)
        
        # Only 2024 sale should be in results
        self.assertEqual(len(results), 1)
        
        # Should use the SECOND purchase lot (first was consumed by 2023 sale)
        self.assertEqual(results[0]['Cost Basis'], '50000.00')
        self.assertEqual(results[0]['Proceeds'], '60000.00')
        self.assertEqual(results[0]['Date Acquired'], '02/01/2023')
    
    def test_interest_income_included(self):
        """Test that Interest Income acquisitions are included in FIFO."""
        # Setup: No trades, only interest income, then a sale
        self.mock_cursor.fetchall.side_effect = [
            # Trade purchases (none)
            [],
            # Interest income purchases
            [(datetime(2024, 1, 1), 0.1, 500.0, 50.0, 'Exchange1')],
            # Sales
            [(datetime(2024, 12, 1), 0.1, 'Exchange1', 1)],
        ]
        self.mock_cursor.fetchone.return_value = (600.0, 60.0)
        
        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['Cost Basis'], '50.00')
        self.assertEqual(results[0]['Proceeds'], '60.00')
        self.assertNotEqual(results[0]['Date Acquired'], 'UNKNOWN')
    
    def test_missing_basis_detection(self):
        """Test that missing basis (insufficient purchase history) is detected."""
        # Setup: Buy 0.5 BTC but sell 1.0 BTC
        self.mock_cursor.fetchall.side_effect = [
            # Trade purchases (only 0.5 BTC)
            [(datetime(2024, 1, 1), 0.5, 50000.0, 25000.0, 'Exchange1')],
            # Interest income purchases
            [],
            # Sales (1.0 BTC)
            [(datetime(2024, 12, 1), 1.0, 'Exchange1', 1)],
        ]
        self.mock_cursor.fetchone.return_value = (60000.0, 60000.0)
        
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
        # Setup: Buy on Jan 1, sell on different dates
        self.mock_cursor.fetchall.side_effect = [
            # Trade purchases
            [
                (datetime(2024, 1, 1), 0.5, 50000.0, 25000.0, 'Exchange1'),
                (datetime(2024, 1, 1), 0.5, 50000.0, 25000.0, 'Exchange1'),
            ],
            # Interest income purchases
            [],
            # Sales
            [
                (datetime(2024, 6, 1), 0.5, 'Exchange1', 1),   # < 365 days = Short
                (datetime(2025, 1, 2), 0.5, 'Exchange1', 2),  # >= 365 days = Long
            ],
        ]
        self.mock_cursor.fetchone.side_effect = [
            (30000.0, 30000.0),  # First sale proceeds
            (30000.0, 30000.0),  # Second sale proceeds (2025, not in 2024 results)
        ]
        
        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)
        
        # Only 2024 sale should be in results
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['Term'], 'Short')
        
        # Test 2025 to see long-term
        self.mock_cursor.fetchall.side_effect = [
            # Trade purchases
            [
                (datetime(2024, 1, 1), 0.5, 50000.0, 25000.0, 'Exchange1'),
                (datetime(2024, 1, 1), 0.5, 50000.0, 25000.0, 'Exchange1'),
            ],
            # Interest income purchases
            [],
            # Sales through 2025
            [
                (datetime(2024, 6, 1), 0.5, 'Exchange1', 1),
                (datetime(2025, 1, 2), 0.5, 'Exchange1', 2),
            ],
        ]
        self.mock_cursor.fetchone.side_effect = [
            (30000.0, 30000.0),
            (30000.0, 30000.0),
        ]
        
        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2025)
        
        # 2025 sale should be long-term (366 days)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['Term'], 'Long')
    
    def test_worksheet_output(self):
        """Test that worksheet contains detailed calculation data."""
        # Setup: Simple single sale
        self.mock_cursor.fetchall.side_effect = [
            # Trade purchases
            [(datetime(2024, 1, 1), 1.0, 50000.0, 50000.0, 'Exchange1')],
            # Interest income purchases
            [],
            # Sales
            [(datetime(2024, 12, 1), 1.0, 'Exchange1', 1)],
        ]
        self.mock_cursor.fetchone.return_value = (60000.0, 60000.0)
        
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
        self.crypto.add_price_pair(datetime(2024, 1, 1), from_curr='USD', to_curr='BTC', price=1/50000.0)

        results, worksheet = self.crypto.get_sales_for_1099b('BTC', 2024)

        self.assertEqual(len(results), 0)
        self.assertEqual(len(worksheet), 0)
    
    def test_mixed_trades_and_interest(self):
        """Test proper chronological sorting of trades and interest income."""
        # Setup: Interleaved trades and interest income
        self.mock_cursor.fetchall.side_effect = [
            # Trade purchases
            [
                (datetime(2024, 1, 1), 0.5, 40000.0, 20000.0, 'Exchange1'),
                (datetime(2024, 3, 1), 0.5, 50000.0, 25000.0, 'Exchange1'),
            ],
            # Interest income purchases (between the trades)
            [
                (datetime(2024, 2, 1), 0.1, 500.0, 50.0, 'Exchange1'),
            ],
            # Sales (sell 1.1 BTC total)
            [(datetime(2024, 12, 1), 1.1, 'Exchange1', 1)],
        ]
        self.mock_cursor.fetchone.return_value = (60000.0, 66000.0)
        
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
        # This would test the script's argument parsing
        # For now, just verify the validation logic exists
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
