from prompt_toolkit import print_formatted_text as print
from prompt_toolkit import HTML, PromptSession
from prompt_toolkit.validation import Validator, ValidationError
from datetime import datetime, timedelta
from prompt_toolkit.shortcuts import yes_no_dialog

from cryptoAccounts import CryptoAccounts

class NumericValidator(Validator):
    def validate(self, document):
        text = document.text

        if text and not text.isnumeric():
            raise ValidationError(message='This input is not numeric')

def main():
    # Create prompt object.
    session = PromptSession()
    now = datetime.now()
    record_tx = False

    while True:
        try :
            satsSource = session.prompt("Enter exchange: ", default="Strike")
            satsBought = float(session.prompt("Enter sats bought: ", validator=None))
            dollarsSold = float(session.prompt("Enter dollars paid: ", validator=None))
            tx_date = None
            while tx_date is None:
                tx_data_raw = session.prompt("Enter datetime: ", validator=None)
                try:
                    tx_date = datetime.strptime(tx_data_raw, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    print("%s is not a datetime: (YY-mm-dd HH:MM:SS)" % tx_data_raw)
            withdraw_wallet = session.prompt("Withdraw wallet: ", default="Ledger-2")
            withdraw_delay_minutes = session.prompt("Withdraw delay (min): ", default="700")

            print("Sats purchased: %s" % satsBought)
            print("Dollar cost: %s" % dollarsSold)
            print("Transaction date: %s" % tx_date)
            record_tx = session.prompt("Do you want to record this transaction? (Y/N) ")
            if record_tx == 'Y' or record_tx == 'y':
                crypto = CryptoAccounts()
                crypto.deposit(exchange=satsSource, deposit_date=tx_date, buy=dollarsSold)
                tx_date = tx_date + timedelta(seconds=30)
                crypto.execute_trade(exchange=satsSource, trade_date=tx_date, buy=satsBought, sell=dollarsSold)
                tx_date = tx_date + timedelta(seconds=30)
                withdraw_date = tx_date + timedelta(minutes=int(withdraw_delay_minutes))
                crypto.transfer_funds(from_account=satsSource, to_account=withdraw_wallet, withdraw_date=tx_date, deposit_date=withdraw_date, tx_amount=satsBought)
                print("Recorded transaction.")
                print("Current balance : " + str(crypto.get_balance("BTC")) + " : " + str(crypto.get_basis("BTC")))
                crypto.close()
                break
        except KeyboardInterrupt:
            break
        except EOFError:
            break

    print("Exiting...")


if __name__ == "__main__":
    main()
