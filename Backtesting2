from abc import ABC

from pyalgotrade import strategy
from pyalgotrade.barfeed import quandlfeed
from pyalgotrade.technical import ma
from pyalgotrade.technical import rsi


def safe_round(value,digits):
    if value is not None:
        value = round(value, digits)
        return value


class FirstStrategy(strategy.BacktestingStrategy, ABC):
    def __init__(self, feed, instrument):
        super(FirstStrategy, self).__init__(feed)
        # We want a 15 period SMA over the closing prices.
        self.__sma = ma.SMA(feed[instrument].getCloseDataSeries(), 15)
        self.__rsi = rsi.RSI(feed[instrument].getCloseDataSeries(), 14)
        self.__instrument = instrument

    def onBars(self, bars):
        bar = bars[self.__instrument]
        self.info("Closing Price is %s, Moving Average is %s, RSI is %s" % (bar.getClose(), safe_round(self.__sma[-1], 2), safe_round(self.__rsi[-1], 2)))


# Load the bar feed from csv file
feed = quandlfeed.Feed()
feed.addBarsFromCSV("orcl", "E:\Python Projects\API\WIKI-ORCL-2000-quandl.csv")

# Evaluate the strategy with the feed's bars.
myStrategy = FirstStrategy(feed, "orcl")
myStrategy.run()
