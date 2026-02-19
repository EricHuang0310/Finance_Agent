"""
Historical Data Loader for Backtesting.

Fetches OHLCV data from the real Alpaca API and caches it locally as Parquet files
so subsequent backtest runs load instantly from disk.
"""

import os
from datetime import datetime, timedelta, date
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv("config/.env")


class DataLoader:
    """Fetches and caches historical market data from Alpaca."""

    def __init__(self, cache_dir: str = "data/backtest_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Lazy-init Alpaca clients (only when actually fetching)
        self._stock_client = None
        self._crypto_client = None

    def _get_stock_client(self):
        if self._stock_client is None:
            from alpaca.data.historical import StockHistoricalDataClient

            api_key = os.getenv("ALPACA_API_KEY")
            api_secret = os.getenv("ALPACA_API_SECRET")
            if not api_key or not api_secret:
                raise ValueError("ALPACA_API_KEY and ALPACA_API_SECRET must be set in config/.env")
            self._stock_client = StockHistoricalDataClient(api_key, api_secret)
        return self._stock_client

    def load_bars(
        self,
        symbol: str,
        asset_type: str = "stock",
        start_date: date = None,
        end_date: date = None,
        lookback_days: int = 200,
        timeframe: str = "1Day",
    ) -> pd.DataFrame | None:
        """
        Load historical bars for a single symbol.

        Data is fetched from (start_date - lookback_days) through end_date
        to ensure enough history for indicator warmup (EMA-200 needs ~200 bars).

        Returns:
            DataFrame with columns [open, high, low, close, volume], DatetimeIndex.
            None if no data available.
        """
        # Calculate actual fetch range (include lookback buffer)
        actual_start = start_date - timedelta(days=int(lookback_days * 1.5))  # Extra buffer for weekends/holidays
        actual_end = end_date

        # Check cache first
        cache_path = self._cache_path(symbol, asset_type, timeframe, actual_start, actual_end)
        if cache_path.exists():
            print(f"  📦 Cache hit: {symbol}")
            df = pd.read_parquet(cache_path)
            # Ensure DatetimeIndex
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            return df

        # Fetch from Alpaca API
        print(f"  🌐 Fetching: {symbol} ({actual_start} to {actual_end})")
        try:
            if asset_type == "crypto":
                df = self._fetch_crypto(symbol, actual_start, actual_end, timeframe)
            else:
                df = self._fetch_stock(symbol, actual_start, actual_end, timeframe)

            if df is None or df.empty:
                print(f"  ⚠️  No data for {symbol}")
                return None

            # Normalize columns (Alpaca sometimes includes extra columns)
            required_cols = ["open", "high", "low", "close", "volume"]
            for col in required_cols:
                if col not in df.columns:
                    print(f"  ⚠️  Missing column '{col}' for {symbol}")
                    return None

            df = df[required_cols].copy()

            # Save to cache
            df.to_parquet(cache_path)
            print(f"  💾 Cached: {symbol} ({len(df)} bars)")

            return df

        except Exception as e:
            print(f"  ❌ Failed to fetch {symbol}: {e}")
            return None

    def load_all(
        self,
        symbols: dict,
        start_date: date,
        end_date: date,
        lookback_days: int = 200,
    ) -> dict[str, pd.DataFrame]:
        """
        Load bars for all symbols.

        Args:
            symbols: {"stocks": ["AAPL", "NVDA", ...], "crypto": ["BTC/USD", ...]}
            start_date: Backtest start date
            end_date: Backtest end date
            lookback_days: Extra history before start_date for indicator warmup

        Returns:
            {symbol: DataFrame} mapping for all symbols with available data
        """
        all_bars = {}

        stocks = symbols.get("stocks", [])
        crypto = symbols.get("crypto", [])

        if stocks:
            print(f"\n📊 Loading {len(stocks)} stock symbols...")
            for symbol in stocks:
                bars = self.load_bars(symbol, "stock", start_date, end_date, lookback_days)
                if bars is not None and not bars.empty:
                    all_bars[symbol] = bars

        if crypto:
            print(f"\n🪙 Loading {len(crypto)} crypto symbols...")
            for symbol in crypto:
                bars = self.load_bars(symbol, "crypto", start_date, end_date, lookback_days)
                if bars is not None and not bars.empty:
                    all_bars[symbol] = bars

        return all_bars

    def _fetch_stock(
        self, symbol: str, start: date, end: date, timeframe: str
    ) -> pd.DataFrame | None:
        """Fetch stock bars from Alpaca API."""
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        tf_map = {"1Day": TimeFrame.Day, "1Hour": TimeFrame.Hour, "1Min": TimeFrame.Minute}
        tf = tf_map.get(timeframe, TimeFrame.Day)

        client = self._get_stock_client()
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=datetime.combine(start, datetime.min.time()),
            end=datetime.combine(end, datetime.max.time()),
        )

        bars = client.get_stock_bars(request)
        df = bars.df

        if isinstance(df.index, pd.MultiIndex):
            if symbol in df.index.get_level_values(0):
                df = df.loc[symbol]
            else:
                return None

        return df

    def _fetch_crypto(
        self, symbol: str, start: date, end: date, timeframe: str
    ) -> pd.DataFrame | None:
        """Fetch crypto bars from Alpaca API."""
        from alpaca.data.historical import CryptoHistoricalDataClient
        from alpaca.data.requests import CryptoBarsRequest
        from alpaca.data.timeframe import TimeFrame

        tf_map = {"1Day": TimeFrame.Day, "1Hour": TimeFrame.Hour, "1Min": TimeFrame.Minute}
        tf = tf_map.get(timeframe, TimeFrame.Day)

        if self._crypto_client is None:
            api_key = os.getenv("ALPACA_API_KEY")
            api_secret = os.getenv("ALPACA_API_SECRET")
            self._crypto_client = CryptoHistoricalDataClient(api_key, api_secret)

        request = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=datetime.combine(start, datetime.min.time()),
            end=datetime.combine(end, datetime.max.time()),
        )

        bars = self._crypto_client.get_crypto_bars(request)
        df = bars.df

        if isinstance(df.index, pd.MultiIndex):
            if symbol in df.index.get_level_values(0):
                df = df.loc[symbol]
            else:
                return None

        return df

    def _cache_path(
        self, symbol: str, asset_type: str, timeframe: str, start: date, end: date
    ) -> Path:
        """Generate deterministic cache file path."""
        # Sanitize symbol for filename (e.g., BTC/USD -> BTC_USD)
        safe_symbol = symbol.replace("/", "_")
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        filename = f"{safe_symbol}_{asset_type}_{timeframe}_{start_str}_{end_str}.parquet"
        return self.cache_dir / filename

    def clear_cache(self):
        """Remove all cached data files."""
        count = 0
        for f in self.cache_dir.glob("*.parquet"):
            f.unlink()
            count += 1
        print(f"🗑️  Cleared {count} cached files")
