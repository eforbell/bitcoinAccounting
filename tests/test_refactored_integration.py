"""Integration tests for refactored query classes.

Tests cross-query-class interactions and full workflows to verify that the
refactored architecture works correctly end-to-end.

REFACTOR-008: Add integration tests for refactored code
"""
import sys
import os
from datetime import datetime
import pytest

# Add src/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from bitcoinAccounts import CryptoAccounts
from db import SqliteBackend


class TestFullWorkflowIntegration:
    """Test complete workflow: import → query → export → 1099-B generation."""

    def test_import_query_export_1099b_workflow(self) -> None:
        """Test full workflow from import to 1099-B generation."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Step 1: Import transactions using import_transactions()
        transactions = [
            # Deposit USD
            {
                'trans_type': 'Deposit',
                'created_date': '2024-01-01 10:00:00',
                'buy': 50000.0,
                'buy_curr': 'USD',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Initial deposit'
            },
            # Buy BTC
            {
                'trans_type': 'Trade',
                'created_date': '2024-01-01 11:00:00',
                'buy': 1.0,
                'buy_curr': 'BTC',
                'sell': 50000.0,
                'sell_curr': 'USD',
                'fee': 10.0,
                'fee_curr': 'USD',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Purchase BTC'
            },
            # Earn interest
            {
                'trans_type': 'Interest Income',
                'created_date': '2024-06-01 10:00:00',
                'buy': 0.01,
                'buy_curr': 'BTC',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Interest earned',
                'usd_equivalent': '600.00'  # $60,000/BTC price
            },
            # Sell some BTC
            {
                'trans_type': 'Trade',
                'created_date': '2024-12-01 10:00:00',
                'buy': 60000.0,
                'buy_curr': 'USD',
                'sell': 1.0,
                'sell_curr': 'BTC',
                'fee': 10.0,
                'fee_curr': 'USD',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Sell BTC'
            }
        ]

        result = crypto.import_transactions(transactions)
        assert result['imported'] == 4
        assert result['skipped'] == 0

        # Step 2: Query transactions using TransactionQuery (via get_transactions)
        headers, all_txs = crypto.get_transactions()
        assert len(all_txs) == 4

        headers, btc_txs = crypto.get_transactions(coin='BTC')
        assert len(btc_txs) == 3  # BTC trade, interest, BTC sale

        # Step 3: Verify balances using WalletQuery
        btc_balance = crypto.get_balance('BTC')
        assert btc_balance == pytest.approx(0.01)  # 1 bought + 0.01 interest - 1 sold

        usd_balance = crypto.get_balance('USD')
        assert usd_balance == pytest.approx(60000.0)  # -50k buy + 60k sell

        strike_balance = crypto.get_balance_by_account('BTC', 'Strike')
        assert strike_balance == pytest.approx(0.01)

        # Step 4: Generate 1099-B using CapitalGainCalculator
        results, worksheet = crypto.get_sales_for_1099b('BTC', 2024)

        # FIFO will consume the Jan 1 purchase for the full 1.0 BTC sale
        assert len(results) == 1
        sale = results[0]

        assert sale['Description'] == '1.00000000 BTC'
        assert sale['Proceeds'] == '60000.00'
        # Cost basis: $50,000 purchase (interest not consumed since we only sold 1.0 BTC)
        assert sale['Cost Basis'] == '50000.00'
        # Jan 1 to Dec 1 is 334 days, which is < 365, so it's Short term
        assert sale['Term'] == 'Short'

        crypto.close()

    def test_import_export_roundtrip(self) -> None:
        """Test round-trip: export with TransactionQuery → reimport."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Import initial transactions
        transactions = [
            {
                'trans_type': 'Deposit',
                'created_date': '2024-01-01 10:00:00',
                'buy': 1.0,
                'buy_curr': 'BTC',
                'exchange': 'Coldcard',
                'group': 'wallet',
                'comment': 'Hardware wallet'
            },
            {
                'trans_type': 'Withdrawal',
                'created_date': '2024-02-01 10:00:00',
                'sell': 0.5,
                'sell_curr': 'BTC',
                'fee': 0.0001,
                'fee_curr': 'BTC',
                'exchange': 'Coldcard',
                'group': 'wallet',
                'comment': 'Send to exchange'
            }
        ]

        crypto.import_transactions(transactions)

        # Export transactions using TransactionQuery
        headers, exported = crypto.get_transactions(wallet='Coldcard')
        assert len(exported) == 2

        # Verify exported data structure
        deposit = exported[0]
        assert deposit['Buy'] == 1.0
        assert deposit['Buy Cur.'] == 'BTC'
        assert deposit['Exchange'] == 'Coldcard'
        assert deposit['Comment'] == 'Hardware wallet'

        withdrawal = exported[1]
        assert withdrawal['Sell'] == 0.5
        assert withdrawal['Sell Cur.'] == 'BTC'
        assert withdrawal['Fee'] == 0.0001

        # Create new database and reimport
        backend2 = SqliteBackend(':memory:', auto_create_tables=True)
        crypto2 = CryptoAccounts(backend2)

        # Convert exported transactions to import format
        reimport_txs = []
        for tx in exported:
            reimport_tx = {
                'trans_type': tx['Type'],
                'created_date': tx['Date'],
                'exchange': tx['Exchange'],
                'group': tx['Group'],
                'comment': tx['Comment']
            }
            if tx.get('Buy'):
                reimport_tx['buy'] = tx['Buy']
                reimport_tx['buy_curr'] = tx['Buy Cur.']
            if tx.get('Sell'):
                reimport_tx['sell'] = tx['Sell']
                reimport_tx['sell_curr'] = tx['Sell Cur.']
            if tx.get('Fee'):
                reimport_tx['fee'] = tx['Fee']
                reimport_tx['fee_curr'] = tx['Fee Cur.']
            reimport_txs.append(reimport_tx)

        result = crypto2.import_transactions(reimport_txs)
        assert result['imported'] == 2
        assert result['skipped'] == 0

        # Verify balances match
        assert crypto2.get_balance('BTC') == crypto.get_balance('BTC')
        assert crypto2.get_balance_by_account('BTC', 'Coldcard') == crypto.get_balance_by_account('BTC', 'Coldcard')

        crypto.close()
        crypto2.close()


