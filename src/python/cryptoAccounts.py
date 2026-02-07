from __future__ import annotations

import csv
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db import DatabaseBackend

class CryptoAccounts(object):

    def __init__(self, backend: DatabaseBackend | None = None):
        """Initialize CryptoAccounts with a database backend.

        Args:
            backend: DatabaseBackend instance. If None, uses get_backend() to create default.
        """
        if backend is None:
            from db import get_backend
            backend = get_backend()

        self.backend = backend

        # Create query helper instances
        from db import PriceLookup, BalanceCalculator, TradeQuery, BasisCalculator, IncomeQuery, TransactionQuery, LedgerWriter, CapitalGainCalculator, WalletQuery
        self.price_lookup = PriceLookup(backend)
        self.balance_calc = BalanceCalculator(backend)
        self.trade_query = TradeQuery(backend, self.price_lookup)
        self.basis_calc = BasisCalculator(self.trade_query)
        self.income_query = IncomeQuery(backend, self.price_lookup)
        self.transaction_query = TransactionQuery(backend)
        self.ledger_writer = LedgerWriter(backend)
        self.capital_gains_calc = CapitalGainCalculator(backend, self.trade_query, self.income_query, self.price_lookup)
        self.wallet_query = WalletQuery(backend)

    def close(self):
        self.backend.close()

    def get_balance(self, coin = 'BTC'):
        """Get total balance across all wallets for a coin.

        Fees are already included in buy/sell amounts, not subtracted separately.
        Stake transactions are excluded from the balance calculation.

        Args:
            coin: Currency code (e.g., 'BTC', 'USD')

        Returns:
            float: Total balance
        """
        balance = self.balance_calc.get_balance(coin)
        # Return 0 for very small amounts (dust)
        return balance if abs(balance) > 0.0000000000001 else 0.0

    def get_balance_by_account(self, coin = 'BTC', account = 'Vault'):
        """Get balance for a specific account/wallet.

        Fees are already included in buy/sell amounts, not subtracted separately.
        Stake transactions are excluded from the balance, consistent with get_balance().

        Args:
            coin: Currency code (e.g., 'BTC', 'USD')
            account: Wallet/exchange name

        Returns:
            float: Account balance
        """
        return self.wallet_query.get_balance_by_account(coin, account)

    def get_basis(self, coin = 'BTC'):
        """Get the average purchase price (cost basis) for a coin.

        Args:
            coin: Currency code (e.g., 'BTC', 'ETH')

        Returns:
            float or None: Average purchase price in USD, or None if no purchases exist
        """
        return self.basis_calc.get_avg_purchase_price(coin, 'USD')

    def get_transactions(self, coin=None, wallet=None, start_date=None, end_date=None):
        """Get all transactions, optionally filtered by coin, wallet, and date range.

        Args:
            coin: Optional currency code to filter by (e.g., 'BTC', 'ETH')
            wallet: Optional wallet/exchange name(s) to filter by. Can be:
                   - Single string: 'Strike'
                   - List of strings: ['Strike', 'Coldcard']
            start_date: Optional start date (YYYY-MM-DD format or date object)
            end_date: Optional end date (YYYY-MM-DD format or date object)

        Returns:
            tuple: (column_names, transactions)
                - column_names: List of column names
                - transactions: List of transaction dictionaries
        """
        return self.transaction_query.get_transactions(coin, wallet, start_date, end_date)
    def print_trades(self, coin = 'BTC'):
        """Print trade history with cost basis for a coin.

        Args:
            coin: Currency code to display trades for (e.g., 'BTC', 'ETH')
        """
        trades = self.trade_query.get_trade_cost(coin, 'USD')
        # Sort by date descending
        trades_sorted = sorted(trades, key=lambda t: t['date'], reverse=True)

        if not trades_sorted:
            return

        # Print header
        print("date\t\tquantity\tunit_cost\ttotal_cost\texchange")

        # Print each trade
        for trade in trades_sorted:
            date = str(trade['date'])
            quantity = "{:.8f}".format(trade['quantity'])
            unit_cost = "{:.2f}".format(trade['unit_cost']) if trade['unit_cost'] is not None else "N/A"
            total_cost = "{:.2f}".format(trade['total_cost']) if trade['total_cost'] is not None else "N/A"
            exchange = trade.get('exchange', '(Unknown)')
            print(f"{date}\t{quantity}\t{unit_cost}\t{total_cost}\t{exchange}", sep="\t")
    def export_transactions_csv(self, out_file, coin=None, wallet=None, start_date=None, end_date=None):
        """Export transactions to CSV file with optional filtering.

        Args:
            out_file: Output CSV file path
            coin: Optional currency code to filter by (e.g., 'BTC', 'ETH')
            wallet: Optional wallet/exchange name to filter by (e.g., 'Strike', 'Coldcard')
            start_date: Optional start date (YYYY-MM-DD format)
            end_date: Optional end date (YYYY-MM-DD format)
        """
        colnames, transactions = self.get_transactions(coin=coin, wallet=wallet, start_date=start_date, end_date=end_date)
        with open(out_file, 'w', newline='') as csv_out:
            trans_writer = csv.DictWriter(csv_out, fieldnames=colnames)
            trans_writer.writeheader()
            for transaction in transactions:
                trans_writer.writerow(transaction)

    def import_transactions(self, transactions):
        """Import a list of transactions into the ledger.

        Args:
            transactions: List of transaction dicts. Each must have:
                - trans_type: One of Trade, Deposit, Withdrawal, Spend, Interest Income,
                              Mining, Interest, or Staking (last two normalize to Interest Income)
                - created_date: Transaction date string
                - exchange: Exchange/wallet name
                Additional fields vary by type (buy, sell, fee, etc.)

        Returns:
            dict with keys:
                - imported: Number of transactions successfully imported
                - skipped: Number of transactions with unknown trans_type

        Notes:
            - Spend: Like Withdrawal but for payments/UTXO consolidation (not custody transfers)
            - Withdrawal: Transfer to another wallet you control
        """
        imported = 0
        skipped = 0

        for transaction in transactions:
            trans_type = transaction.get('trans_type', '')

            # Normalize Interest/Staking aliases to Interest Income
            if trans_type in ('Interest Income', 'Interest', 'Staking'):
                self.ledger_writer.interest_income(
                    createddate=transaction.get('created_date', ''),
                    buy=transaction.get('buy', 0.0),
                    buy_curr=transaction.get('buy_curr', ''),
                    exchange=transaction.get('exchange', ''),
                    group=transaction.get('group', ''),
                    comment=transaction.get('comment', ''),
                    commit=False
                )
                # Optionally store USD equivalent as price pair for cost basis
                if 'usd_equivalent' in transaction:
                    usd_equiv = transaction['usd_equivalent']
                    try:
                        usd_equiv = float(usd_equiv)
                    except ValueError:
                        # Handle '$1234.56' format by stripping currency symbol
                        usd_equiv = float(str(usd_equiv).lstrip('$').replace(',', ''))
                    buy_amount = float(transaction.get('buy', 0.0))
                    if buy_amount > 0:
                        conv_price = usd_equiv / buy_amount
                        self.backend.execute(self.getPricePairQuery(), {
                            "to_curr": 'USD',
                            "price": conv_price,
                            "from_curr": transaction.get('buy_curr', ''),
                            "date": transaction.get('created_date', ''),
                        })
                imported += 1

            elif trans_type == "Mining":
                self.ledger_writer.mining(
                    createddate=transaction.get('created_date', ''),
                    buy=transaction.get('buy', 0.0),
                    buy_curr=transaction.get('buy_curr', ''),
                    exchange=transaction.get('exchange', ''),
                    group=transaction.get('group', ''),
                    comment=transaction.get('comment', ''),
                    transactionid=transaction.get('transactionid', ''),
                    commit=False
                )
                imported += 1

            elif trans_type == "Deposit":
                self.ledger_writer.deposit(
                    createddate=transaction.get('created_date', ''),
                    buy=transaction.get('buy', 0.0),
                    buy_curr=transaction.get('buy_curr', ''),
                    exchange=transaction.get('exchange', ''),
                    group=transaction.get('group', ''),
                    comment=transaction.get('comment', ''),
                    commit=False
                )
                imported += 1

            elif trans_type == "Withdrawal":
                self.ledger_writer.withdraw(
                    createddate=transaction.get('created_date', ''),
                    sell=transaction.get('sell', 0.0),
                    sell_curr=transaction.get('sell_curr', ''),
                    fee=transaction.get('fee', 0.0),
                    fee_curr=transaction.get('fee_curr', ''),
                    exchange=transaction.get('exchange', ''),
                    group=transaction.get('group', ''),
                    comment=transaction.get('comment', ''),
                    commit=False
                )
                imported += 1

            elif trans_type == "Spend":
                self.ledger_writer.spend(
                    createddate=transaction.get('created_date', ''),
                    sell=transaction.get('sell', 0.0),
                    sell_curr=transaction.get('sell_curr', ''),
                    fee=transaction.get('fee', 0.0),
                    fee_curr=transaction.get('fee_curr', ''),
                    exchange=transaction.get('exchange', ''),
                    group=transaction.get('group', ''),
                    comment=transaction.get('comment', ''),
                    commit=False
                )
                imported += 1

            elif trans_type == "Trade":
                self.ledger_writer.trade(
                    createddate=transaction.get('created_date', ''),
                    buy=transaction.get('buy', 0.0),
                    buy_curr=transaction.get('buy_curr', ''),
                    sell=transaction.get('sell', 0.0),
                    sell_curr=transaction.get('sell_curr', ''),
                    fee=transaction.get('fee', 0.0),
                    fee_curr=transaction.get('fee_curr', ''),
                    exchange=transaction.get('exchange', ''),
                    group=transaction.get('group', ''),
                    comment=transaction.get('comment', ''),
                    commit=False
                )
                imported += 1

            else:
                skipped += 1

        self.backend.commit()
        return {"imported": imported, "skipped": skipped}

    def transfer_funds(self, withdraw_date=None, deposit_date=None, from_account="Strike", tx_coin="BTC", tx_amount=0.0, to_account="Ledger-2", fee_coin="BTC", fee_amount=0.0, comment=""):
        if withdraw_date is None:
            withdraw_date = datetime.now()
        if deposit_date is None:
            delta = timedelta(minutes=10)
            deposit_date = withdraw_date + delta
        if (tx_coin is None or tx_amount is None or from_account is None or to_account is None):
            print("Invalid parameters")
            return
        if (from_account.__contains__(":")):
            from_exchange, from_group = from_account.split(":")
        else:
            from_exchange = from_account
            from_group = None

        if (to_account.__contains__(":")):
            to_exchange, to_group = to_account.split(":")
        else:
            to_exchange = to_account
            to_group = None

        self.ledger_writer.withdraw(
            createddate=str(withdraw_date),
            sell=tx_amount+fee_amount,
            sell_curr=tx_coin,
            fee=fee_amount,
            fee_curr=fee_coin,
            exchange=from_exchange,
            group=from_group or "",
            comment=comment,
            commit=False
        )
        self.ledger_writer.deposit(
            createddate=str(deposit_date),
            buy=tx_amount,
            buy_curr=tx_coin,
            exchange=to_exchange,
            group=to_group or "",
            comment=comment,
            commit=False
        )
        self.backend.commit()

    def deposit(self, deposit_date=None, buy=0, buy_curr="USD", exchange="Strike", group="", comment=""):
        if deposit_date is None:
            deposit_date = datetime.now()
        self.ledger_writer.deposit(deposit_date, buy, buy_curr, exchange, group, comment)

    def withdraw(self, withdraw_date=None, sell=0, sell_curr="USD", fee=0.0, fee_curr="USD", exchange="Strike", group="", comment=""):
        if withdraw_date is None:
            withdraw_date = datetime.now()
        self.ledger_writer.withdraw(withdraw_date, sell, sell_curr, fee, fee_curr, exchange, group, comment)

    def interest(self, interest_date=None, buy=0.0, buy_curr="USD", exchange="River", group="", comment=""):
        if interest_date is None:
            interest_date = datetime.now()
        self.ledger_writer.interest_income(interest_date, buy, buy_curr, exchange, group, comment)

    def execute_trade(self, trade_date=None, buy=0.0, buy_curr="BTC", sell=0.0, sell_curr="USD", fee=0.0, fee_curr="USD",
                      exchange="Strike", group="", comment=""):
        if trade_date is None:
            trade_date = datetime.now()
        self.ledger_writer.trade(trade_date, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange, group, comment)

    def add_price_pair(self, pair_date=None, to_curr="BTC", from_curr="USD", price=0.0):
        if pair_date is None:
            pair_date = datetime.now()
        price_query = self.getPricePairQuery()
        self.backend.execute(price_query, {"to_curr": to_curr, "price": price, "from_curr": from_curr, "date": pair_date})
        self.backend.commit()

    def getPricePairQuery(self):
        return "insert into pair_price (to_curr, price, from_curr, date) values (:to_curr, :price, :from_curr, :date)"

    def get_sales_for_1099b(self, coin='BTC', tax_year=2024, wallet=None):
        """
        Generate 1099-B data for sales of a coin in a given tax year using FIFO cost basis.

        Tax year determines accounting method:
        - Pre-2025: Universal FIFO (wallet parameter optional for user preference)
        - 2025+: Per-wallet FIFO (wallet parameter should be specified for compliance)

        Args:
            coin: Cryptocurrency symbol
            tax_year: Tax year for reporting
            wallet: Optional wallet filter
                    - Pre-2025: Optional (can use global FIFO)
                    - 2025+: Recommended (IRS requires per-wallet accounting)

        Returns:
            tuple: (sales_list, worksheet_list)
            - sales_list: list of dicts formatted for TaxAct 1099-B CSV import
            - worksheet_list: list of dicts with detailed calculation breakdown
        """
        # Validate wallet requirement for 2025+
        if tax_year >= 2025 and wallet is None:
            import warnings
            warnings.warn(
                f"Per-wallet accounting is required for tax year {tax_year} (IRS Rev. Proc. 2024-28). "
                f"Using global FIFO may not be compliant. Consider specifying --wallet parameter.",
                UserWarning
            )

        # Delegate to CapitalGainCalculator
        return self.capital_gains_calc.get_1099b_data(coin, tax_year, wallet)

    def forecast_capital_gains_fifo(self, coin='BTC', quantity=1.0, sale_price_usd=None, wallet=None):
        """
        Forecast capital gains for a hypothetical sale using FIFO basis.

        Does not record any transactions - for planning purposes only.

        Args:
            coin: The cryptocurrency to simulate selling
            quantity: How much to sell
            sale_price_usd: Sale price per unit in USD (if None, uses current market)
            wallet: Optional wallet filter for per-wallet FIFO (2025+ compliance)

        Returns:
            tuple: (lots_list, summary_dict)
            - lots_list: List of lots that would be sold (FIFO order)
            - summary_dict: Summary statistics (totals, short/long breakdown)
        """
        # Delegate to CapitalGainCalculator
        return self.capital_gains_calc.forecast_sale(coin, quantity, sale_price_usd, wallet)

    def get_wallets(self, active_only=False):
        """Get list of all wallets with metadata (if wallets table exists).

        Args:
            active_only: If True, only return active wallets. Default False returns all.
        """
        return self.wallet_query.get_wallets(active_only)
    
    def get_wallet_balance(self, coin='BTC', wallet=None):
        """
        Get balance for a specific wallet, or all wallets if wallet=None.

        Returns:
            If wallet specified: float (balance)
            If wallet=None: dict {wallet_id: balance}
        """
        return self.wallet_query.get_balance_by_wallet(coin, wallet)



