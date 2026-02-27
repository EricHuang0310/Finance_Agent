"""
Symbol Screener Module
Dynamically discovers tradeable symbols using Alpaca's market data APIs.

Screens stocks by:
- Volume (most active)
- Price momentum (top gainers/losers)
- Volatility
- Liquidity filters (min price, min volume)

Screens crypto by:
- Volume leaders
- Price momentum
"""

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd


class SymbolScreener:
    """Scans the market to find interesting symbols for the trading pipeline."""

    def __init__(self, alpaca_client, config: dict, bars_getter=None):
        self.client = alpaca_client
        self._bars_getter = bars_getter
        self.screener_cfg = config.get("screener", {})

        # Defaults
        self.max_stocks = self.screener_cfg.get("max_stocks", 20)
        self.max_crypto = self.screener_cfg.get("max_crypto", 5)
        self.min_price = self.screener_cfg.get("min_price", 5.0)
        self.max_price = self.screener_cfg.get("max_price", 1000.0)
        self.min_avg_volume = self.screener_cfg.get("min_avg_volume", 500_000)
        self.min_market_cap = self.screener_cfg.get("min_market_cap", 1_000_000_000)
        self.lookback_days = self.screener_cfg.get("lookback_days", 20)

        # Universe: broad set of liquid, well-known stocks to screen from
        # This avoids scanning the entire market (thousands of symbols)
        self._stock_universe = self.screener_cfg.get("universe", [
            # Mega-cap tech
            "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO",
            "ORCL", "CRM", "ADBE", "AMD", "INTC", "QCOM", "TXN", "MU",
            "AMAT", "LRCX", "KLAC", "MRVL", "SNPS", "CDNS", "PANW", "CRWD",
            # Finance
            "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW",
            # Healthcare
            "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "AMGN",
            # Consumer
            "WMT", "COST", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW",
            # Energy
            "XOM", "CVX", "COP", "SLB", "EOG",
            # Industrial
            "CAT", "DE", "UNP", "HON", "RTX", "LMT", "GE", "BA",
            # Communication
            "NFLX", "DIS", "CMCSA", "VZ", "T",
            # Crypto-adjacent / High-vol
            "COIN", "MSTR", "PLTR", "SOFI", "HOOD", "RBLX", "SNAP", "SQ",
            # Semis
            "TSM", "ASML", "ARM", "SMCI",
            # ETFs (optional, can be screened too)
            "SPY", "QQQ", "IWM", "XLF", "XLE", "XLK",
        ])

        self._crypto_universe = self.screener_cfg.get("crypto_universe", [
            "BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "AVAX/USD",
            "LINK/USD", "DOT/USD", "MATIC/USD", "ADA/USD", "XRP/USD",
        ])

    def _get_bars(self, symbol: str, asset_type: str) -> Optional[pd.DataFrame]:
        """Fetch bars via injected getter (cache-aware) or direct client call."""
        if self._bars_getter:
            return self._bars_getter(symbol, asset_type, lookback_days=self.lookback_days)
        if asset_type == "crypto":
            return self.client.get_crypto_bars(symbol, "1Day", lookback_days=self.lookback_days)
        return self.client.get_stock_bars(symbol, "1Day", lookback_days=self.lookback_days)

    def screen_stocks(self) -> list[dict]:
        """
        Screen the stock universe and return top candidates ranked by a
        composite activity score (volume surge + momentum + volatility).
        """
        print(f"\n  Screening {len(self._stock_universe)} stocks...")
        results = []

        for symbol in self._stock_universe:
            try:
                bars = self._get_bars(symbol, "stock")
                if bars is None or len(bars) < 10:
                    continue

                info = self._compute_metrics(bars, symbol)
                if info is None:
                    continue

                # Apply filters
                if info["latest_close"] < self.min_price:
                    continue
                if info["latest_close"] > self.max_price:
                    continue
                if info["avg_volume"] < self.min_avg_volume:
                    continue

                results.append(info)

            except Exception as e:
                # Silently skip symbols that fail (delisted, no data, etc.)
                pass

        # Rank by composite activity score
        results.sort(key=lambda x: x["activity_score"], reverse=True)

        top = results[: self.max_stocks]
        print(f"  Selected {len(top)} stocks from {len(results)} that passed filters")
        return top

    def screen_crypto(self) -> list[dict]:
        """Screen crypto universe and return top candidates."""
        print(f"\n  Screening {len(self._crypto_universe)} crypto pairs...")
        results = []

        for symbol in self._crypto_universe:
            try:
                bars = self._get_bars(symbol, "crypto")
                if bars is None or len(bars) < 10:
                    continue

                info = self._compute_metrics(bars, symbol)
                if info is None:
                    continue

                results.append(info)

            except Exception:
                pass

        results.sort(key=lambda x: x["activity_score"], reverse=True)

        top = results[: self.max_crypto]
        print(f"  Selected {len(top)} crypto from {len(results)} candidates")
        return top

    def screen_all(self) -> dict:
        """
        Run full screening and return a dynamic watchlist.

        Returns:
            {
                "stocks": ["NVDA", "TSLA", ...],
                "crypto": ["BTC/USD", "ETH/USD", ...],
                "details": { "NVDA": {...}, ... },
                "timestamp": "..."
            }
        """
        stock_results = self.screen_stocks()
        crypto_results = self.screen_crypto()

        stock_symbols = [r["symbol"] for r in stock_results]
        crypto_symbols = [r["symbol"] for r in crypto_results]

        details = {}
        for r in stock_results + crypto_results:
            details[r["symbol"]] = {
                "latest_close": r["latest_close"],
                "momentum_pct": round(r["momentum_pct"], 2),
                "volume_ratio": round(r["volume_ratio"], 2),
                "volatility": round(r["volatility"], 4),
                "activity_score": round(r["activity_score"], 4),
            }

        return {
            "stocks": stock_symbols,
            "crypto": crypto_symbols,
            "details": details,
            "timestamp": datetime.now().isoformat(),
            "screened_from": {
                "stock_universe": len(self._stock_universe),
                "crypto_universe": len(self._crypto_universe),
            },
        }

    def _compute_metrics(self, bars: pd.DataFrame, symbol: str) -> Optional[dict]:
        """Compute screening metrics from bar data."""
        if len(bars) < 5:
            return None

        closes = bars["close"].astype(float)
        volumes = bars["volume"].astype(float)

        latest_close = closes.iloc[-1]
        avg_volume = volumes.mean()

        # Volume ratio: latest volume vs 20-day average
        latest_volume = volumes.iloc[-1]
        volume_ratio = latest_volume / max(avg_volume, 1)

        # Momentum: % change over the lookback period
        first_close = closes.iloc[0]
        momentum_pct = ((latest_close - first_close) / first_close) * 100

        # Short-term momentum (5-day)
        if len(closes) >= 5:
            close_5d_ago = closes.iloc[-5]
            momentum_5d = ((latest_close - close_5d_ago) / close_5d_ago) * 100
        else:
            momentum_5d = momentum_pct

        # Volatility: std of daily returns
        returns = closes.pct_change().dropna()
        volatility = returns.std() if len(returns) > 1 else 0.0

        # Composite activity score:
        # High volume surge + strong momentum (either direction) + moderate volatility
        vol_surge_score = min(3.0, max(0, volume_ratio - 1.0))  # 0-3 points
        momentum_score = min(3.0, abs(momentum_5d) / 5.0)  # 0-3 points (5% = 1 pt)
        volatility_score = min(2.0, volatility * 50)  # 0-2 points

        activity_score = (
            vol_surge_score * 0.4
            + momentum_score * 0.4
            + volatility_score * 0.2
        )

        return {
            "symbol": symbol,
            "latest_close": latest_close,
            "avg_volume": avg_volume,
            "latest_volume": latest_volume,
            "volume_ratio": volume_ratio,
            "momentum_pct": momentum_pct,
            "momentum_5d": momentum_5d,
            "volatility": volatility,
            "activity_score": activity_score,
        }