class TestCrossQueryClassInteractions:
    """Test interactions between different query classes."""

    def test_capital_gain_calculator_uses_trade_and_income_queries(self) -> None:
        """Test CapitalGainCalculator correctly queries TradeQuery and IncomeQuery."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add trades (used by TradeQuery)
        crypto.execute_trade(
            trade_date=datetime(2024, 1, 1),
            buy=0.5,
            buy_curr='BTC',
            sell=25000.0,
            sell_curr='USD',
            exchange='Strike'
        )

        # Add interest income (used by IncomeQuery)
        crypto.interest(
            interest_date=datetime(2024, 2, 1),
            buy=0.1,
            buy_curr='BTC',
            exchange='Strike',
            comment='Staking rewards'
        )

        # Add another trade
        crypto.execute_trade(
            trade_date=datetime(2024, 3, 1),
            buy=0.4,
            buy_curr='BTC',
            sell=20000.0,
            sell_curr='USD',
            exchange='Strike'
        )

        # Add a sale
        crypto.execute_trade(
            trade_date=datetime(2024, 12, 1),
            buy=60000.0,
            buy_curr='USD',
            sell=1.0,
            sell_curr='BTC',
            exchange='Strike'
        )

        # CapitalGainCalculator should use TradeQuery to get purchases
        # and IncomeQuery to get interest income, then apply FIFO matching
        results, worksheet = crypto.get_sales_for_1099b('BTC', 2024)

        # Should have 1 sale broken into 3 lots (FIFO order):
        # - 0.5 BTC from Jan 1 trade @ $50k/BTC
        # - 0.1 BTC from Feb 1 interest @ $0/BTC (income has zero basis)
        # - 0.4 BTC from Mar 1 trade @ $50k/BTC
        assert len(results) == 3

        # First lot: 0.5 BTC @ $50k/BTC
        assert results[0]['Description'] == '0.50000000 BTC'
        assert results[0]['Cost Basis'] == '25000.00'
        assert results[0]['Proceeds'] == '30000.00'  # 0.5/1.0 * $60k

        # Second lot: 0.1 BTC from interest (zero basis)
        assert results[1]['Description'] == '0.10000000 BTC'
        assert results[1]['Cost Basis'] == '0.00'
        assert results[1]['Proceeds'] == '6000.00'  # 0.1/1.0 * $60k

        # Third lot: 0.4 BTC @ $50k/BTC
        assert results[2]['Description'] == '0.40000000 BTC'
        assert results[2]['Cost Basis'] == '20000.00'
        assert results[2]['Proceeds'] == '24000.00'  # 0.4/1.0 * $60k

        crypto.close()

    def test_ledger_writer_and_transaction_query_consistency(self) -> None:
        """Test LedgerWriter creates records that TransactionQuery can retrieve."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Use LedgerWriter (via convenience methods) to write transactions
        crypto.deposit(
            exchange='Strike',
            deposit_date=datetime(2024, 1, 1),
            buy=1000.0,
            buy_curr='USD',
            comment='Test deposit'
        )

        crypto.withdraw(
            exchange='Strike',
            withdraw_date=datetime(2024, 1, 2),
            sell=500.0,
            sell_curr='USD',
            fee=1.0,
            fee_curr='USD',
            comment='Test withdrawal'
        )

        # Use TransactionQuery (via get_transactions) to read them back
        headers, txs = crypto.get_transactions(coin='USD')
        assert len(txs) == 2

        # Verify deposit
        deposit = txs[0]
        assert deposit['Type'] == 'Deposit'
        assert deposit['Buy'] == 1000.0
        assert deposit['Buy Cur.'] == 'USD'
        assert deposit['Comment'] == 'Test deposit'

        # Verify withdrawal
        withdrawal = txs[1]
        assert withdrawal['Type'] == 'Withdrawal'
        assert withdrawal['Sell'] == 500.0
        assert withdrawal['Sell Cur.'] == 'USD'
        assert withdrawal['Fee'] == 1.0
        assert withdrawal['Comment'] == 'Test withdrawal'

        # Verify balance matches what LedgerWriter recorded
        # Note: Fees are already included in sell amounts, not subtracted separately
        # So: 1000 deposit - 500 withdrawal (fee is tracked in fee column, not deducted again)
        balance = crypto.get_balance('USD')
        assert balance == pytest.approx(500.0)  # 1000 deposit - 500 withdrawal

        crypto.close()

    def test_wallet_query_aggregates_ledger_writer_records(self) -> None:
        """Test WalletQuery correctly aggregates records from LedgerWriter."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Use LedgerWriter to create transactions in multiple wallets
        crypto.deposit(exchange='Vault', deposit_date=datetime(2024, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 1, 2), buy=0.5, buy_curr='BTC')
        crypto.deposit(exchange='River', deposit_date=datetime(2024, 1, 3), buy=0.3, buy_curr='BTC')

        # Use WalletQuery to aggregate by wallet
        vault_balance = crypto.get_balance_by_account('BTC', 'Vault')
        strike_balance = crypto.get_balance_by_account('BTC', 'Strike')
        river_balance = crypto.get_balance_by_account('BTC', 'River')
        total_balance = crypto.get_balance('BTC')

        assert vault_balance == 1.0
        assert strike_balance == 0.5
        assert river_balance == 0.3
        assert total_balance == 1.8

        # Test get_wallet_balance with None to get all wallets (returns dict)
        all_balances = crypto.get_wallet_balance('BTC', None)
        assert isinstance(all_balances, dict)
        assert all_balances['Vault'] == 1.0
        assert all_balances['Strike'] == 0.5
        assert all_balances['River'] == 0.3

        # Test that we can query transactions and see all exchanges
        headers, all_txs = crypto.get_transactions()
        exchanges = {tx['Exchange'] for tx in all_txs}
        assert exchanges == {'Vault', 'Strike', 'River'}

        crypto.close()


class TestDataConsistency:
    """Test data consistency across query classes."""

    def test_transaction_query_filters_match_balance_calculations(self) -> None:
        """Test filtered transactions from TransactionQuery match balance calculations."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add transactions in multiple wallets
        crypto.deposit(exchange='Vault', deposit_date=datetime(2024, 1, 1), buy=2.0, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 1, 2), buy=1.0, buy_curr='BTC')
        crypto.withdraw(exchange='Vault', withdraw_date=datetime(2024, 1, 3), sell=0.5, sell_curr='BTC', fee=0.0001, fee_curr='BTC')

        # Get transactions for Vault only
        headers, vault_txs = crypto.get_transactions(wallet='Vault')
        assert len(vault_txs) == 2

        # Manually calculate balance from filtered transactions
        # Note: Fees are already included in buy/sell amounts, not subtracted separately
        manual_balance = 0.0
        for tx in vault_txs:
            if tx.get('Buy') and tx.get('Buy Cur.') == 'BTC':
                manual_balance += tx['Buy']
            if tx.get('Sell') and tx.get('Sell Cur.') == 'BTC':
                manual_balance -= tx['Sell']

        # Compare with WalletQuery balance
        wallet_balance = crypto.get_balance_by_account('BTC', 'Vault')

        assert manual_balance == pytest.approx(wallet_balance)
        assert wallet_balance == pytest.approx(1.5)  # 2.0 - 0.5 (fee tracked separately)

        crypto.close()

    def test_date_filtered_transactions_match_balance_snapshot(self) -> None:
        """Test date-filtered transactions produce correct balance snapshot."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add transactions across multiple dates
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 2, 1), buy=0.5, buy_curr='BTC')
        crypto.withdraw(exchange='Strike', withdraw_date=datetime(2024, 3, 1), sell=0.3, sell_curr='BTC', fee=0.0001, fee_curr='BTC')

        # Get transactions up to Jan 31 (should only include first deposit)
        headers, jan_txs = crypto.get_transactions(
            end_date=datetime(2024, 1, 31)
        )
        assert len(jan_txs) == 1

        # Get transactions from Feb 1 to Feb 28 (should only include second deposit)
        headers, feb_txs = crypto.get_transactions(
            start_date=datetime(2024, 2, 1),
            end_date=datetime(2024, 2, 28)
        )
        assert len(feb_txs) == 1

        # Verify date filtering works correctly
        assert jan_txs[0]['Buy'] == 1.0
        assert feb_txs[0]['Buy'] == 0.5

        # Current balance should be all transactions
        # Note: Fees are already included in sell amounts, not subtracted separately
        current_balance = crypto.get_balance('BTC')
        assert current_balance == pytest.approx(1.2)  # 1.0 + 0.5 - 0.3 (fee tracked separately)

        crypto.close()

    def test_multiple_wallet_filter_consistency(self) -> None:
        """Test filtering by multiple wallets returns consistent results."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add transactions in 3 wallets
        crypto.deposit(exchange='Vault', deposit_date=datetime(2024, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 1, 2), buy=0.5, buy_curr='BTC')
        crypto.deposit(exchange='River', deposit_date=datetime(2024, 1, 3), buy=0.3, buy_curr='BTC')

        # Filter by multiple wallets using TransactionQuery
        headers, multi_wallet_txs = crypto.get_transactions(wallet=['Vault', 'Strike'])
        assert len(multi_wallet_txs) == 2

        # Get individual wallet balances
        vault_balance = crypto.get_balance_by_account('BTC', 'Vault')
        strike_balance = crypto.get_balance_by_account('BTC', 'Strike')

        # Sum should match filtered transaction total
        expected_total = vault_balance + strike_balance
        assert expected_total == 1.5

        # Verify transactions are correct
        exchanges = {tx['Exchange'] for tx in multi_wallet_txs}
        assert exchanges == {'Vault', 'Strike'}

        crypto.close()


