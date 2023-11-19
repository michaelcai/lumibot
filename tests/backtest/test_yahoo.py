import datetime

from lumibot.backtesting import BacktestingBroker, YahooDataBacktesting
from lumibot.strategies import Strategy
from lumibot.traders import Trader


class YahooPriceTest(Strategy):
    parameters = {
        "symbol": "SPY",  # The symbol to trade
    }

    def initialize(self):
        # There is only one trading operation per day
        # No need to sleep between iterations
        self.sleeptime = "1D"

    def on_trading_iteration(self):
        # Get the parameters
        symbol = self.parameters["symbol"]

        # Get the datetime
        self.dt = self.get_datetime()

        # Get the last price
        self.last_price = self.get_last_price(symbol)


class TestYahooBacktestFull:
    def test_yahoo_last_price(self):
        """
        Test Polygon REST Client with Lumibot Backtesting and real API calls to Polygon. Using the Amazon stock
        which only has options expiring on Fridays. This test will buy 10 shares of Amazon and 1 option contract
        in the historical 2023-08-04 period (in the past!).
        """
        # Parameters: True = Live Trading | False = Backtest
        # trade_live = False
        backtesting_start = datetime.datetime(2023, 11, 1)
        backtesting_end = datetime.datetime(2023, 11, 2)

        data_source = YahooDataBacktesting(
            datetime_start=backtesting_start,
            datetime_end=backtesting_end,
        )

        broker = BacktestingBroker(data_source=data_source)

        poly_strat_obj = YahooPriceTest(
            broker=broker,
            backtesting_start=backtesting_start,
            backtesting_end=backtesting_end,
        )

        trader = Trader(logfile="", backtest=True)
        trader.add_strategy(poly_strat_obj)
        results = trader.run_all(show_plot=False, show_tearsheet=False, save_tearsheet=False)

        assert results

        last_price = poly_strat_obj.last_price
        # Round to 2 decimal places
        last_price = round(last_price, 2)

        assert last_price == 416.18  # This is the correct price for 2023-11-01 (the open price)
