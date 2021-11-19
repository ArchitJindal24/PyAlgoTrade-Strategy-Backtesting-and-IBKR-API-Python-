from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
import threading
import time


class IBapi(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)

    def tickPrice(self, reqId, tickType, price, attrib):
        if tickType == 2 and reqId == 1:
            print('The Current ask price is: ', price)


def run_loop():
    app.run()


app = IBapi()
app.connect('127.0.0.1', 7497, 2224)

# Start the socket in a thread
api_thread = threading.Thread(target=run_loop, daemon=True)
api_thread.start()

time.sleep(1)  # Sleep interval is to allow time for connection to server

# create contract object
BTC = Contract()
BTC.symbol = 'BRR'
BTC.secType = 'FUT'
BTC.exchange = 'CMECRYPTO'
BTC.lastTradeDateOrContractMonth = '202103'

# Request market data
app.reqMktData(1, BTC, '', True, False, [])

time.sleep(10)  # Sleep interval to allow time for incoming price data
app.disconnect()

app = IBapi()
app.connect('127.0.0.1', 7497, 2224)
app.run()
