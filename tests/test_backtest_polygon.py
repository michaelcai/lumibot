import datetime
import os

import pytest
import pytz
import pandas_market_calendars as mcal

from lumibot.entities import Asset
from lumibot.backtesting import PolygonDataBacktesting
from lumibot.strategies import Strategy


# Lumibot doesn't allow any other non-global hooks for storing data during backtesting
ORDERS = []
PRICES = {}
FILLED_ORDERS = []
FILLED_PRICES = {}

# API Key for Polygon.io
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")


class PolygonBacktestStrat(Strategy):
    parameters = {"symbol": "AMZN"}

    # Set the initial values for the strategy
    def initialize(self):
        self.sleeptime = "1D"
        self.first_price = None
        self.first_option_price = None
        self.orders = []
        self.chains = {}

    def select_option_expiration(self, chain, days_to_expiration=1) -> datetime.date:
        """
        Select the option expiration date based on the number of days (from today) until expiration
        :param chain: List of valid option contracts and their expiration dates and strike prices.
            Format: {'TradingClass': 'SPY', 'Multiplier': 100, 'Expirations': [], 'Strikes': []}
        :param days_to_expiration: Number of days until expiration, will select the next expiration date at or after
            this that is available on the exchange
        :return: option expiration as a datetime.date object
        """
        market_cal = mcal.get_calendar("NYSE")  # Typically NYSE, but can be different for some assets
        today = self.get_datetime()
        extra_days_padding = 7  # Some options are not traded every day. Make sure we get enough trading days to check

        # Trading Days DataFrame Format:
        #       index               market_open              market_close
        # =========== ========================= =========================
        #  2012-07-02 2012-07-02 13:30:00+00:00 2012-07-02 20:00:00+00:00
        #  2012-07-03 2012-07-03 13:30:00+00:00 2012-07-03 17:00:00+00:00
        #  2012-07-05 2012-07-05 13:30:00+00:00 2012-07-05 20:00:00+00:00
        trading_days_df = market_cal.schedule(
            start_date=today,
            end_date=today + datetime.timedelta(days=days_to_expiration + extra_days_padding)
        )

        # Look for the next trading day that is in the list of expiration dates. Skip the first trading day because
        # that is today and we want to find the next expiration date.
        #   Date Format: 2023-07-31
        trading_datestrs = [x.to_pydatetime().date() for x in trading_days_df.index.to_list()]
        for trading_day in trading_datestrs[days_to_expiration:]:
            day_str = trading_day.strftime("%Y-%m-%d")
            if day_str in chain['Expirations']:
                return trading_day

        raise ValueError(f"Could not find an option expiration date for {days_to_expiration} day(s) "
                         f"from today({today})")

    def before_market_opens(self):
        underlying_asset = Asset(self.parameters["symbol"])
        self.chains = self.get_chains(underlying_asset)

    def before_starting_trading(self):
        underlying_asset = Asset(self.parameters["symbol"])
        self.chains = self.get_chains(underlying_asset)

    def after_market_closes(self):
        orders = self.get_orders()
        self.log_message(f"PolygonBacktestStrat: {len(orders)} orders executed today")

    # Trading Strategy: Backtest will only buy traded assets on first iteration
    def on_trading_iteration(self):
        if self.first_iteration:
            now = self.get_datetime()

            # Create simple option chain | Plugging Amazon "AMZN"; always checking Friday (08/04/23) ensuring
            # Traded_asset exists
            underlying_asset = Asset(self.parameters["symbol"])
            current_asset_price = self.get_last_price(underlying_asset)

            # Option Chain: Get Full Option Chain Information
            chain = self.get_chain(self.chains, exchange="SMART")
            expiration = self.select_option_expiration(chain, days_to_expiration=1)
            # expiration = datetime.date(2023, 8, 4)

            strike_price = round(current_asset_price)
            option_asset = Asset(
                symbol=underlying_asset.symbol,
                asset_type="option",
                expiration=expiration,
                right="CALL",
                strike=strike_price,
                multiplier=100,
                currency="USD",
            )
            current_option_price = self.get_last_price(option_asset)

            # Buy 10 shares of the underlying asset for the test
            qty = 10
            self.log_message(f"Buying {qty} shares of {underlying_asset} at {current_asset_price} @ {now}")
            order_underlying_asset = self.create_order(underlying_asset, quantity=qty, side="buy")
            submitted_order = self.submit_order(order_underlying_asset)
            ORDERS.append(submitted_order)
            PRICES[submitted_order.identifier] = current_asset_price

            # Buy 1 option contract for the test
            order_option_asset = self.create_order(option_asset, quantity=1, side="buy")
            submitted_order = self.submit_order(order_option_asset)
            ORDERS.append(submitted_order)
            PRICES[submitted_order.identifier] = current_option_price


class TestPolygonBacktestFull:
    def test_polygon_restclient(self):
        """
        Test Polygon REST Client with Lumibot Backtesting and real API calls to Polygon. Using the Amazon stock
        which only has options expiring on Fridays. This test will buy 10 shares of Amazon and 1 option contract
        in the historical 2023-08-04 period (in the past!).
        """
        
        # Parameters: True = Live Trading | False = Backtest
        # trade_live = False
        symbol = "AMZN"
        underlying_asset = Asset(symbol=symbol, asset_type="stock")
        backtesting_start = datetime.datetime(2023, 8, 1)
        backtesting_end = datetime.datetime(2023, 8, 4)

        # Execute Backtest | Polygon.io API Connection
        results = PolygonBacktestStrat.backtest(
            PolygonDataBacktesting,
            backtesting_start,
            backtesting_end,
            benchmark_asset="SPY",
            show_plot=False,
            show_tearsheet=False,
            save_tearsheet=False,
            polygon_api_key=POLYGON_API_KEY,  # TODO Replace with Lumibot owned API Key
            # Painfully slow with free subscription setting b/c lumibot is over querying and imposing a very
            # strict rate limit
            polygon_has_paid_subscription=True,
        )

        assert results
        assert len(ORDERS) == 2
        stock_order = ORDERS[0]
        option_order = ORDERS[1]
        asset_order_id = stock_order.identifier
        option_order_id = option_order.identifier
        assert asset_order_id in PRICES
        assert option_order_id in PRICES
        assert 130.0 < PRICES[asset_order_id] < 140.0, "Valid asset price should be between 130 and 140 for time period"
        assert PRICES[option_order_id] == 4.10, "Opening Price is $4.10 on 08/01/2023"

        # TODO: Talk to RobG about why this is failing during BackTest. Status is correct, position_filled is not
        assert option_order.status == 'fill'
        assert option_order.position_filled, "Option order should be filled"


@pytest.mark.skip("DataSource is not working well outside of a full backtest")
class TestPolygonBacktestBasics:
    def test_polygon_basics(self):
        asset = Asset("SPY")
        now = datetime.datetime.now(pytz.utc)
        start = now - datetime.timedelta(days=1)
        end = now
        polygon_backtest = PolygonDataBacktesting(
            start,
            end,
            polygon_api_key=POLYGON_API_KEY,
            has_paid_subscription=True,
        )
        assert polygon_backtest.get_last_price(asset)
