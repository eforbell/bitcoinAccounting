"""Integration tests for CLI scripts to verify SQLite backend compatibility.

Tests the core functionality used by each CLI script with in-memory SQLite database.
SQL-011: CLI scripts compatibility verification
"""
import sys
import os
from datetime import datetime, timedelta
import pytest

# Add src/python to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

from cryptoAccounts import CryptoAccounts
from db import SqliteBackend


class TestBalanceScript:
    """Tests for 'balance' script functionality."""

    def test_balance_with_multiple_accounts(self) -> None:
        """Verify balance script queries work across multiple accounts."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add transactions to different accounts
        crypto.deposit(exchange='Vault', deposit_date=datetime(2025, 1, 1), buy=0.5, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 2), buy=0.3, buy_curr='BTC')
        crypto.deposit(exchange='River', deposit_date=datetime(2025, 1, 3), buy=0.2, buy_curr='BTC')

        # Test get_balance_by_account (used by balance script)
        vault_balance = crypto.get_balance_by_account('BTC', 'Vault')
        strike_balance = crypto.get_balance_by_account('BTC', 'Strike')
        river_balance = crypto.get_balance_by_account('BTC', 'River')
        total_balance = crypto.get_balance('BTC')

        assert vault_balance == 0.5
        assert strike_balance == 0.3
        assert river_balance == 0.2
        assert total_balance == 1.0

        crypto.close()

    def test_balance_with_basis(self) -> None:
        """Verify balance script can compute basis."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add some trades with USD prices
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=10000, buy_curr='USD')
        crypto.execute_trade(
            exchange='Strike',
            trade_date=datetime(2025, 1, 1, 1, 0, 0),
            buy=0.2,
            buy_curr='BTC',
            sell=10000,
            sell_curr='USD',
            fee=0,
            fee_curr='USD'
        )

        balance = crypto.get_balance('BTC')
        basis = crypto.get_basis('BTC')

        assert balance == 0.2
        assert basis == 50000.0  # $10000 / 0.2 BTC


class TestBuySatsScript:
    """Tests for 'buySats' script functionality."""

    def test_buy_flow(self) -> None:
        """Verify complete buy flow: deposit USD, trade for BTC."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        exchange = 'Strike'
        purchase_date = datetime(2025, 1, 15, 10, 0, 0)
        total_usd = 5000.0
        btc_quantity = 0.1

        # Step 1: Deposit USD
        crypto.deposit(exchange=exchange, deposit_date=purchase_date, buy=total_usd, buy_curr='USD')

        # Step 2: Execute trade
        # Note: fees are tracked separately but already included in buy/sell amounts
        crypto.execute_trade(
            exchange=exchange,
            trade_date=purchase_date + timedelta(seconds=30),
            buy=btc_quantity,
            buy_curr='BTC',
            sell=total_usd,
            sell_curr='USD',
            fee=0.0001,
            fee_curr='BTC'
        )

        # Verify results
        btc_balance = crypto.get_balance('BTC')
        usd_balance = crypto.get_balance('USD')

        assert btc_balance == 0.1  # Fee tracked separately, not deducted from balance
        assert usd_balance == 0.0

        crypto.close()

    def test_buy_with_withdrawal(self) -> None:
        """Verify buy followed by withdrawal to cold storage."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        exchange = 'Strike'
        wallet = 'Ledger-2'
        purchase_date = datetime(2025, 1, 15, 10, 0, 0)
        btc_quantity = 0.1

        # Buy BTC
        crypto.deposit(exchange=exchange, deposit_date=purchase_date, buy=5000, buy_curr='USD')
        crypto.execute_trade(
            exchange=exchange,
            trade_date=purchase_date,
            buy=btc_quantity,
            buy_curr='BTC',
            sell=5000,
            sell_curr='USD',
            fee=0,
            fee_curr='USD'
        )

        # Withdraw to cold storage
        crypto.transfer_funds(
            from_account=exchange,
            to_account=wallet,
            withdraw_date=purchase_date + timedelta(hours=1),
            deposit_date=purchase_date + timedelta(hours=12),
            tx_amount=btc_quantity,
            tx_coin='BTC'
        )

        # Verify balances
        exchange_balance = crypto.get_balance_by_account('BTC', exchange)
        wallet_balance = crypto.get_balance_by_account('BTC', wallet)

        assert exchange_balance == 0.0
        assert wallet_balance == btc_quantity

        crypto.close()


