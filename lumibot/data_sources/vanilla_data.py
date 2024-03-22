import logging
from datetime import datetime

import pytz
import akshare

from lumibot.entities import Bars, Asset
from lumibot.tools.helpers import create_options_symbol, parse_timestep_qty_and_unit

from .data_source import DataSource


class VanillaData(DataSource):
    SOURCE = "Vanilla"
    MIN_TIMESTEP = "day"
    TIMESTEP_MAPPING = [
        {"timestep": "day", "representations": ["1d"]},
    ]

    def __init__(self):
        super().__init__()
        

    def get_historical_prices(
        self, asset, length, timestep="", timeshift=None, quote=None, exchange=None, include_after_hours=True
    ):
        """Takes an asset and returns the last known price"""
        asset_str = str(asset).upper()
        try:
            df = akshare.futures_zh_daily_sina(asset_str).tail(length)
            if df is None:
                return None
        except Exception as e:
            logging.error(f"Error getting historical prices for {asset}: {e}")
            return None

        # Convert the dataframe to a Bars object
        bars = Bars(df, self.SOURCE, asset, raw=df, quote=quote)

        return bars
    def get_chains(self, asset: Asset, quote: Asset = None, exchange: str = None):
        raise NotImplementedError(
            "Lumibot Vanilla does not support historical options data. If you need this "
            "feature, please use a different data source."
        )
    def get_last_price(self, asset, quote=None, exchange=None):
        """Get bars for a given asset"""
        asset = str(asset).upper()
        bars = akshare.futures_zh_spot(asset)
        if bars is None:
            return None
        price = bars.iloc[0].current_price
        #price = self.tradier.market.get_last_price(asset)
        return price