import pandas as pd
from cryptoAccounts import CryptoAccounts
import matplotlib.pyplot as plt
from config import connect


class CryptoViz(object):

    def __init__(self):
        # use config.connect() for DB connection
        self.connection = connect()
        self.cryptoAccounts = CryptoAccounts()

    def close(self):
        self.connection.close()


con = connect()
query = "select * from get_trade_cost_new('BTC', 'USD') order by date"
df = pd.read_sql(query, con)
