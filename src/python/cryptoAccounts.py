import psycopg2
import csv
from datetime import datetime, timedelta

now = datetime.now()

class CryptoAccounts(object):

    def __init__(self):
        self.connection = psycopg2.connect(database="postgres", user="bitcoin_accounting", password="REDACTED-ROTATED", host="numenor", port="5432", sslmode='require')


    def close(self):
        self.connection.close()

    def get_balance(self, coin = 'BTC'):
        cur = self.connection.cursor()
        query = "select get_balance('" + coin + "')"
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            return row[0]

    def get_balance_by_account(self, coin = 'BTC', account = 'Vault'):
        cur = self.connection.cursor()
        query = "select get_balance_by_account('" + coin + "', '" + account + "')"
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            return row[0]

    def get_basis(self, coin = 'BTC'):
        cur = self.connection.cursor()
        query = "select get_avg_purchase_price('" + coin + "')"
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            return row[0]
            
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

   

