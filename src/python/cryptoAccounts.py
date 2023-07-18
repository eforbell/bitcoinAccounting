import psycopg2
import csv
from datetime import datetime, timedelta

now = datetime.now()

class CryptoAccounts(object):

    def __init__(self):
        self.connection = psycopg2.connect(database="postgres", user="bitcoin_accounting", password="bitcoin_accounting", host="numenor.local", port="5432")


    def close(self):
        self.connection.close()


    def get_balances(self, coin):
        cur = self.connection.cursor()
        cur.execute('''
        select c.name \"coin\", get_balance(c.name) as balance from coins c 
            where get_balance(c.name) is not null
            order by balance desc;
        ''')
        rows = cur.fetchall()
        for row in rows:
            print(row[0])
            print(row[1])
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

    def execute_trade(self, trade_date=now, buy=0.0, buy_curr="BTC", sell=0.0, sell_curr="USD", fee=0.0, fee_curr="USD",
                      exchange="Strike", group=""):
        cur = self.connection.cursor()
        cur.execute(
            self.getTradeQuery(),
            (trade_date, buy, buy_curr, sell, sell_curr, fee, fee_curr, exchange, group))
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

crypto = CryptoAccounts()
#crypto.transfer_funds('2022-04-01 09:59:00', 'Swan Bitcoin','BTC', 0.01239033,'Ledger-2', 'BTC', 0.0);
#crypto.transfer_funds('2022-02-22 09:50:00', 'LN','BTC', 0.00120000,'Muun', 'BTC', 0.00000242);
#crypto.transfer_funds('2022-01-16 09:25:00', ,'Strike (Val)','BTC', 0.02312012, 'Ledger', 'BTC', 0.0);
#colnames, transactions = crypto.import_transactions_nexo_csv('/Users/forbell/Desktop/cointracking/nexo_transactions_final.csv')
#colnames, transactions = crypto.import_transactions_ledger_csv('/Users/forbell/Desktop/cointracking/ALGO-rewards.csv')
#colnames, transactions = crypto.import_transactions_rvn_mining('/Users/forbell/Desktop/cointracking/rvn-mining-01-29-2022.csv')
#colnames, transactions = crypto.import_transactions_ada_csv('/Users/forbell/Desktop/cointracking/rewards_9ab0a58f72b459260c20d98ef1dee2ec7882e6ec825b91c1a663fca6_usd_cointracking_2021-12-02_2022-01-16.csv')
#crypto.import_transactions(colnames, transactions)
satsBought = 0.00800784
dollarsSold = 250.0
tx_date = datetime.strptime("2023-07-04 14:36:00", '%Y-%m-%d %H:%M:%S')
#crypto.deposit(deposit_date=tx_date,buy=dollarsSold)
#crypto.execute_trade(trade_date=tx_date, buy=satsBought,sell=dollarsSold)
withdraw_date = tx_date + timedelta(minutes=60)
crypto.transfer_funds(withdraw_date=tx_date,deposit_date=withdraw_date, tx_amount=satsBought)
crypto.export_transactions_csv("t://Wallets/tx_export/transactions_2023-07-04.csv")
crypto.close()