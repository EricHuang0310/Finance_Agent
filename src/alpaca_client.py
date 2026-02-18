"""
Alpaca Markets API Client
Wraps alpaca-py SDK for stock and crypto trading.

Requires:
    pip install alpaca-py
"""

import os
from datetime import datetime, timedelta
from typing import Optional, List

from dotenv import load_dotenv

load_dotenv("config/.env")


class AlpacaClient:
    """Wrapper around Alpaca API for market data and trading."""

    def __init__(self):
        from alpaca.trading.client import TradingClient
        from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient

        api_key = os.getenv("ALPACA_API_KEY")
        api_secret = os.getenv("ALPACA_API_SECRET")
        self.is_paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"

        if not api_key or not api_secret:
            raise ValueError("ALPACA_API_KEY and ALPACA_API_SECRET must be set in config/.env")

        self.trading_client = TradingClient(api_key, api_secret, paper=self.is_paper)
        self.stock_data_client = StockHistoricalDataClient(api_key, api_secret)
        self.crypto_data_client = CryptoHistoricalDataClient(api_key, api_secret)
        self._api_key = api_key
        self._api_secret = api_secret

        print(f"✅ Alpaca client initialized ({'PAPER' if self.is_paper else 'LIVE'})")

    # ──────────────────────────────────────────────
    # Market Data
    # ──────────────────────────────────────────────

    def get_stock_bars(self, symbol: str, timeframe: str = "1Day", lookback_days: int = 90):
        """Fetch historical stock bars as a DataFrame."""
        import pandas as pd
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        tf_map = {"1Day": TimeFrame.Day, "1Hour": TimeFrame.Hour, "1Min": TimeFrame.Minute}
        tf = tf_map.get(timeframe, TimeFrame.Day)

        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=datetime.now() - timedelta(days=lookback_days),
        )

        bars = self.stock_data_client.get_stock_bars(request)
        df = bars.df

        if isinstance(df.index, pd.MultiIndex):
            df = df.loc[symbol]

        return df

    def get_crypto_bars(self, symbol: str, timeframe: str = "1Day", lookback_days: int = 90):
        """Fetch historical crypto bars as a DataFrame."""
        import pandas as pd
        from alpaca.data.requests import CryptoBarsRequest
        from alpaca.data.timeframe import TimeFrame

        tf_map = {"1Day": TimeFrame.Day, "1Hour": TimeFrame.Hour, "1Min": TimeFrame.Minute}
        tf = tf_map.get(timeframe, TimeFrame.Day)

        request = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=datetime.now() - timedelta(days=lookback_days),
        )

        bars = self.crypto_data_client.get_crypto_bars(request)
        df = bars.df

        if isinstance(df.index, pd.MultiIndex):
            df = df.loc[symbol]

        return df

    # ──────────────────────────────────────────────
    # News
    # ──────────────────────────────────────────────

    def get_news(self, symbol: str, days: int = 3, limit: int = 50) -> list:
        """Fetch recent news articles for a symbol from Alpaca News API."""
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest

        news_client = NewsClient(self._api_key, self._api_secret)

        # Strip slash for crypto symbols (BTC/USD -> BTCUSD) for news query
        query_symbol = symbol.replace("/", "")

        request = NewsRequest(
            symbols=query_symbol,
            start=datetime.now() - timedelta(days=days),
            limit=limit,
            sort="desc",
        )

        result = news_client.get_news(request)
        if hasattr(result, "data") and isinstance(result.data, dict):
            return result.data.get("news", [])
        return []

    # ──────────────────────────────────────────────
    # Market Hours
    # ──────────────────────────────────────────────

    def is_market_open(self) -> dict:
        """Check if market is currently open using Alpaca's clock API."""
        clock = self.trading_client.get_clock()
        return {
            "is_open": clock.is_open,
            "next_open": clock.next_open.isoformat() if clock.next_open else None,
            "next_close": clock.next_close.isoformat() if clock.next_close else None,
        }

    # ──────────────────────────────────────────────
    # Account & Positions
    # ──────────────────────────────────────────────

    def get_account(self) -> dict:
        """Get account information."""
        account = self.trading_client.get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "portfolio_value": float(account.portfolio_value),
            "last_equity": float(account.last_equity),
            "buying_power": float(account.buying_power),
            "daytrade_count": account.daytrade_count,
        }

    def get_positions(self) -> list[dict]:
        """Get all open positions."""
        positions = self.trading_client.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
                "side": p.side.value,
            }
            for p in positions
        ]

    # ──────────────────────────────────────────────
    # Order Placement
    # ──────────────────────────────────────────────

    def place_market_order(self, symbol: str, qty: float, side: str = "buy") -> dict:
        """Place a simple market order."""
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )

        order = self.trading_client.submit_order(request)
        return {"id": str(order.id), "status": order.status.value}

    def place_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str = "buy",
        stop_loss_price: float = 0,
        take_profit_price: float = 0,
    ) -> dict:
        """Place a bracket order with stop loss and take profit."""
        from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
        from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=take_profit_price),
            stop_loss=StopLossRequest(stop_price=stop_loss_price),
        )

        order = self.trading_client.submit_order(request)
        return {"id": str(order.id), "status": order.status.value}
