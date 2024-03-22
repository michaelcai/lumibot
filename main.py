import datetime
import pandas as pd
import pandas_ta as ta
from lumibot.brokers import Vanilla
from lumibot.entities import Asset
from lumibot.strategies.strategy import Strategy
from lumibot.traders import Trader


class VanillaImportantFunctions(Strategy):
    def initialize(self):
        # Set the time between trading iterations
        self.sleeptime = "10S"
    def on_trading_iteration(self):
        # Skip first interation
        if self.first_iteration:
            return 
        ###########################
        # Get orders
        ###########################
        
        orders = self.get_orders()
        
        ###########################
        # Get latest price
        ###########################
        
        base = Asset("i2405")
        price = self.get_last_price(base)
      
        ###########################
        # Placing an Order
        ###########################
        
        # Limit Order for 1 i2405 at a limit price of last price - 10
        self.log_message(f"Order count: {len(orders)}")
        if len(orders) == 0:
          
          lmt_order = self.create_order(base, 1, "buy", limit_price=price-10, exchange="DCE")
          self.submit_order(lmt_order)
          self.log_message(f"Submit new order: {lmt_order}", color="blue")
        
        ###########################
        # Getting Historical Data
        ###########################

        # Get the historical prices for our base/quote pair for the last 100 minutes
        bars = self.get_historical_prices(base, 100)
        if bars is not None:
            df = bars.df
            max_price = df["close"].max()
            self.log_message(f"Max price for {base} was {max_price}")

            ############################
            # TECHNICAL ANALYSIS
            ############################

            # Use pandas_ta to calculate the 20 period RSI
            rsi = df.ta.rsi(length=20)
            current_rsi = rsi.iloc[-1]
            self.log_message(f"RSI for {base} was {current_rsi}")

            # Use pandas_ta to calculate the MACD
            macd = df.ta.macd()
            current_macd = macd.iloc[-1]
            self.log_message(f"MACD for {base} was {current_macd}")

            # Use pandas_ta to calculate the 55 EMA
            ema = df.ta.ema(length=55)
            current_ema = ema.iloc[-1]
            self.log_message(f"EMA for {base} was {current_ema}")
            
        ###########################
        # Positions and Orders
        ###########################

        # Get all the positions that we own, including cash
        positions = self.get_positions()
        for position in positions:
            self.log_message(f"Position: {position}")

            # Get the asset of the position
            asset = position.asset

            # Get the quantity of the position
            quantity = position.quantity

            # Get the symbol from the asset
            symbol = asset.symbol

            self.log_message(f"we own {quantity} shares of {symbol}")
        # Get one specific position
        asset_to_get = Asset("i2405")
        position = self.get_position(asset_to_get)
        self.log_message(f"Position: {position}")
        
        # Get all of the outstanding orders
        orders = self.get_orders()
        for order in orders:
            self.log_message(f"Order: {order}")
            if not order.is_canceled():
                self.log_message(f"Cancel order: {order.exchange},{order.symbol} {order.identifier}", color="blue")
                self.cancel_order(order)
            # Do whatever you need to do with the order
            
        # Get the value of the entire portfolio, including positions and cash
        portfolio_value = self.portfolio_value
        # Get the amount of cash in the account (the amount in the quote_asset)
        cash = self.cash

        self.log_message(f"The current value of your account is {portfolio_value}")
        # Note: Cash is based on the quote asset
        self.log_message(f"The current amount of cash in your account is {cash}")


if __name__ == "__main__":
  
    trader = Trader()

    CONFIG = {
        "trader_client_url": "127.0.0.1:6000",
        "trade_list": ["DCE,i2405", "INE,ec2404"]
    }


    broker = Vanilla(CONFIG)
    quote_asset = Asset(
        symbol="CNY"
    )
    strategy = VanillaImportantFunctions(
        broker=broker,
        quote_asset=quote_asset
    )

    trader.add_strategy(strategy)
    strategy_executors = trader.run_all()
