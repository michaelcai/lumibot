import time
import datetime
import logging
import smart_trader_api.client as api
from termcolor import colored

from lumibot.data_sources import VanillaData
from lumibot.entities import Asset, Order, Position

from .broker import Broker


class Vanilla(Broker):
    """
    Vanilla broker using GW.
    """

    def __init__(self, config, data_source: VanillaData = None, max_workers=20, chunk_size=100, **kwargs):
        self.market = "24/7"
        if data_source is None:
            data_source = VanillaData()
        super().__init__(self, config=config, data_source=data_source, max_workers=max_workers, **kwargs)

        self.fetch_open_orders_last_request_time = None
        if not isinstance(self.data_source, VanillaData):
            raise ValueError(f"Vanilla Broker's Data Source must be of type {VanillaData}")
        conf = api.TradeClientConf(url = config["trader_client_url"])
        self.api = api.new_trade_client(conf)
        self.trade_list = config["trade_list"]
    # =========Clock functions=====================

    def get_timestamp(self):
        """Returns the current UNIX timestamp representation from Vanilla"""
        return time.time()

    def is_market_open(self):   
        ## TODO: Need to adjust to the trading schedule of CTP
        return True

    def get_time_to_open(self):
        ## TODO: Need to adjust to the trading schedule of CTP
        return None

    def get_time_to_close(self):
        ## TODO: Need to adjust to the trading schedule of CTP
        return None

    def is_margin_enabled(self):
        """Check if the broker is using margin trading"""
        return "margin" in self._config and self._config["margin"]

    def _fetch_balance(self):
        return self.api.future_account("all")

    # =========Positions functions==================
    def _get_balances_at_broker(self, quote_asset):
        """Get's the current actual cash, positions value, and total
        liquidation value from ccxt.

        This method will get the current actual values from ccxt broker
        for the actual cash, positions value, and total liquidation.

        Best attempts will be made to use USD as a base currency.

        Returns
        -------
        tuple of float
            (cash, positions_value, total_liquidation_value)
        """
        balances = self._fetch_balance()
        
        return (balances.available_funds,0,balances.equity)

    def _parse_broker_position(self, position, strategy, orders=None):
        """parse a broker position representation
        into a position object"""
        quantity = position.size
        symbol = position.instrument_name.split(",")[1]

        asset = Asset(
            symbol=symbol,
        )
        position_return = Position(strategy, asset, quantity, orders=orders)
        return position_return

    def _pull_broker_position(self, asset):
        """Given a asset, get the broker representation
        of the corresponding asset"""
        positions = self._pull_broker_positions()
        for position in positions:
            if asset in position["instrument_name"]:
                return position
        return None

    def _pull_broker_positions(self, strategy=None):
        """Get the broker representation of all positions"""
        try:
            positions = self.api.future_positions('all')
        except Exception as e:
            logging.info(colored(str(e), "red"))
            return []
        else:
            return positions

    def _parse_broker_positions(self, broker_positions, strategy):
        """parse a list of broker positions into a
        list of position objects"""
        result = []
        for broker_position in broker_positions:
            result.append(self._parse_broker_position(broker_position, strategy))

        return result

    def _pull_positions(self, strategy):
        """Get the account positions. return a list of
        position objects"""
        response = self._pull_broker_positions(strategy)
        result = self._parse_broker_positions(response, strategy.name)
        return result

    def _pull_position(self, strategy, asset):
        """Get the account position for a given asset.
        return a position object"""
        response = self._pull_broker_position(asset)
        result = self._parse_broker_position(response, strategy)
        return result

    # =======Orders and assets functions=========
    def _parse_broker_order(self, response, strategy_name, strategy_object=None):
        """parse a broker order representation
        to an order object"""
        instrument_name = response.instrument_name.split(",")
        order = Order(
            strategy_name,
            asset=Asset(
                symbol=instrument_name[1],
                asset_type="future",
            ),
            quantity=response.amount,
            side=response.direction,
            limit_price=response.price,
            type="limit",
            exchange=instrument_name[0]
        )
        order.set_identifier(response.order_id)
        if response.order_state in ["SUBMITTING", "NOT_TRADED", "PART_TRADED"]:
            order.status = "open"
        elif response.order_state == "ALL_TRADED":
            order.status = "filled"
        elif response.order_state in ["CANCELLED", "REJECTED", "CANCEL_REJECTED"]:
            order.status = "canceled"
        order.update_raw(response)
        return order

    def _pull_broker_order(self, identifier):
        """Get a broker order representation by its id"""
        open_orders = self._pull_broker_all_orders()
        closed_orders = self._pull_broker_closed_orders()
        all_orders = open_orders + closed_orders

        response = [order for order in all_orders if order["id"] == identifier]

        return response[0] if len(response) > 0 else None

    def _pull_broker_closed_orders(self):
        all_close_orders = []
        for trade in self.trade_list:
            orders = self.api.future_close_orders(trade)
            all_close_orders += orders
        return all_close_orders

    def _pull_broker_all_orders(self):
        """Get the broker open orders"""
        all_orders = []
        for trade in self.trade_list:
            open_orders = self.api.future_open_orders(trade)
            close_orders = self.api.future_close_orders(trade)
            all_orders += open_orders
            all_orders += close_orders
        return all_orders

    def _flatten_order(self, order):
        """Some submitted orders may trigger other orders.
        _flatten_order returns a list containing the main order
        and all the derived ones"""
        orders = [order]
        # if "legs" in order._raw and order._raw.legs:
        #     strategy_name = order.strategy
        #     for json_sub_order in order._raw.legs:
        #         sub_order = self._parse_broker_order(json_sub_order, strategy_name)
        #         orders.append(sub_order)

        return orders

    def _submit_order(self, order):
        """Submit an order for an asset"""

        # Orders limited.
        order_class = None
        order_types = ["limit"]
        markets_error_message = f"Only `limit` orders work " f"with CTP markets."

        if order.order_class != order_class:
            logging.error(f"A compound order of {order.order_class} was entered. " f"{markets_error_message}")
            return

        if order.type not in order_types:
            logging.error(f"An order type of {order.type} was entered which is not " f"valid. {markets_error_message}")
            return
        args = self.create_order_args(order)
        try:
            if order.side == "buy":
                response = self.api.future_open_long(args[0], args[2], int(args[1]))
            else:
                response = self.api.future_open_short(args[0], args[2]), int(args[1])
            order.set_identifier(response.id)
            order.status = "open"
            order.update_raw(response)

        except Exception as e:
            order.set_error(e)
            message = str(e)
            full_message = f"{order} did not go through. The following error occurred: {message}"
            logging.info(colored(full_message, "red"))

        return order

    def create_order_args(self, order):
        """Will create the args for the vanilla `create_order` submission.
        Parameters
        ----------
        order

        Returns
        -------
        create_order api arguments : dict

        """
        if order.type != "limit":
            raise ValueError("Only support LIMIT order")
        args = [
            f"{order.exchange},{order.symbol}",
            order.quantity,
            order.limit_price
        ]
        return args

    def cancel_order(self, order):
        """Cancel an order"""
        try:            
            response = self.api.future_order_cancel(f"{order.exchange},{order.symbol}", order.identifier)
        except Exception as e:
            print(e)
        else:
            if order.identifier == response.id:
                order.set_canceled()

    def get_historical_account_value(self):
        logging.error("The function get_historical_account_value is not " "implemented yet for Vanilla.")
        return {"hourly": None, "daily": None}

    def wait_for_order_registration(self, order):
        """Wait for the registration of the orders with the broker.

        Not yet implemented, requires streaming.
        """
        raise NotImplementedError(
            "Waiting for an order registration is not yet implemented, "
            "requires streaming. Check the order status at each interval."
        )

    def wait_for_order_registrations(self, orders):
        """Wait for the registration of the order with the broker.

        Not yet implemented, requires streaming.
        """
        raise NotImplementedError(
            "Waiting for an order registration is not yet implemented,"
            "requires streaming. Check the order status at each interval."
        )

    def wait_for_order_execution(self, order):
        """Wait for order to fill.

        Not yet implemented, requires streaming.
        """
        raise NotImplementedError(
            "Waiting for an order execution is not yet implemented,"
            "requires streaming. Check the order status at each interval."
        )

    def wait_for_order_executions(self, order):
        """Wait for orders to fill.

        Not yet implemented, requires streaming.
        """
        raise NotImplementedError(
            "Waiting for an order execution is not yet implemented,"
            "requires streaming. Check the order status at each interval."
        )

    def _get_stream_object(self):
        pass

    def _register_stream_events(self):
        pass

    def _run_stream(self):
        pass
