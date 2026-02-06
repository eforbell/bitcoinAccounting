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
        from db import PriceLookup, BalanceCalculator, TradeQuery, BasisCalculator, IncomeQuery
        self.price_lookup = PriceLookup(backend)
        self.balance_calc = BalanceCalculator(backend)
        self.trade_query = TradeQuery(backend, self.price_lookup)
        self.basis_calc = BasisCalculator(self.trade_query)
        self.income_query = IncomeQuery(backend, self.price_lookup)

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
        query = """
            SELECT
                COALESCE(SUM(CASE WHEN buy_curr = :coin AND trans_type != 'Stake' THEN buy ELSE 0 END), 0) -
                COALESCE(SUM(CASE WHEN sell_curr = :coin THEN sell ELSE 0 END), 0)
            FROM ledger
            WHERE exchange = :account
        """
        result = self.backend.execute_scalar(query, {"coin": coin, "account": account})
        balance = float(result) if result is not None else 0.0
        # Return 0 for very small amounts (dust)
        return balance if abs(balance) > 0.0000000000001 else 0.0

    def get_basis(self, coin = 'BTC'):
        """Get the average purchase price (cost basis) for a coin.

        Args:
            coin: Currency code (e.g., 'BTC', 'ETH')

        Returns:
            float or None: Average purchase price in USD, or None if no purchases exist
        """
        return self.basis_calc.get_avg_purchase_price(coin, 'USD')

    def get_bitcoin_price(self):
        import requests

        try:
            # API endpoint for Coingecko to get Bitcoin price in USD
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
            
            # Make the API request
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception for bad status codes
            
            # Parse the JSON response
            data = response.json()
            
            # Extract Bitcoin price
            btc_price = data['bitcoin']['usd']
            
            return btc_price
        
        except requests.exceptions.RequestException as e:
            return f"Error fetching price: {e}"
            
    def get_transactions(self, coin=None, wallet=None, start_date=None, end_date=None):
        """Get all transactions, optionally filtered by coin, wallet, and date range.

        Args:
            coin: Optional currency code to filter by (e.g., 'BTC', 'ETH')
            wallet: Optional wallet/exchange name to filter by (e.g., 'Strike', 'Coldcard')
            start_date: Optional start date (YYYY-MM-DD format)
            end_date: Optional end date (YYYY-MM-DD format)

        Returns:
            tuple: (column_names, transactions)
                - column_names: List of column names
                - transactions: List of transaction dictionaries
        """
        baseQuery = '''select l.trans_type "Type", l.buy "Buy", l.buy_curr "Buy Cur.", l.sell "Sell", l.sell_curr "Sell Cur.", l.fee "Fee", l.fee_curr "Fee Cur.", l.exchange "Exchange", l."group" "Group", l."comment" "Comment", l.createddate "Date" from ledger l'''

        # Build WHERE clause with filters
        where_clauses = []
        params = {}

        if coin is not None:
            where_clauses.append("(l.buy_curr = :coin OR l.sell_curr = :coin OR l.fee_curr = :coin)")
            params['coin'] = coin

        if wallet is not None:
            where_clauses.append("l.exchange = :wallet")
            params['wallet'] = wallet

        if start_date is not None:
            where_clauses.append("l.createddate >= :start_date")
            params['start_date'] = start_date

        if end_date is not None:
            # Include the entire end date by comparing to the start of the next day
            where_clauses.append("l.createddate < date(:end_date, '+1 day')")
            params['end_date'] = end_date

        # Build final query
        if where_clauses:
            query = baseQuery + " WHERE " + " AND ".join(where_clauses) + " ORDER BY createddate ASC, l.id ASC"
        else:
            query = baseQuery + " ORDER BY createddate ASC, l.id ASC"

        rows = self.backend.execute(query, params) if params else self.backend.execute(query)

        transactions = [dict(row) for row in rows]
        colnames = list(transactions[0].keys()) if transactions else []
        return colnames, transactions
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
                - trans_type: One of Trade, Deposit, Withdrawal, Interest Income,
                              Mining, Interest, or Staking (last two normalize to Interest Income)
                - created_date: Transaction date string
                - exchange: Exchange/wallet name
                Additional fields vary by type (buy, sell, fee, etc.)

        Returns:
            dict with keys:
                - imported: Number of transactions successfully imported
                - skipped: Number of transactions with unknown trans_type
        """
        imported = 0
        skipped = 0

        for transaction in transactions:
            trans_type = transaction.get('trans_type', '')

            # Normalize Interest/Staking aliases to Interest Income
            if trans_type in ('Interest Income', 'Interest', 'Staking'):
                query = self.getInterestIncomeQuery()
                self.backend.execute(query, {
                    "createddate": transaction.get('created_date', ''),
                    "buy": transaction.get('buy', 0.0),
                    "buy_curr": transaction.get('buy_curr', ''),
                    "exchange": transaction.get('exchange', ''),
                    "group": transaction.get('group', ''),
                    "comment": transaction.get('comment', ''),
                })
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
                query = self.getMiningQuery()
                self.backend.execute(query, {
                    "createddate": transaction.get('created_date', ''),
                    "buy": transaction.get('buy', 0.0),
                    "buy_curr": transaction.get('buy_curr', ''),
                    "exchange": transaction.get('exchange', ''),
                    "group": transaction.get('group', ''),
                    "comment": transaction.get('comment', ''),
                    "transactionid": transaction.get('transactionid', ''),
                })
                imported += 1

            elif trans_type == "Deposit":
                query = self.getDepositQuery()
                self.backend.execute(query, {
                    "createddate": transaction.get('created_date', ''),
                    "buy": transaction.get('buy', 0.0),
                    "buy_curr": transaction.get('buy_curr', ''),
                    "exchange": transaction.get('exchange', ''),
                    "group": transaction.get('group', ''),
                    "comment": transaction.get('comment', ''),
                })
                imported += 1

            elif trans_type == "Withdrawal":
                query = self.getWithdrawQuery()
                self.backend.execute(query, {
                    "createddate": transaction.get('created_date', ''),
                    "sell": transaction.get('sell', 0.0),
                    "sell_curr": transaction.get('sell_curr', ''),
                    "fee": transaction.get('fee', 0.0),
                    "fee_curr": transaction.get('fee_curr', ''),
                    "exchange": transaction.get('exchange', ''),
                    "group": transaction.get('group', ''),
                    "comment": transaction.get('comment', ''),
                })
                imported += 1

            elif trans_type == "Trade":
                query = self.getTradeQuery()
                self.backend.execute(query, {
                    "createddate": transaction.get('created_date', ''),
                    "buy": transaction.get('buy', 0.0),
                    "buy_curr": transaction.get('buy_curr', ''),
                    "sell": transaction.get('sell', 0.0),
                    "sell_curr": transaction.get('sell_curr', ''),
                    "fee": transaction.get('fee', 0.0),
                    "fee_curr": transaction.get('fee_curr', ''),
                    "exchange": transaction.get('exchange', ''),
                    "group": transaction.get('group', ''),
                    "comment": transaction.get('comment', ''),
                })
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

        withdrawQuery = self.getWithdrawQuery()
        depositQuery = self.getDepositQuery()
        self.backend.execute(withdrawQuery, {
            "createddate": str(withdraw_date),
            "sell": tx_amount+fee_amount,
            "sell_curr": tx_coin,
            "fee": fee_amount,
            "fee_curr": fee_coin,
            "exchange": from_exchange,
            "group": from_group,
            "comment": comment,
        })
        self.backend.execute(depositQuery, {
            "createddate": str(deposit_date),
            "buy": tx_amount,
            "buy_curr": tx_coin,
            "exchange": to_exchange,
            "group": to_group,
            "comment": comment,
        })
        self.backend.commit()

    def deposit(self, deposit_date=None, buy=0, buy_curr="USD", exchange="Strike", group="", comment=""):
        if deposit_date is None:
            deposit_date = datetime.now()
        self.backend.execute(
            self.getDepositQuery(),
            {"createddate": deposit_date, "buy": buy, "buy_curr": buy_curr, "exchange": exchange, "group": group, "comment": comment})
        self.backend.commit()

    def withdraw(self, withdraw_date=None, sell=0, sell_curr="USD", fee=0.0, fee_curr="USD", exchange="Strike", group="", comment=""):
        if withdraw_date is None:
            withdraw_date = datetime.now()
        self.backend.execute(
            self.getWithdrawQuery(),
            {"createddate": withdraw_date, "sell": sell, "sell_curr": sell_curr, "fee": fee, "fee_curr": fee_curr, "exchange": exchange, "group": group, "comment": comment})
        self.backend.commit()

    def interest(self, interest_date=None, buy=0.0, buy_curr="USD", exchange="River", group="", comment=""):
        if interest_date is None:
            interest_date = datetime.now()
        self.backend.execute(
            self.getInterestIncomeQuery(),
            {"createddate": interest_date, "buy": buy, "buy_curr": buy_curr, "exchange": exchange, "group": group, "comment": comment})
        self.backend.commit()

    def execute_trade(self, trade_date=None, buy=0.0, buy_curr="BTC", sell=0.0, sell_curr="USD", fee=0.0, fee_curr="USD",
                      exchange="Strike", group="", comment=""):
        if trade_date is None:
            trade_date = datetime.now()
        self.backend.execute(
            self.getTradeQuery(),
            {"createddate": trade_date, "buy": buy, "buy_curr": buy_curr, "sell": sell, "sell_curr": sell_curr, "fee": fee, "fee_curr": fee_curr, "exchange": exchange, "group": group, "comment": comment})
        self.backend.commit()

    def add_price_pair(self, pair_date=None, to_curr="BTC", from_curr="USD", price=0.0):
        if pair_date is None:
            pair_date = datetime.now()
        price_query = self.getPricePairQuery()
        self.backend.execute(price_query, {"to_curr": to_curr, "price": price, "from_curr": from_curr, "date": pair_date})
        self.backend.commit()

    def getDepositQuery(self):
        return "insert into ledger (createddate, trans_type, buy, buy_curr, exchange, \"group\", comment) values (:createddate, 'Deposit', :buy, :buy_curr, :exchange, :group, :comment)"

    def getWithdrawQuery(self):
        return "insert into ledger (createddate, trans_type, sell, sell_curr, fee, fee_curr, exchange, \"group\", comment) values (:createddate, 'Withdrawal', :sell, :sell_curr, :fee, :fee_curr, :exchange, :group, :comment)"

    def getInterestIncomeQuery(self):
        return "insert into ledger (createddate, trans_type, buy, buy_curr, exchange, \"group\", comment) values (:createddate, 'Interest Income', :buy, :buy_curr, :exchange, :group, :comment)"

    def getMiningQuery(self):
        return "insert into ledger (createddate, trans_type, buy, buy_curr, exchange, \"group\", comment, transactionid) values (:createddate, 'Mining', :buy, :buy_curr, :exchange, :group, :comment, :transactionid)"

    def getTradeQuery(self):
        return "insert into ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange, \"group\", comment) values (:createddate, 'Trade', :buy, :buy_curr, :sell, :sell_curr, :fee, :fee_curr, :exchange, :group, :comment)"

    def getPricePairQuery(self):
        return "insert into pair_price (to_curr, price, from_curr, date) values (:to_curr, :price, :from_curr, :date)"

    def _get_purchase_lots(self, coin='BTC', wallet=None):
        """Get all purchase lots (trades and interest) for a coin, optionally filtered by wallet.

        Returns a list of tuples sorted by date: (date, quantity, unit_cost, total_cost, exchange)

        Args:
            coin: Cryptocurrency symbol
            wallet: Optional wallet filter

        Returns:
            list: Purchase lots as tuples (date, quantity, unit_cost, total_cost, exchange)
        """
        # Get all purchases (trades) with cost basis using TradeQuery
        all_trade_costs = self.trade_query.get_trade_cost(coin, 'USD')

        # Filter to purchases only (quantity > 0) and apply wallet filter
        if wallet:
            trade_purchases = [
                (t['date'], t['quantity'], t['unit_cost'] or 0, t['total_cost'] or 0, t.get('exchange', ''))
                for t in all_trade_costs
                if t['quantity'] > 0 and t.get('exchange') == wallet
            ]
        else:
            trade_purchases = [
                (t['date'], t['quantity'], t['unit_cost'] or 0, t['total_cost'] or 0, t.get('exchange', ''))
                for t in all_trade_costs
                if t['quantity'] > 0
            ]

        # Get interest income using IncomeQuery
        all_interest = self.income_query.get_interest_income(coin, 'USD')

        # Apply wallet filter if specified
        if wallet:
            interest_purchases = [
                (i['date'], i['to_quantity'], i['unit_cost'] or 0, i['total_cost'] or 0, i.get('exchange', ''))
                for i in all_interest
                if i.get('exchange') == wallet
            ]
        else:
            interest_purchases = [
                (i['date'], i['to_quantity'], i['unit_cost'] or 0, i['total_cost'] or 0, i.get('exchange', ''))
                for i in all_interest
            ]

        # Combine and sort all purchases by date
        all_purchases = list(trade_purchases) + list(interest_purchases)
        all_purchases.sort(key=lambda x: x[0])  # Sort by date
        return all_purchases

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
        from datetime import datetime

        # Validate wallet requirement for 2025+
        if tax_year >= 2025 and wallet is None:
            import warnings
            warnings.warn(
                f"Per-wallet accounting is required for tax year {tax_year} (IRS Rev. Proc. 2024-28). "
                f"Using global FIFO may not be compliant. Consider specifying --wallet parameter.",
                UserWarning
            )

        # Get all purchases using helper method
        all_purchases = self._get_purchase_lots(coin, wallet)

        # Need trade costs for proceeds lookup later
        all_trade_costs = self.trade_query.get_trade_cost(coin, 'USD')

        # Get ALL sales through the end of the tax year using TradeQuery
        # This is critical for FIFO: we must account for all prior year sales that
        # consumed the purchase queue before we calculate basis for the current tax year
        tax_year_end = datetime(tax_year, 12, 31, 23, 59, 59)
        sales_data = self.trade_query.get_sales(coin, str(tax_year_end), wallet)

        # Convert to tuple format for compatibility with existing logic
        sales = [(s['createddate'], s['quantity'], s['exchange'], s['id']) for s in sales_data]
        
        if not sales:
            return [], []
        
        # Build purchase queue for FIFO matching
        purchase_queue = []
        for purchase in all_purchases:
            purchase_date, quantity, unit_cost, total_cost, exchange = purchase

            # Parse date if it's a string (from SQLite)
            if isinstance(purchase_date, str):
                purchase_date = datetime.fromisoformat(purchase_date.replace('Z', '+00:00'))

            # unit_cost and total_cost are already calculated
            unit_cost_val = float(unit_cost) if unit_cost else 0.0

            purchase_queue.append({
                'date': purchase_date,
                'quantity_remaining': float(quantity),
                'unit_cost': unit_cost_val,
                'exchange': exchange
            })
        
        # Process each sale using FIFO
        # We process ALL sales chronologically to properly consume the FIFO queue,
        # but only output 1099-B entries for sales within the specific tax year
        results = []
        worksheet = []
        tax_year_start = datetime(tax_year, 1, 1, 0, 0, 0)
        
        for sale in sales:
            sale_date, sale_quantity, sale_exchange, sale_id = sale
            sale_quantity = float(sale_quantity)

            # Parse date if it's a string (from SQLite)
            if isinstance(sale_date, str):
                sale_date = datetime.fromisoformat(sale_date.replace('Z', '+00:00'))

            # Check if this sale is within the tax year we're reporting
            sale_in_tax_year = (sale_date >= tax_year_start and sale_date <= tax_year_end)
            
            # Get proceeds only if we need to report this sale
            if sale_in_tax_year:
                # Get proceeds (what we sold the coin for in USD) using TradeQuery
                # Find this specific sale in the trade cost data
                sale_found = False
                for t in all_trade_costs:
                    t_date = t['date']
                    if isinstance(t_date, str):
                        t_date = datetime.fromisoformat(t_date.replace('Z', '+00:00'))

                    if t_date == sale_date and t['quantity'] < 0:
                        proceeds_total = abs(float(t['total_cost'])) if t['total_cost'] is not None else 0.0
                        proceeds_per_unit = abs(float(t['unit_cost'])) if t['unit_cost'] is not None else 0.0
                        sale_found = True
                        break

                if not sale_found:
                    # Fallback: use price lookup - convert datetime to string for price lookup
                    proceeds_per_unit = self.price_lookup.get_price(coin, 'USD', sale_date.isoformat() if isinstance(sale_date, datetime) else sale_date)
                    if proceeds_per_unit is not None:
                        proceeds_total = sale_quantity * proceeds_per_unit
                    else:
                        proceeds_per_unit = 0.0
                        proceeds_total = 0.0
            
            # Match this sale with purchases using FIFO
            quantity_to_match = sale_quantity
            matched_purchases = []
            
            for purchase in purchase_queue:
                if quantity_to_match <= 0:
                    break
                
                if purchase['quantity_remaining'] > 0:
                    # Determine how much of this purchase applies to this sale
                    match_quantity = min(quantity_to_match, purchase['quantity_remaining'])
                    
                    matched_purchases.append({
                        'acquire_date': purchase['date'],
                        'quantity': match_quantity,
                        'unit_cost': purchase['unit_cost'],
                        'cost_basis': match_quantity * purchase['unit_cost']
                    })
                    
                    purchase['quantity_remaining'] -= match_quantity
                    quantity_to_match -= match_quantity
            
            # Check if there's unmatched quantity (missing basis)
            if quantity_to_match > 0.00000001:  # Allow for floating point precision
                # Add entry for unmatched quantity with $0 basis
                matched_purchases.append({
                    'acquire_date': None,  # Unknown acquisition date
                    'quantity': quantity_to_match,
                    'unit_cost': 0.0,
                    'cost_basis': 0.0
                })
            
            # Create 1099-B entries (one per purchase lot matched)
            # But only for sales within the tax year we're reporting
            if sale_in_tax_year:
                for match in matched_purchases:
                    # Handle missing basis (no acquisition date)
                    if match['acquire_date'] is None:
                        acquire_date_str = 'UNKNOWN'
                        holding_days = 0
                        term = 'Short'  # Conservative: report as short-term
                    else:
                        acquire_date_str = match['acquire_date'].strftime('%m/%d/%Y')
                        holding_days = (sale_date - match['acquire_date']).days
                        term = 'Long' if holding_days >= 365 else 'Short'
                    
                    # Calculate proportional proceeds for this lot
                    lot_proceeds = (match['quantity'] / sale_quantity) * proceeds_total
                    gain_loss = lot_proceeds - match['cost_basis']
                    
                    # Add to 1099-B form output
                    result = {
                        'Description': f"{match['quantity']:.8f} {coin}",
                        'Date Acquired': acquire_date_str,
                        'Date Sold': sale_date.strftime('%m/%d/%Y'),
                        'Proceeds': f"{lot_proceeds:.2f}",
                        'Cost Basis': f"{match['cost_basis']:.2f}",
                        'Adjustment Code': '',
                        'Adjustment Amount': '',
                        'Wash Sale Loss': '',
                        'Form': '8949',
                        'Term': term
                    }
                    results.append(result)
                    
                    # Add to detailed worksheet
                    worksheet_entry = {
                        'Sale Date': sale_date.strftime('%m/%d/%Y'),
                        'Sale Quantity': f"{sale_quantity:.8f}",
                        'Proceeds': f"{lot_proceeds:.2f}",
                        'Acquire Date': acquire_date_str,
                        'Lot Quantity': f"{match['quantity']:.8f}",
                        'Unit Cost Basis': f"{match['unit_cost']:.2f}",
                        'Total Cost Basis': f"{match['cost_basis']:.2f}",
                        'Holding Days': str(holding_days) if match['acquire_date'] else 'UNKNOWN',
                        'Term': term,
                        'Gain/Loss': f"{gain_loss:.2f}"
                    }
                    worksheet.append(worksheet_entry)
        
        return results, worksheet

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
        from datetime import datetime

        # Get all purchases using helper method
        all_purchases = self._get_purchase_lots(coin, wallet)

        if not all_purchases:
            return [], {}

        # Get all historical sales using TradeQuery
        sales_data = self.trade_query.get_sales(coin, wallet=wallet)
        historical_sales = [(s['createddate'], s['quantity'], s['exchange'], s['id']) for s in sales_data]
        
        # Build purchase queue
        purchase_queue = []
        for purchase in all_purchases:
            purchase_date, qty, unit_cost, total_cost, exchange = purchase

            # Parse date if it's a string (from SQLite)
            if isinstance(purchase_date, str):
                purchase_date = datetime.fromisoformat(purchase_date.replace('Z', '+00:00'))

            unit_cost_val = float(unit_cost) if unit_cost else 0.0

            purchase_queue.append({
                'date': purchase_date,
                'quantity_remaining': float(qty),
                'unit_cost': unit_cost_val,
                'exchange': exchange
            })
        
        # Process historical sales to consume the queue
        for sale in historical_sales:
            sale_date, sale_quantity, sale_exchange, sale_id = sale
            sale_quantity = float(sale_quantity)
            quantity_to_match = sale_quantity

            for purchase in purchase_queue:
                if quantity_to_match <= 0:
                    break

                if purchase['quantity_remaining'] > 0:
                    match_quantity = min(quantity_to_match, purchase['quantity_remaining'])
                    purchase['quantity_remaining'] -= match_quantity
                    quantity_to_match -= match_quantity
        
        # Now simulate the hypothetical sale
        sale_date = datetime.now()
        quantity_to_sell = float(quantity)
        quantity_remaining = quantity_to_sell
        lots = []
        
        for purchase in purchase_queue:
            if quantity_remaining <= 0:
                break
            
            if purchase['quantity_remaining'] > 0:
                match_quantity = min(quantity_remaining, purchase['quantity_remaining'])
                holding_days = (sale_date - purchase['date']).days
                term = 'Long' if holding_days >= 365 else 'Short'
                
                lots.append({
                    'acquire_date': purchase['date'],
                    'quantity': match_quantity,
                    'unit_cost': purchase['unit_cost'],
                    'cost_basis': match_quantity * purchase['unit_cost'],
                    'holding_days': holding_days,
                    'term': term
                })
                
                quantity_remaining -= match_quantity
        
        # Handle missing basis
        if quantity_remaining > 0.00000001:
            lots.append({
                'acquire_date': None,
                'quantity': quantity_remaining,
                'unit_cost': 0.0,
                'cost_basis': 0.0,
                'holding_days': 0,
                'term': 'Short'
            })
        
        # Calculate summary statistics
        total_cost_basis = sum(lot['cost_basis'] for lot in lots)
        total_quantity = sum(lot['quantity'] for lot in lots)
        
        short_term_lots = [lot for lot in lots if lot['term'] == 'Short']
        long_term_lots = [lot for lot in lots if lot['term'] == 'Long']
        missing_basis_lots = [lot for lot in lots if lot['acquire_date'] is None]
        
        short_term_quantity = sum(lot['quantity'] for lot in short_term_lots)
        long_term_quantity = sum(lot['quantity'] for lot in long_term_lots)
        missing_basis_quantity = sum(lot['quantity'] for lot in missing_basis_lots)
        
        short_term_cost = sum(lot['cost_basis'] for lot in short_term_lots)
        long_term_cost = sum(lot['cost_basis'] for lot in long_term_lots)
        
        # Calculate proportional proceeds
        if sale_price_usd:
            total_proceeds = quantity_to_sell * sale_price_usd
            short_term_proceeds = short_term_quantity * sale_price_usd
            long_term_proceeds = long_term_quantity * sale_price_usd
        else:
            total_proceeds = 0
            short_term_proceeds = 0
            long_term_proceeds = 0
        
        summary = {
            'total_quantity': total_quantity,
            'total_cost_basis': total_cost_basis,
            'total_proceeds': total_proceeds,
            'short_term_count': len(short_term_lots),
            'short_term_quantity': short_term_quantity,
            'short_term_cost': short_term_cost,
            'short_term_proceeds': short_term_proceeds,
            'long_term_count': len(long_term_lots),
            'long_term_quantity': long_term_quantity,
            'long_term_cost': long_term_cost,
            'long_term_proceeds': long_term_proceeds,
            'missing_basis_count': len(missing_basis_lots),
            'missing_basis_quantity': missing_basis_quantity
        }
        
        return lots, summary

    def get_wallets(self, active_only=False):
        """Get list of all wallets with metadata (if wallets table exists).

        Args:
            active_only: If True, only return active wallets. Default False returns all.
        """
        # Check if wallets table exists (backend-specific)
        from db import SqliteBackend
        if isinstance(self.backend, SqliteBackend):
            # SQLite: check sqlite_master
            check_query = """
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='table' AND name='wallets'
            """
        else:
            # PostgreSQL: check information_schema
            check_query = """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'wallets'
            """

        table_exists = self.backend.execute_scalar(check_query) > 0

        if table_exists:
            # Get wallet metadata from wallets table
            active_filter = "WHERE active = 1" if active_only else ""  # Use 1 for boolean (works in both backends)
            query = f"""
                SELECT wallet_id, wallet_type, custody, description, active
                FROM wallets
                {active_filter}
                ORDER BY wallet_id
            """
            rows = self.backend.execute(query)
            return [{'wallet_id': row['wallet_id'], 'type': row['wallet_type'], 'custody': row['custody'],
                    'description': row['description'], 'active': row['active']}
                   for row in rows]
        else:
            # Fallback: get distinct exchange values from ledger
            query = """
                SELECT DISTINCT exchange
                FROM ledger
                WHERE exchange IS NOT NULL
                ORDER BY exchange
            """
            rows = self.backend.execute(query)
            return [{'wallet_id': row['exchange'], 'type': 'unknown', 'custody': 'unknown',
                    'description': None, 'active': True}
                   for row in rows]
    
    def get_wallet_balance(self, coin='BTC', wallet=None):
        """
        Get balance for a specific wallet, or all wallets if wallet=None.

        Returns:
            If wallet specified: float (balance)
            If wallet=None: dict {wallet_id: balance}
        """
        if wallet:
            # Balance for specific wallet - use get_balance_by_account
            return self.get_balance_by_account(coin, wallet)
        else:
            # Balance for all wallets
            # Note: Fees are already included in buy/sell amounts, not subtracted separately
            query = """
                SELECT
                    exchange,
                    COALESCE(SUM(CASE WHEN buy_curr = :coin THEN buy ELSE 0 END), 0) -
                    COALESCE(SUM(CASE WHEN sell_curr = :coin THEN sell ELSE 0 END), 0) as balance
                FROM ledger
                WHERE exchange IS NOT NULL
                GROUP BY exchange
                ORDER BY exchange
            """
            rows = self.backend.execute(query, {"coin": coin})
            return {row['exchange']: float(row['balance']) for row in rows}