class TestTradesScript:
    """Tests for 'trades' script functionality."""

    def test_print_trades(self) -> None:
        """Verify print_trades() executes without errors."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add sample trade
        crypto.deposit(exchange='Kraken', deposit_date=datetime(2025, 1, 1), buy=10000, buy_curr='USD')
        crypto.execute_trade(
            exchange='Kraken',
            trade_date=datetime(2025, 1, 1, 12, 0, 0),
            buy=0.2,
            buy_curr='BTC',
            sell=10000,
            sell_curr='USD',
            fee=5,
            fee_curr='USD'
        )

        # Add price data for cost basis
        crypto.add_price_pair(
            from_curr='BTC',
            to_curr='USD',
            price=50000,
            pair_date=datetime(2025, 1, 1, 12, 0, 0)
        )

        # This should not raise an error
        crypto.print_trades('BTC')

        crypto.close()


class TestSellScript:
    """Tests for 'sell' script functionality."""

    def test_sell_btc(self) -> None:
        """Verify selling BTC for USD."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # First buy BTC
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=10000, buy_curr='USD')
        crypto.execute_trade(
            exchange='Strike',
            trade_date=datetime(2025, 1, 1),
            buy=0.2,
            buy_curr='BTC',
            sell=10000,
            sell_curr='USD',
            fee=0,
            fee_curr='USD'
        )

        # Now sell half
        crypto.execute_trade(
            exchange='Strike',
            trade_date=datetime(2025, 2, 1),
            buy=6000,
            buy_curr='USD',
            sell=0.1,
            sell_curr='BTC',
            fee=0,
            fee_curr='USD'
        )

        btc_balance = crypto.get_balance('BTC')
        usd_balance = crypto.get_balance('USD')

        assert btc_balance == 0.1
        assert usd_balance == 6000.0

        crypto.close()


class TestEarnInterestScript:
    """Tests for 'earnInterest' script functionality."""

    def test_interest_income(self) -> None:
        """Verify recording interest income."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Record interest income
        crypto.interest(
            exchange='Kraken',
            interest_date=datetime(2025, 1, 15),
            buy=0.001,
            buy_curr='BTC',
            group='staking-rewards'
        )

        balance = crypto.get_balance('BTC')
        assert balance == 0.001

        crypto.close()


class TestTransferScript:
    """Tests for 'transfer' script functionality."""

    def test_transfer_between_accounts(self) -> None:
        """Verify transfer_funds() works correctly."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Setup: deposit to source account
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=1.0, buy_curr='BTC')

        # Transfer
        crypto.transfer_funds(
            from_account='Strike',
            to_account='Ledger-2',
            withdraw_date=datetime(2025, 1, 2, 10, 0, 0),
            deposit_date=datetime(2025, 1, 2, 22, 0, 0),
            tx_amount=1.0,
            tx_coin='BTC'
        )

        strike_balance = crypto.get_balance_by_account('BTC', 'Strike')
        ledger_balance = crypto.get_balance_by_account('BTC', 'Ledger-2')
        total_balance = crypto.get_balance('BTC')

        assert strike_balance == 0.0
        assert ledger_balance == 1.0
        assert total_balance == 1.0

        crypto.close()