class TestComplexScenarios:
    """Test complex real-world scenarios involving multiple query classes."""

    def test_complete_buy_custody_sell_workflow(self) -> None:
        """Test complete workflow: buy on exchange, move to custody, sell from exchange."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Step 1: Import USD deposit and purchase via import_transactions
        import_txs = [
            {
                'trans_type': 'Deposit',
                'created_date': '2024-01-01 10:00:00',
                'buy': 100000.0,
                'buy_curr': 'USD',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Initial funding'
            },
            {
                'trans_type': 'Trade',
                'created_date': '2024-01-01 11:00:00',
                'buy': 2.0,
                'buy_curr': 'BTC',
                'sell': 100000.0,
                'sell_curr': 'USD',
                'fee': 10.0,
                'fee_curr': 'USD',
                'exchange': 'Strike',
                'group': '',
                'comment': 'Buy BTC'
            }
        ]

        result = crypto.import_transactions(import_txs)
        assert result['imported'] == 2

        # Step 2: Transfer to cold storage using transfer_funds (uses LedgerWriter)
        crypto.transfer_funds(
            from_account='Strike',
            to_account='Coldcard',
            withdraw_date=datetime(2024, 1, 2),
            deposit_date=datetime(2024, 1, 2, 1, 0, 0),
            tx_amount=2.0,
            tx_coin='BTC',
            fee_amount=0.0001,
            fee_coin='BTC'
        )

        # Step 3: Verify balances using WalletQuery
        # Note: transfer_funds adds fee to sell amount, so Strike withdraws tx_amount + fee
        strike_btc = crypto.get_balance_by_account('BTC', 'Strike')
        coldcard_btc = crypto.get_balance_by_account('BTC', 'Coldcard')
        # Strike: 2.0 bought - (2.0 + 0.0001) transferred = -0.0001
        assert strike_btc == pytest.approx(-0.0001, abs=1e-6)
        assert coldcard_btc == 2.0

        # Step 4: Transfer back to exchange
        crypto.transfer_funds(
            from_account='Coldcard',
            to_account='Strike',
            withdraw_date=datetime(2024, 12, 1),
            deposit_date=datetime(2024, 12, 1, 1, 0, 0),
            tx_amount=1.0,
            tx_coin='BTC',
            fee_amount=0.0001,
            fee_coin='BTC'
        )

        # Step 5: Sell BTC using execute_trade (uses LedgerWriter)
        crypto.execute_trade(
            trade_date=datetime(2024, 12, 2),
            buy=60000.0,
            buy_curr='USD',
            sell=1.0,
            sell_curr='BTC',
            fee=10.0,
            fee_curr='USD',
            exchange='Strike'
        )

        # Step 6: Export all transactions using TransactionQuery
        headers, all_txs = crypto.get_transactions()
        # Count: 1 USD deposit + 1 BTC buy + (1 withdraw + 1 deposit) + (1 withdraw + 1 deposit) + 1 sale = 7
        assert len(all_txs) == 7

        # Step 7: Generate 1099-B using CapitalGainCalculator
        results, worksheet = crypto.get_sales_for_1099b('BTC', 2024)
        assert len(results) == 1

        sale = results[0]
        assert sale['Description'] == '1.00000000 BTC'
        assert sale['Cost Basis'] == '50000.00'  # Half of original $100k purchase
        assert sale['Proceeds'] == '60000.00'
        # Jan 1 to Dec 2 is 336 days < 365, so it's Short term
        assert sale['Term'] == 'Short'

        # Step 8: Verify final balances
        final_btc = crypto.get_balance('BTC')
        final_usd = crypto.get_balance('USD')

        # BTC calculations:
        # - Bought 2.0 BTC via trade
        # - Transfer 1: Strike withdraws 2.0001 (2.0 + 0.0001 fee), Coldcard deposits 2.0
        # - Transfer 2: Coldcard withdraws 1.0001 (1.0 + 0.0001 fee), Strike deposits 1.0
        # - Sold 1.0 BTC via trade
        # Total BTC = 2.0 - 2.0001 + 2.0 - 1.0001 + 1.0 - 1.0 = 0.9998
        assert final_btc == pytest.approx(0.9998)

        # USD: 100k deposit - 100k BTC purchase + 60k BTC sale = 60k
        # But we also have USD fees from the trades (10 + 10 = 20)
        # Actually, trade fees are tracked separately and don't affect balance
        # Let me reconsider: USD balance = deposits - trades
        assert final_usd == pytest.approx(60000.0)  # 100k deposit - 100k buy + 60k sale

        crypto.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
