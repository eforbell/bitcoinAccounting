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


crypto = CryptoAccounts()
crypto.export_transactions_csv('bnb_out.csv','BNB')