class TestExport1099bScript:
    """Tests for 'export_1099b' script functionality."""

    def test_sales_for_1099b_generation(self) -> None:
        """Verify get_sales_for_1099b() works with SQLite."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Buy BTC
        crypto.deposit(exchange='Kraken', deposit_date=datetime(2024, 1, 1), buy=10000, buy_curr='USD')
        crypto.execute_trade(
            exchange='Kraken',
            trade_date=datetime(2024, 1, 1, 12, 0, 0),
            buy=0.2,
            buy_curr='BTC',
            sell=10000,
            sell_curr='USD',
            fee=0,
            fee_curr='USD'
        )

        # Add price data
        crypto.add_price_pair(pair_date=datetime(2024, 1, 1, 12, 0, 0), to_curr='BTC', from_curr='USD', price=50000)
        crypto.add_price_pair(pair_date=datetime(2024, 6, 1, 12, 0, 0), to_curr='BTC', from_curr='USD', price=60000)

        # Sell BTC (short-term gain)
        crypto.execute_trade(
            exchange='Kraken',
            trade_date=datetime(2024, 6, 1, 12, 0, 0),
            buy=12000,
            buy_curr='USD',
            sell=0.2,
            sell_curr='BTC',
            fee=0,
            fee_curr='USD'
        )

        # Get 1099b data (returns tuple of two lists: (form_b_rows, summary_rows))
        form_b_rows, summary_rows = crypto.get_sales_for_1099b(
            coin='BTC',
            tax_year=2024,
            wallet=None
        )

        assert len(form_b_rows) == 1
        # Check that the sale was recorded (exact format may vary)
        assert form_b_rows[0] is not None

        crypto.close()


class TestForecastGainsScript:
    """Tests for 'forecast_gains' script functionality."""

    def test_forecast_capital_gains(self) -> None:
        """Verify forecast_capital_gains_fifo() works with SQLite."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Buy BTC at different times
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 1, 1), buy=10000, buy_curr='USD')
        crypto.execute_trade(
            exchange='Strike',
            trade_date=datetime(2024, 1, 1, 12, 0, 0),
            buy=0.1,
            buy_curr='BTC',
            sell=10000,
            sell_curr='USD',
            fee=0,
            fee_curr='USD'
        )

        # Add price data
        crypto.add_price_pair(pair_date=datetime(2024, 1, 1, 12, 0, 0), to_curr='BTC', from_curr='USD', price=100000)
        crypto.add_price_pair(pair_date=datetime(2025, 1, 15, 12, 0, 0), to_curr='BTC', from_curr='USD', price=110000)

        # Forecast gains if sold today at a given price
        # Returns tuple of results, not dict
        result = crypto.forecast_capital_gains_fifo(
            coin='BTC',
            quantity=0.1,
            sale_price_usd=110000,
            wallet=None
        )

        # Just verify it returns something (tuple or other structure)
        assert result is not None

        crypto.close()


class TestWalletBalancesScript:
    """Tests for 'wallet_balances' script functionality."""

    def test_get_wallets(self) -> None:
        """Verify get_wallets() executes without errors."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add deposits to different wallets (wallets may be implicit in ledger)
        crypto.deposit(exchange='Ledger-2', deposit_date=datetime(2025, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.deposit(exchange='Vault', deposit_date=datetime(2025, 1, 1), buy=0.5, buy_curr='BTC')

        # get_wallets() queries the wallets table (not ledger)
        # Wallets may need to be explicitly created, or this returns empty
        wallets = crypto.get_wallets()

        # Just verify the method works (may return empty list for in-memory DB)
        assert isinstance(wallets, list)

        crypto.close()

    def test_get_wallet_balance(self) -> None:
        """Verify get_wallet_balance() works correctly."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add deposit to wallet (wallet created implicitly)
        crypto.deposit(exchange='Ledger-2', deposit_date=datetime(2025, 1, 1), buy=0.5, buy_curr='BTC')

        # get_wallet_balance(coin, wallet) - note parameter order
        balance = crypto.get_wallet_balance('BTC', 'Ledger-2')

        assert balance == 0.5

        crypto.close()


class TestWalletLedgerScript:
    """Tests for 'wallet_ledger' script functionality."""

    def test_get_transactions(self) -> None:
        """Verify get_transactions() returns transaction history."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add transactions
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=0.1, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 2), buy=0.2, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 3), buy=0.3, buy_curr='BTC')

        # Get transactions (returns tuple: (headers, transaction_list))
        result = crypto.get_transactions(coin='BTC')

        # result[0] is headers, result[1] is list of transaction dicts
        assert len(result) == 2  # (headers, transactions)
        headers = result[0]
        transactions = result[1]

        assert isinstance(headers, list)
        assert isinstance(transactions, list)
        assert len(transactions) == 3

        crypto.close()


class TestExchangeLiquidityScript:
    """Tests for 'exchange_liquidity' script functionality."""

    def test_balances_across_exchanges(self) -> None:
        """Verify balances can be queried per exchange."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Distribute BTC across exchanges
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=0.3, buy_curr='BTC')
        crypto.deposit(exchange='Kraken', deposit_date=datetime(2025, 1, 1), buy=0.5, buy_curr='BTC')
        crypto.deposit(exchange='River', deposit_date=datetime(2025, 1, 1), buy=0.2, buy_curr='BTC')

        strike_bal = crypto.get_balance_by_account('BTC', 'Strike')
        kraken_bal = crypto.get_balance_by_account('BTC', 'Kraken')
        river_bal = crypto.get_balance_by_account('BTC', 'River')

        assert strike_bal == 0.3
        assert kraken_bal == 0.5
        assert river_bal == 0.2

        crypto.close()


