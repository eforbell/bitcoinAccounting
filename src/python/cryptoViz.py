import psycopg2
import pandas as pd
from cryptoAccounts import CryptoAccounts
import matplotlib.pyplot as plt


class CryptoViz(object):

    def __init__(self):
        self.connection = psycopg2.connect(database="crypto", user="forbell", password="", host="127.0.0.1", port="5432")
        self.cryptoAccounts = CryptoAccounts

    def close(self):
        self.connection.close()


con = psycopg2.connect(database="crypto", user="forbell", password="", host="127.0.0.1", port="5432")
query = "select * from get_trade_cost_new('BTC', 'USD') order by date"
df = pd.read_sql(query, con)
