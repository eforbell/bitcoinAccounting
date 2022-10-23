import json
import os
import psycopg2
import requests
import yfinance as yf
import pandas as pd
from pandas_datareader import data as pdr
yf.pdr_override()

def get_history(ticker, startDate, endDate):
    return pdr.get_data_yahoo(ticker, start=startDate, end=endDate)

def get_headers():
    headers = {}
    headers['Key'] = 'ac0aa691716192efc74867ab30789d27'
    headers['Secret'] = '86cd872ad2790fd877b0ffcc5d972700'
    headers['Content-Type'] = 'application/json'
    return headers

def get_coins():
    coins_raw = requests.get('https://cryptocurrencychart.com/api/coin/list', headers=get_headers()).json()
    coins = {}
    for coin in coins_raw['coins']:
        if (coin['name'] not in ['BnB Coin','Stellar Lumens','BatCoin']):
            coins[coin['symbol']] = coin['id']
    return coins


def get_history_legacy(coinId, startDate, endDate):
    history = requests.get('https://cryptocurrencychart.com/api/coin/history/'+str(coinId)+'/'+startDate+'/'+endDate+'/closePrice', headers=get_headers())
    return history.json()['data']

class TickerData:
    def __init__(self, ticker):
        self.ticker = yf.Tickers(ticker)
        self.data = yf.download(tickers=(ticker), period='1y', interval='1d', group_by='ticker', auto_adjust=True,
                                prepost=False)
        self.df = pd.DataFrame(self.data)

    def find_z(self):
        mean = self.df['Close'].mean()
        z_from_mean = (self.df['Close'].tail(1) - mean) / np.std(self.df['Close'])
        return z_from_mean


connection = psycopg2.connect(database="crypto2", user="bitcoin_accounting", password="bitcoin_accounting", host="127.0.0.1", port="5432")
cursor = connection.cursor()
#cursor.execute("delete from pair_price");
#connection.commit()
#history_dir = 'src/resources/data/historical'
#for history_file in os.listdir(history_dir):
#    if (history_file.endswith('.json')):
#        with open(os.path.join(history_dir,history_file)) as myfile:
#            data = myfile.read()
#            history = json.loads(data)
#            coin = history['coin']['symbol']
#            for price_history in history['data']:
#                cursor.execute("insert into pair_price (to_curr, price, from_curr,date) values ('USD', %s, %s, %s)",(price_history['closePrice'],coin, price_history['date']))
#            connection.commit()


cursor.execute("select DATE(max(date)) as start_date, DATE(now()) as end_date from pair_price")
dates = cursor.fetchone()
startDate = str(dates[0])
endDate = str(dates[1])
startDate = '2022-06-29'
endDate = '2022-06-30'
if startDate != endDate:
    #coins = get_coins()
    myCoins = ['BTC-USD','ADA-USD','ALGO-USD','BNB-USD','ETH-USD','USDC-USD','LTC-USD','RUNE-USD','RVN-USD','BAT-USD']
    #myCoins = ['BTC-USD']
    for coin in myCoins:
        history = get_history(coin,startDate,endDate)
        for index, row in history.iterrows():
            closePrice = str(row['Close'])
            date = str(index)
            coinOnly = coin.split("-")[0]
            cursor.execute("insert into pair_price (to_curr, price, from_curr,date) values ('USD', %s, %s, %s)",(closePrice,coinOnly,date))
        connection.commit()
    coins = get_coins()
    myLegacyCoins = ['GUSD','BUSD','ALGO']
    for coin in myLegacyCoins:
        history = get_history_legacy(coins[coin],startDate,endDate)
        for price_history in history:
            closePrice = str(price_history['closePrice'])
            date = price_history['date']
            cursor.execute("insert into pair_price (to_curr, price, from_curr,date) values ('USD', %s, %s, %s)",(closePrice,coin,date))

        connection.commit()
connection.close()

# coins = get_coins()
# history_dir = '/Volumes/SCRATCH1/workspace/cryptoAccounting/src/resources/data/historical'
# with open(os.path.join(history_dir,'btc.csv'),'w') as out:
#     history = get_history(coins['BTC'],'2021-01-01','2021-11-06')
#     for price_history in history:
#         closePrice = str(price_history['closePrice'])
#         date = price_history['date']
#         out.write(date+','+closePrice+'\n')
# connection.close()