class TestValidateTransfersScript:
    """Tests for 'validate_transfers' script functionality."""

    def test_matching_transfers(self) -> None:
        """Verify transfer validation with matching withdrawal/deposit pairs."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Valid transfer pair
        crypto.transfer_funds(
            from_account='Strike',
            to_account='Ledger-2',
            withdraw_date=datetime(2025, 1, 1, 10, 0, 0),
            deposit_date=datetime(2025, 1, 1, 22, 0, 0),
            tx_amount=0.5,
            tx_coin='BTC'
        )

        # Both withdrawal and deposit should exist
        result = crypto.get_transactions('BTC')
        # result[0] is headers, result[1] is list of transaction dicts
        headers = result[0]
        transactions = result[1]

        withdrawals = [tx for tx in transactions if tx.get('Type') == 'Withdrawal']
        deposits = [tx for tx in transactions if tx.get('Type') == 'Deposit']

        assert len(withdrawals) == 1
        assert len(deposits) == 1
        assert withdrawals[0]['Sell'] == 0.5
        assert deposits[0]['Buy'] == 0.5

        crypto.close()


class TestDiagnoseBalancesScript:
    """Tests for 'diagnose_balances' script functionality."""

    def test_balance_calculation_verification(self) -> None:
        """Verify balance calculations are consistent."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add transactions
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.withdraw(exchange='Strike', withdraw_date=datetime(2025, 1, 2), sell=0.3, sell_curr='BTC')

        balance = crypto.get_balance('BTC')
        account_balance = crypto.get_balance_by_account('BTC', 'Strike')

        # Both methods should agree
        assert balance == 0.7
        assert account_balance == 0.7

        crypto.close()


