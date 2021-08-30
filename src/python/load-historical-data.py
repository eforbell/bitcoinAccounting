import json
import os
import psycopg2
import requests

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
        if (coin['name'] not in ['BnB Coin','Stellar Lumens']):
            coins[coin['symbol']] = coin['id']
    return coins

def get_history(coinId, startDate, endDate):
    history = requests.get('https://cryptocurrencychart.com/api/coin/history/'+str(coinId)+'/'+startDate+'/'+endDate+'/closePrice', headers=get_headers())

    return history.json()['data']

connection = psycopg2.connect(database="crypto", user="forbell", password="", host="127.0.0.1", port="5432")
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

startDate = '2021-04-07'
endDate = '2021-08-30'
coins = get_coins()
#myCoins = ['BTC','ADA','ALGO','BNB','BUSD','ETH','GUSD','USDC','LTC','NEXO','RUNE','RVN','VET','VTHO']
myCoins = ['XLM','SOL']
for coin in myCoins:
    history = get_history(coins[coin],startDate,endDate)
    for price_history in history:
        closePrice = str(price_history['closePrice'])
        date = price_history['date']
        cursor.execute("insert into pair_price (to_curr, price, from_curr,date) values ('USD', %s, %s, %s)",(closePrice,coin,date))
        connection.commit()
connection.close()
