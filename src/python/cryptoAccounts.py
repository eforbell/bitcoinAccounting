import psycopg2
import csv
from datetime import datetime, timedelta

now = datetime.now()

class CryptoAccounts(object):

    def __init__(self):
        # Use config.connect() to centralize DB credentials and allow environment overrides
        from config import connect
        self.connection = connect()


    def close(self):
        self.connection.close()

    def get_balance(self, coin = 'BTC'):
        cur = self.connection.cursor()
        query = "select get_balance('" + coin + "')"
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            returnVal = row[0]
            if abs(float(returnVal))-0.0000000000001 > 0:
                return returnVal
            else:
                return 0

    def get_balance_by_account(self, coin = 'BTC', account = 'Vault'):
        cur = self.connection.cursor()
        query = "select get_balance_by_account('" + coin + "', '" + account + "')"
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            returnVal = row[0]
            if abs(float(returnVal))-0.0000000000001 > 0:
                return returnVal
            else:
                return 0

    def get_basis(self, coin = 'BTC'):
        cur = self.connection.cursor()
        query = "select get_avg_purchase_price('" + coin + "')"
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            return row[0]

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
            
    def get_transactions(self, coin = None):
        cur = self.connection.cursor()
        baseQuery = "select l.trans_type \"Type\", l.buy \"Buy\", l.buy_curr \"Buy Cur.\", l.sell \"Sell\", l.sell_curr \"Sell Cur.\", l.fee \"Fee\", l.fee_curr \"Fee Cur.\", l.exchange \"Exchange\", l.\"group\" \"Group\", l.\"comment\" \"Comment\", l.createddate \"Date\" from ledger l"
        if coin is not None:
            cur.execute(baseQuery + " where l.buy_curr = %s or l.sell_curr = %s order by createddate", (coin, coin))
        else:
            cur.execute(baseQuery + " order by createddate")
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
        transactions = []
        for row in rows:
            transaction = {}
            for i, colname in enumerate(colnames):
                transaction[colname] = row[i]
            transactions.append(transaction)
        return colnames, transactions
    def print_trades(self, coin = 'BTC'):
        cur = self.connection.cursor()
        baseQuery = "select date, quantity, unit_cost, total_cost, exchange from get_trade_cost_new(%s, %s)  order by date desc"
        cur.execute(baseQuery, (coin, 'USD'))
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        #for col in colnames:
        #    print(col, end=" ")
        #print()
        print(str(cols[0])+"\t\t",cols[1],cols[2],cols[3],cols[4],sep="\t")
        for row in rows:
           quantity = "{:.8f}".format(row[1])
           cost = "{:.2f}".format(row[2])
           total_cost = "{:.2f}".format(row[3])+"\t"
           if len(row) > 4:
               exchange = row[4]
           else:
               exchange = "(Unknown)"
           print(str(row[0]),quantity,cost,total_cost,exchange,sep="\t")
    def export_transactions_csv(self, out_file, coin = None):
        colnames, transactions = self.get_transactions(coin)
        with open(out_file, 'w', newline='') as csv_out:
            trans_writer = csv.DictWriter(csv_out, fieldnames=colnames)
            trans_writer.writeheader()
            for transaction in transactions:
                trans_writer.writerow(transaction)

    def import_transactions(self, colnames, transactions):
        cur = self.connection.cursor()
        for transaction in transactions:
            if transaction['trans_type'] == "Interest Income" or transaction['trans_type'] == "Interest" or transaction['trans_type'] == 'Staking':
                query = self.getInterestIncomeQuery()
                transaction['trans_type'] = "Interest Income"
                cur.execute(query, (transaction['created_date'], transaction['buy'], transaction['buy_curr'], transaction['exchange'], transaction['group'],transaction['comment']))
                price_query = self.getPricePairQuery()
                if 'usd_equivalent' in transaction:
                    usd_equiv = transaction['usd_equivalent']
                    try:
                        usd_equiv = float(usd_equiv)
                    except(ValueError):
                        usd_equiv = float(usd_equiv[1:])
                    conv_price = float(usd_equiv)/float(transaction['buy'])
                    cur.execute(price_query, ('USD', conv_price, transaction['buy_curr'], transaction['created_date']));
            elif transaction['trans_type'] == "Mining":
                query = self.getMiningQuery()
                cur.execute(query, (transaction['created_date'], transaction['buy'], transaction['buy_curr'], transaction['exchange'], transaction['group'], transaction['transactionid']))
            elif transaction['trans_type'] == "Deposit":
                query = self.getDepositQuery()
            elif transaction['trans_type'] == "Withdrawal":
                query = self.getWithdrawQuery()
        self.connection.commit()

    def import_transactions_rvn_mining(self, in_file):
        colnames = ['Confirmed','Date','Type','Label','Address','Amount (RVN)','Asset','ID']
        with open(in_file, 'r') as csv_in:
            rvn_input = csv.DictReader(csv_in, fieldnames=colnames)
            transactions = []
            rowNum = 0
            for row in rvn_input:
                rowNum += 1
                transaction = {}
                if rowNum == 1:
                    continue
                transaction['exchange'] = 'RVNMiningWallet'
                if row['Label'] == 'Mining':
                    transaction['trans_type'] = "Mining"
                    transaction['created_date'] = row['Date']
                    transaction['buy_curr'] = 'RVN'
                    transaction['buy'] = row['Amount (RVN)']
                    transaction['transactionid'] = row['ID']
                    transaction['group'] = 'Ravenminer'
                else:
                    continue
                transactions.append(transaction)
        return colnames, transactions

    def import_transactions_nexo_csv(self, in_file):
        colnames = ['transactionId','trans_type','buy_curr','buy','usd_equivalent','comment','Outstanding Loan', 'created_date']
        with open(in_file, 'r') as csv_in:
            nexo_input = csv.DictReader(csv_in, fieldnames=colnames)
            transactions = []
            rowNum = 0
            for row in nexo_input:
                rowNum += 1
                transaction = {}
                if rowNum == 1:
                    continue
                for i, colname in enumerate(colnames):
                    transaction[colname] = row[colname]
                if (transaction['buy_curr'] == 'NEXOBNB'):
                    transaction['buy_curr'] = 'BNB'
                elif (transaction['buy_curr'] == 'NEXONEXO'):
                    transaction['buy_curr'] = 'NEXO'
                elif (transaction['buy_curr'] == 'BNBN'):
                    transaction['buy_curr'] = 'BNB'
                elif (transaction['buy_curr'] == 'NEXOBEP2'):
                    transaction['buy_curr'] = 'NEXO'
                transaction['exchange'] = 'Nexo'
                transaction['group'] = None
                transactions.append(transaction)
        return colnames, transactions

    def import_transactions_ada_csv(self, in_file):
        colnames = ['trans_type','buy','buy_curr','sell','sell_cur','fee','fee_curr', 'exchange','group','comment','created_date']
        with open(in_file, 'r') as csv_in:
            ada_input = csv.DictReader(csv_in, fieldnames=colnames)
            transactions = []
            rowNum = 0
            for row in ada_input:
                if row['exchange'] == 'Cardano Protocol':
                    row['exchange'] = 'Ledger'
                rowNum += 1
                if rowNum == 1:
                    continue
                transactions.append(row)

        return colnames, transactions

    def import_transactions_ledger_csv(self, in_file):
        colnames = ['created_date','curr','op_type','value','fee','hash','account name','xpub','cost_currency','cost','cost_at_export']
        with open(in_file, 'r') as csv_in:
            ledger_live_input = csv.DictReader(csv_in, fieldnames=colnames)
            transactions = []
            rowNum = 0
            for row in ledger_live_input:
                rowNum += 1
                transaction = {}
                if rowNum == 1:
                    continue
                #for i, colname in enumerate(colnames):
                if (row['op_type'] == 'IN' and row['curr'] == 'ALGO' and row['fee'] == '0' and row['value'] != '0'): #reward
                    transaction['buy_curr'] = row['curr']
                    transaction['buy'] = row['value']
                    transaction['trans_type'] = 'Interest Income'
                    transaction['created_date'] = row['created_date']
                    transaction['comment'] = 'Reward'
                    transaction['usd_equivalent'] = row['cost']
                else:
                    continue
                transaction['exchange'] = 'Ledger'
                transaction['group'] = None
                transactions.append(transaction)
        return colnames, transactions


    def transfer_funds(self, withdraw_date= datetime.now(), deposit_date = None, from_account="Strike", tx_coin="BTC", tx_amount=0.0, to_account="Ledger-2", fee_coin="BTC", fee_amount=0.0):
        if (deposit_date is None):
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
        depositQuery =  self.getDepositQuery()
        cur = self.connection.cursor()
        cur.execute(withdrawQuery, (str(withdraw_date), tx_amount+fee_amount, tx_coin, fee_amount, fee_coin, from_exchange, from_group))
        cur.execute(depositQuery, (str(deposit_date), tx_amount, tx_coin, to_exchange, to_group))
        self.connection.commit()

    def deposit(self, deposit_date=now, buy=0, buy_curr="USD", exchange="Strike", group=""):
        cur = self.connection.cursor()
        cur.execute(
            self.getDepositQuery(),
            (deposit_date, buy, buy_curr, exchange, group))
        self.connection.commit()

    def withdraw(self, withdraw_date=now, sell=0, sell_curr="USD", fee=0.0, fee_curr="USD", exchange="Strike", group=""):
        cur = self.connection.cursor()
        cur.execute(
            self.getWithdrawQuery(),
            (withdraw_date, sell, sell_curr, fee, fee_curr, exchange, group))
        self.connection.commit()

    def interest(self, interest_date=now, buy=0.0, buy_curr="USD", exchange="River", group=""):
        cur = self.connection.cursor()
        cur.execute(
            self.getInterestIncomeQuery(),
            (interest_date, buy, buy_curr, exchange, group))
        self.connection.commit()

    def execute_trade(self, trade_date=now, buy=0.0, buy_curr="BTC", sell=0.0, sell_curr="USD", fee=0.0, fee_curr="USD",
                      exchange="Strike", group=""):
        cur = self.connection.cursor()
        cur.execute(
            self.getTradeQuery(),
            (trade_date, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange, group))
        self.connection.commit()

    def add_price_pair(self, pair_date=now, to_curr="BTC", from_curr="USD", price=0.0):
        cur = self.connection.cursor()
        price_query = self.getPricePairQuery()
        cur.execute(price_query, (from_curr, price, to_curr, pair_date));
        self.connection.commit()

    def getDepositQuery(self):
        return "insert into ledger (createddate, trans_type, buy, buy_curr, exchange, \"group\") values (%s, 'Deposit', %s, %s, %s, %s)"

    def getWithdrawQuery(self):
        return "insert into ledger (createddate, trans_type, sell, sell_curr, fee, fee_curr, exchange, \"group\") values (%s, 'Withdrawal', %s, %s, %s, %s, %s, %s)"

    def getInterestIncomeQuery(self):
        return "insert into ledger (createddate, trans_type, buy, buy_curr, exchange, \"group\", \"comment\") values (%s, 'Interest Income', %s, %s, %s, %s, %s)"

    def getMiningQuery(self):
        return "insert into ledger (createddate, trans_type, buy, buy_curr, exchange, \"group\", transactionid) values (%s, 'Mining', %s, %s, %s, %s, %s)"

    def getTradeQuery(self):
        return "insert into ledger (createddate, trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange, \"group\") values (%s, 'Trade', %s, %s, %s, %s, %s, %s, %s, %s)"

    def getPricePairQuery(self):
        return "insert into pair_price (to_curr, price, from_curr, date) values (%s, %s, %s, %s)"

    def getInterestIncomeQuery(self):
        return "insert into ledger (createddate, trans_type, buy, buy_curr, exchange, \"group\") values (%s, 'Interest Income', %s, %s, %s, %s)"

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
        from decimal import Decimal
        
        # Validate wallet requirement for 2025+
        if tax_year >= 2025 and wallet is None:
            import warnings
            warnings.warn(
                f"Per-wallet accounting is required for tax year {tax_year} (IRS Rev. Proc. 2024-28). "
                f"Using global FIFO may not be compliant. Consider specifying --wallet parameter.",
                UserWarning
            )
        
        cur = self.connection.cursor()
        
        # Get all purchases (trades) with cost basis calculated using get_trade_cost_new
        # Filter by wallet if specified for per-wallet FIFO
        wallet_filter_sql = "AND exchange = %s" if wallet else ""
        trade_purchase_query = f"""
            SELECT date, quantity, unit_cost, total_cost, exchange
            FROM get_trade_cost_new(%s, 'USD')
            WHERE quantity > 0 {wallet_filter_sql}
            ORDER BY date ASC
        """
        
        # Get interest income separately (not included in get_trade_cost_new)
        interest_purchase_query = f"""
            SELECT l.createddate as date, l.buy as quantity, 
                   COALESCE(pp.price, 0) as unit_cost,
                   COALESCE(l.buy * pp.price, 0) as total_cost,
                   l.exchange
            FROM ledger l
            LEFT JOIN pair_price pp ON pp.from_curr = l.buy_curr 
                AND pp.to_curr = 'USD' 
                AND pp.date::date = l.createddate::date
            WHERE l.buy_curr = %s 
                AND l.trans_type = 'Interest Income'
                AND l.buy > 0
                {wallet_filter_sql}
            ORDER BY l.createddate ASC
        """
        
        # Get ALL sales through the end of the tax year (not just sales IN the tax year)
        # This is critical for FIFO: we must account for all prior year sales that
        # consumed the purchase queue before we calculate basis for the current tax year
        sale_query = f"""
            SELECT createddate, sell as quantity, exchange, id
            FROM ledger
            WHERE sell_curr = %s 
                AND trans_type = 'Trade'
                AND sell > 0
                AND createddate <= %s
                {wallet_filter_sql}
            ORDER BY createddate ASC
        """
        
        # Execute queries with wallet parameter if specified
        if wallet:
            cur.execute(trade_purchase_query, (coin, wallet))
            trade_purchases = cur.fetchall()
            
            cur.execute(interest_purchase_query, (coin, wallet))
            interest_purchases = cur.fetchall()
        else:
            cur.execute(trade_purchase_query, (coin,))
            trade_purchases = cur.fetchall()
            
            cur.execute(interest_purchase_query, (coin,))
            interest_purchases = cur.fetchall()
        
        # Combine and sort all purchases by date
        all_purchases = list(trade_purchases) + list(interest_purchases)
        all_purchases.sort(key=lambda x: x[0])  # Sort by date
        
        # Get sales through end of tax year
        tax_year_end = datetime(tax_year, 12, 31, 23, 59, 59)
        if wallet:
            cur.execute(sale_query, (coin, tax_year_end, wallet))
        else:
            cur.execute(sale_query, (coin, tax_year_end))
        sales = cur.fetchall()
        
        if not sales:
            return [], []
        
        # Build purchase queue for FIFO matching
        purchase_queue = []
        for purchase in all_purchases:
            purchase_date, quantity, unit_cost, total_cost, exchange = purchase
            
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
            
            # Check if this sale is within the tax year we're reporting
            sale_in_tax_year = (sale_date >= tax_year_start and sale_date <= tax_year_end)
            
            # Get proceeds only if we need to report this sale
            if sale_in_tax_year:
                # Get proceeds (what we sold the coin for in USD)
                proceeds_query = """
                    SELECT unit_cost, total_cost
                    FROM get_trade_cost_new(%s, 'USD')
                    WHERE date = %s AND quantity < 0
                    LIMIT 1
                """
                cur.execute(proceeds_query, (coin, sale_date))
                proceeds_result = cur.fetchone()
                
                if proceeds_result and proceeds_result[1]:
                    proceeds_total = abs(float(proceeds_result[1]))
                    proceeds_per_unit = abs(float(proceeds_result[0]))
                else:
                    # Try pair_price as fallback
                    price_query = """
                        SELECT price FROM pair_price
                        WHERE to_curr = 'USD' AND from_curr = %s
                            AND date::date = %s::date
                        LIMIT 1
                    """
                    cur.execute(price_query, (coin, sale_date))
                    price_result = cur.fetchone()
                    proceeds_per_unit = float(price_result[0]) if price_result else 0.0
                    proceeds_total = sale_quantity * proceeds_per_unit
            
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
        
        cur = self.connection.cursor()
        
        # Build wallet filter clause
        wallet_filter_sql = "AND exchange = %s" if wallet else ""
        
        # Get all purchases (same logic as 1099-B export)
        trade_purchase_query = f"""
            SELECT date, quantity, unit_cost, total_cost, exchange
            FROM get_trade_cost_new(%s, 'USD')
            WHERE quantity > 0 {wallet_filter_sql}
            ORDER BY date ASC
        """
        
        interest_purchase_query = f"""
            SELECT l.createddate as date, l.buy as quantity, 
                   COALESCE(pp.price, 0) as unit_cost,
                   COALESCE(l.buy * pp.price, 0) as total_cost,
                   l.exchange
            FROM ledger l
            LEFT JOIN pair_price pp ON pp.from_curr = l.buy_curr 
                AND pp.to_curr = 'USD' 
                AND pp.date::date = l.createddate::date
            WHERE l.buy_curr = %s 
                AND l.trans_type = 'Interest Income'
                AND l.buy > 0
                {wallet_filter_sql}
            ORDER BY l.createddate ASC
        """
        
        if wallet:
            cur.execute(trade_purchase_query, (coin, wallet))
            trade_purchases = cur.fetchall()
            
            cur.execute(interest_purchase_query, (coin, wallet))
            interest_purchases = cur.fetchall()
        else:
            cur.execute(trade_purchase_query, (coin,))
            trade_purchases = cur.fetchall()
            
            cur.execute(interest_purchase_query, (coin,))
            interest_purchases = cur.fetchall()
        
        # Combine and sort all purchases by date
        all_purchases = list(trade_purchases) + list(interest_purchases)
        all_purchases.sort(key=lambda x: x[0])
        
        if not all_purchases:
            return [], {}
        
        # Get all sales through today to consume FIFO queue properly
        # Filter by wallet if specified
        sale_query = f"""
            SELECT createddate, sell as quantity, exchange, id
            FROM ledger
            WHERE sell_curr = %s 
                AND trans_type = 'Trade'
                AND sell > 0
                {wallet_filter_sql}
            ORDER BY createddate ASC
        """
        
        if wallet:
            cur.execute(sale_query, (coin, wallet))
        else:
            cur.execute(sale_query, (coin,))
        historical_sales = cur.fetchall()
        
        # Build purchase queue
        purchase_queue = []
        for purchase in all_purchases:
            purchase_date, qty, unit_cost, total_cost, exchange = purchase
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
        cur = self.connection.cursor()
        
        # Check if wallets table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'wallets'
            )
        """)
        wallets_table_exists = cur.fetchone()[0]
        
        if wallets_table_exists:
            # Get wallet metadata from wallets table
            active_filter = "WHERE active = true" if active_only else ""
            query = f"""
                SELECT wallet_id, wallet_type, custody, description, active
                FROM wallets
                {active_filter}
                ORDER BY wallet_id
            """
            cur.execute(query)
            return [{'wallet_id': row[0], 'type': row[1], 'custody': row[2], 
                    'description': row[3], 'active': row[4]} 
                   for row in cur.fetchall()]
        else:
            # Fallback: get distinct exchange values from ledger
            cur.execute("""
                SELECT DISTINCT exchange 
                FROM ledger 
                WHERE exchange IS NOT NULL
                ORDER BY exchange
            """)
            return [{'wallet_id': row[0], 'type': 'unknown', 'custody': 'unknown',
                    'description': None, 'active': True}
                   for row in cur.fetchall()]
    
    def get_wallet_balance(self, coin='BTC', wallet=None):
        """
        Get balance for a specific wallet, or all wallets if wallet=None.
        
        Returns:
            If wallet specified: float (balance)
            If wallet=None: dict {wallet_id: balance}
        """
        cur = self.connection.cursor()
        
        if wallet:
            # Balance for specific wallet
            # Note: Fees are already included in buy/sell amounts, not subtracted separately
            query = """
                SELECT 
                    COALESCE(SUM(CASE WHEN buy_curr = %s THEN buy ELSE 0 END), 0) -
                    COALESCE(SUM(CASE WHEN sell_curr = %s THEN sell ELSE 0 END), 0)
                FROM ledger
                WHERE exchange = %s
            """
            cur.execute(query, (coin, coin, wallet))
            result = cur.fetchone()[0]
            return float(result) if result else 0.0
        else:
            # Balance for all wallets
            # Note: Fees are already included in buy/sell amounts, not subtracted separately
            query = """
                SELECT 
                    exchange,
                    COALESCE(SUM(CASE WHEN buy_curr = %s THEN buy ELSE 0 END), 0) -
                    COALESCE(SUM(CASE WHEN sell_curr = %s THEN sell ELSE 0 END), 0) as balance
                FROM ledger
                WHERE exchange IS NOT NULL
                GROUP BY exchange
                HAVING COALESCE(SUM(CASE WHEN buy_curr = %s THEN buy ELSE 0 END), 0) -
                       COALESCE(SUM(CASE WHEN sell_curr = %s THEN sell ELSE 0 END), 0) != 0
                ORDER BY exchange
            """
            cur.execute(query, (coin, coin, coin, coin))
            return {row[0]: float(row[1]) for row in cur.fetchall()}