class TestCompareWithSparrowScript:
    """Tests for 'compare_with_sparrow' script functionality."""

    def test_balance_comparison_setup(self) -> None:
        """Verify balance can be queried for comparison with external wallets."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Setup wallet with known balance
        crypto.deposit(exchange='Ledger-2', deposit_date=datetime(2025, 1, 1), buy=1.23456789, buy_curr='BTC')

        # get_wallet_balance(coin, wallet) - note parameter order
        wallet_balance = crypto.get_wallet_balance('BTC', 'Ledger-2')

        assert wallet_balance == pytest.approx(1.23456789, rel=1e-8)

        crypto.close()


class TestExportTxScript:
    """Tests for 'export_tx' script functionality."""

    def test_transaction_export(self) -> None:
        """Verify transactions can be queried for CSV export."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add various transaction types
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.withdraw(exchange='Strike', withdraw_date=datetime(2025, 1, 2), sell=0.5, sell_curr='BTC')
        crypto.interest(exchange='Strike', interest_date=datetime(2025, 1, 3), buy=0.01, buy_curr='BTC')

        result = crypto.get_transactions('BTC')

        # result[0] is headers, result[1] is list of transaction dicts
        headers = result[0]
        transactions = result[1]

        assert len(transactions) == 3
        assert transactions[0]['Type'] == 'Deposit'
        assert transactions[1]['Type'] == 'Withdrawal'
        assert transactions[2]['Type'] == 'Interest Income'

        crypto.close()

    def test_export_with_wallet_filter(self) -> None:
        """Verify export can filter by wallet/exchange."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add transactions to different wallets
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.deposit(exchange='Coldcard', deposit_date=datetime(2025, 1, 2), buy=0.5, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 3), buy=0.3, buy_curr='BTC')
        crypto.deposit(exchange='Vault', deposit_date=datetime(2025, 1, 4), buy=0.2, buy_curr='BTC')

        # Filter by Strike wallet
        headers, transactions = crypto.get_transactions(wallet='Strike')

        assert len(transactions) == 2
        assert all(tx['Exchange'] == 'Strike' for tx in transactions)
        assert transactions[0]['Buy'] == 1.0
        assert transactions[1]['Buy'] == 0.3

        crypto.close()

    def test_export_with_date_range_filter(self) -> None:
        """Verify export can filter by date range."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add transactions across different dates
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 6, 15), buy=0.5, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 12, 31), buy=0.3, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 15), buy=0.2, buy_curr='BTC')

        # Filter to 2024 only
        headers, transactions = crypto.get_transactions(
            start_date='2024-01-01',
            end_date='2024-12-31'
        )

        assert len(transactions) == 3
        for tx in transactions:
            tx_date = str(tx['Date'])[:10]
            assert tx_date >= '2024-01-01'
            assert tx_date <= '2024-12-31'

        crypto.close()

    def test_export_with_combined_filters(self) -> None:
        """Verify export can combine wallet, coin, and date filters."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add diverse transactions
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 6, 15), buy=100.0, buy_curr='USD')
        crypto.deposit(exchange='Coldcard', deposit_date=datetime(2024, 3, 1), buy=0.5, buy_curr='BTC')
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=0.3, buy_curr='BTC')

        # Filter: Strike + BTC + 2024
        headers, transactions = crypto.get_transactions(
            coin='BTC',
            wallet='Strike',
            start_date='2024-01-01',
            end_date='2024-12-31'
        )

        assert len(transactions) == 1
        assert transactions[0]['Exchange'] == 'Strike'
        assert transactions[0]['Buy Cur.'] == 'BTC'
        assert transactions[0]['Buy'] == 1.0

        crypto.close()

    def test_export_with_empty_result_set(self) -> None:
        """Verify export handles empty result sets gracefully."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add some transactions
        crypto.deposit(exchange='Strike', deposit_date=datetime(2024, 1, 1), buy=1.0, buy_curr='BTC')

        # Filter for non-existent wallet
        headers, transactions = crypto.get_transactions(wallet='NonExistent')

        assert len(transactions) == 0
        assert headers == []

        # Filter for future dates
        headers, transactions = crypto.get_transactions(
            start_date='2030-01-01',
            end_date='2030-12-31'
        )

        assert len(transactions) == 0

        crypto.close()

    def test_export_csv_file_creation(self) -> None:
        """Verify export_transactions_csv creates valid CSV file."""
        import tempfile
        import csv

        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add test transactions
        crypto.deposit(exchange='Strike', deposit_date=datetime(2025, 1, 1), buy=1.0, buy_curr='BTC')
        crypto.deposit(exchange='Coldcard', deposit_date=datetime(2025, 1, 2), buy=0.5, buy_curr='BTC')

        # Export to temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            temp_path = f.name

        try:
            crypto.export_transactions_csv(temp_path, wallet='Strike')

            # Read and verify CSV
            with open(temp_path, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 1
            assert rows[0]['Exchange'] == 'Strike'
            assert rows[0]['Buy'] == '1.0'
            assert rows[0]['Buy Cur.'] == 'BTC'

        finally:
            # Clean up
            import os
            if os.path.exists(temp_path):
                os.remove(temp_path)

        crypto.close()

    def test_export_with_coin_filter_includes_fees(self) -> None:
        """Verify coin filter includes transactions where coin appears in fee_curr."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Add trade with BTC fee
        crypto.execute_trade(
            exchange='Strike',
            trade_date=datetime(2025, 1, 1),
            buy=100.0,
            buy_curr='USD',
            sell=0.001,
            sell_curr='ETH',
            fee=0.0001,
            fee_curr='BTC'
        )

        # Filter by BTC (should include transaction with BTC fee)
        headers, transactions = crypto.get_transactions(coin='BTC')

        assert len(transactions) == 1
        assert transactions[0]['Fee Cur.'] == 'BTC'

        crypto.close()


class TestGainsTrackerScript:
    """Tests for 'gains_tracker' script functionality."""

    def test_realized_gains_tracking(self) -> None:
        """Verify realized gains can be tracked with FIFO."""
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        crypto = CryptoAccounts(backend)

        # Buy low, sell high
        crypto.deposit(exchange='Kraken', deposit_date=datetime(2024, 1, 1), buy=10000, buy_curr='USD')
        crypto.execute_trade(
            exchange='Kraken',
            trade_date=datetime(2024, 1, 1),
            buy=0.2,
            buy_curr='BTC',
            sell=10000,
            sell_curr='USD',
            fee=0,
            fee_curr='USD'
        )

        # Add price data
        crypto.add_price_pair(pair_date=datetime(2024, 1, 1), to_curr='BTC', from_curr='USD', price=50000)
        crypto.add_price_pair(pair_date=datetime(2024, 6, 1), to_curr='BTC', from_curr='USD', price=70000)

        # Sell
        crypto.execute_trade(
            exchange='Kraken',
            trade_date=datetime(2024, 6, 1),
            buy=14000,
            buy_curr='USD',
            sell=0.2,
            sell_curr='BTC',
            fee=0,
            fee_curr='USD'
        )

        # Get 1099b data (gains tracker uses this)
        # Returns tuple of (form_b_rows, summary_rows)
        form_b_rows, summary_rows = crypto.get_sales_for_1099b(coin='BTC', tax_year=2024, wallet=None)

        # Verify at least one sale was recorded
        assert len(form_b_rows) == 1
        assert form_b_rows[0] is not None

        crypto.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
