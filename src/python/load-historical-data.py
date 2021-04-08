import json
import os
import psycopg2

connection = psycopg2.connect(database="crypto", user="forbell", password="", host="127.0.0.1", port="5432")
cursor = connection.cursor()
cursor.execute("delete from pair_price");
connection.commit()
history_dir = 'src/resources/data/historical'
for history_file in os.listdir(history_dir):
    if (history_file.endswith('.json')):
        with open(os.path.join(history_dir,history_file)) as myfile:
            data = myfile.read()
            history = json.loads(data)
            coin = history['coin']['symbol']
            for price_history in history['data']:
                cursor.execute("insert into pair_price (to_curr, price, from_curr,date) values ('USD', %s, %s, %s)",(price_history['closePrice'],coin, price_history['date']))
            connection.commit()

connection.close()
