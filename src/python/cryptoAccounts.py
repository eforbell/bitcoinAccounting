import psycopg2
import csv


class CryptoAccounts(object):

    def __init__(self):
        self.connection = psycopg2.connect(database="crypto", user="forbell", password="", host="127.0.0.1", port="5432")


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
        with open(out_file, 'w') as csv_out:
            trans_writer = csv.DictWriter(csv_out, fieldnames=colnames)
            trans_writer.writeheader()
            for transaction in transactions:
                trans_writer.writerow(transaction)

    def transfer_funds(self, date, from_account, tx_coin, tx_amount, to_account, fee_coin, fee_amount):
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

        withdrawQuery = "insert into ledger (createddate, trans_type, sell, sell_curr, fee, fee_curr, exchange, \"group\") values (%s, 'Withdrawal', %s, %s, %s, %s, %s, %s)"
        depositQuery =  "insert into ledger (createddate, trans_type, buy, buy_curr, exchange, \"group\") values (%s, 'Deposit', %s, %s, %s, %s)"
        cur = self.connection.cursor()
        cur.execute(withdrawQuery, (date, tx_amount, tx_coin, fee_amount, fee_coin, from_exchange, from_group))
        cur.execute(depositQuery, (date, tx_amount, tx_coin, to_exchange, to_group))
        self.connection.commit()



crypto = CryptoAccounts()
#crypto.export_transactions_csv('bnb_out.csv','BNB')
crypto.transfer_funds('2021-03-30 20:24:47', 'Binance:Binance US', 'VET', 18663, 'Ledger', 'VET', 100)
crypto.transfer_funds('2021-04-09 15:25:52', 'Binance:Binance US', 'VET', 3387, 'Ledger', 'VET', 100)
crypto.close()