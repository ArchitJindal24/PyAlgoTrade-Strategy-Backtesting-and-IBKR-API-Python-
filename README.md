# PyAlgoTrade-Strategy-Backtesting-and-IBKR-API-Python-
On the basis of closing/opening, highest/lowest and other valuation data provided, simple and more complex trading startegies can eb tested.
Program automatically carries out purchase/sale transactions in simulation on provided data as per the strategy giving us the total portfolio value at the end of simulation
based on initial sum given. 
Integration is also done with real world transactions using API given by IBKR.
Note that all API is customized, so you probably need to change ports to use this. Take help from IBKR site.
This is not a complete project except for backtesting program.

## Indian markets (ICICI Direct)
The `icici_breeze/` folder ports the SMA strategy to NSE using ICICI Direct's Breeze API, with a backtester and a paper/live trader. See [icici_breeze/README.md](icici_breeze/README.md).
