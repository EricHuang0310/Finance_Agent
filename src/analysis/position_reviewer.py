"""
Position Exit Review Module
Evaluates existing positions to determine if they should be closed
based on momentum/trend signals.
"""

from dataclasses import dataclass, asdict
from typing import Optional, Callable

import pandas as pd

from src.analysis.technical import TechnicalAnalyzer, TechnicalSignal


# Known crypto base symbols for format conversion (BTCUSD → BTC/USD)
_CRYPTO_BASES = {"BTC", "ETH", "SOL", "DOGE", "AVAX", "LINK", "DOT", "MATIC", "ADA", "XRP",
                 "LTC", "UNI", "AAVE", "SHIB", "BCH"}


@dataclass
class ExitSignal:
    """Result of exit evaluation for a single position."""
    symbol: str
    side: str               # "long" or "short" (from position)
    exit_action: str         # "close" or "hold"
    exit_reason: str
    exit_score: float        # 0.0 (strong hold) to 1.0 (urgent exit)
    current_price: float
    avg_entry_price: float
    qty: float
    unrealized_pl: float
    unrealized_plpc: float   # as decimal, e.g. 0.05 = 5%
    tech_score: float
    trend: str
    rsi: float
    atr: float

    def to_dict(self) -> dict:
        return asdict(self)


class PositionReviewer:
    """Evaluates existing positions for exit signals using momentum/trend criteria."""

    def __init__(self, config: dict):
        exit_cfg = config.get("position_exit", {})
        self.exit_threshold = exit_cfg.get("exit_threshold", 0.5)
        self.atr_multiplier = exit_cfg.get("atr_multiplier", 2.0)
        self.trailing_lookback_bars = exit_cfg.get("trailing_lookback_bars", 10)

        self.tech_analyzer = TechnicalAnalyzer()

    def review_position(
        self,
        position: dict,
        tech_signal: TechnicalSignal,
        market_score: float,
        bars: pd.DataFrame,
    ) -> ExitSignal:
        """Evaluate a single position for exit.

        Args:
            position: from AlpacaClient.get_positions() — has symbol, qty, side,
                      avg_entry_price, current_price, unrealized_pl, unrealized_plpc
            tech_signal: current technical analysis for this symbol
            market_score: current market analyst score for this symbol
            bars: historical bar data for trailing stop calculation
        """
        is_long = position["side"] == "long"
        exit_score = 0.0
        reasons = []

        # ── 1. Trend Reversal (weight: 0.35) ──
        if is_long and tech_signal.score < 0:
            contribution = 0.35 * min(1.0, abs(tech_signal.score))
            exit_score += contribution
            reasons.append(f"trend reversed (score={tech_signal.score:.2f})")
        elif not is_long and tech_signal.score > 0:
            contribution = 0.35 * min(1.0, abs(tech_signal.score))
            exit_score += contribution
            reasons.append(f"trend reversed (score={tech_signal.score:.2f})")

        # ── 2. Momentum Weakening (weight: 0.25) ──
        if is_long:
            if tech_signal.rsi < 50:
                rsi_component = min(1.0, (50 - tech_signal.rsi) / 20)
                exit_score += 0.125 * rsi_component
                reasons.append(f"RSI weakened ({tech_signal.rsi:.1f})")
            if tech_signal.trend != "bullish":
                exit_score += 0.125
                if "RSI" not in (reasons[-1] if reasons else ""):
                    reasons.append(f"EMA alignment broken (trend={tech_signal.trend})")
                else:
                    reasons.append(f"EMA alignment broken")
        else:
            if tech_signal.rsi > 50:
                rsi_component = min(1.0, (tech_signal.rsi - 50) / 20)
                exit_score += 0.125 * rsi_component
                reasons.append(f"RSI weakened ({tech_signal.rsi:.1f})")
            if tech_signal.trend != "bearish":
                exit_score += 0.125
                reasons.append(f"EMA alignment broken (trend={tech_signal.trend})")

        # ── 3. Trailing Stop via ATR (weight: 0.25) ──
        trailing_stop = None
        if bars is not None and len(bars) >= self.trailing_lookback_bars:
            closes = bars["close"].astype(float)
            recent = closes.tail(self.trailing_lookback_bars)
            current_price = position["current_price"]

            if is_long:
                recent_high = float(recent.max())
                trailing_stop = recent_high - self.atr_multiplier * tech_signal.atr
                if current_price < trailing_stop:
                    breach_pct = (trailing_stop - current_price) / max(trailing_stop, 0.01)
                    exit_score += 0.25 * min(1.0, breach_pct * 10 + 0.5)
                    reasons.append(f"trailing stop breached (${trailing_stop:.2f})")
            else:
                recent_low = float(recent.min())
                trailing_stop = recent_low + self.atr_multiplier * tech_signal.atr
                if current_price > trailing_stop:
                    breach_pct = (current_price - trailing_stop) / max(trailing_stop, 0.01)
                    exit_score += 0.25 * min(1.0, breach_pct * 10 + 0.5)
                    reasons.append(f"trailing stop breached (${trailing_stop:.2f})")

        # ── 4. Market Context Deterioration (weight: 0.15) ──
        if is_long and market_score < -0.2:
            exit_score += 0.15 * min(1.0, abs(market_score))
            reasons.append(f"market context bearish ({market_score:.2f})")
        elif not is_long and market_score > 0.2:
            exit_score += 0.15 * min(1.0, abs(market_score))
            reasons.append(f"market context bullish ({market_score:.2f})")

        exit_score = min(1.0, exit_score)
        exit_action = "close" if exit_score >= self.exit_threshold else "hold"
        exit_reason = "; ".join(reasons) if reasons else "holding - trend intact"

        return ExitSignal(
            symbol=position["symbol"],
            side=position["side"],
            exit_action=exit_action,
            exit_reason=exit_reason,
            exit_score=round(exit_score, 4),
            current_price=position["current_price"],
            avg_entry_price=position["avg_entry_price"],
            qty=position["qty"],
            unrealized_pl=position["unrealized_pl"],
            unrealized_plpc=position["unrealized_plpc"],
            tech_score=tech_signal.score,
            trend=tech_signal.trend,
            rsi=tech_signal.rsi,
            atr=tech_signal.atr,
        )

    def review_all(
        self,
        positions: list[dict],
        tech_signals: dict,
        market_data: dict,
        bars_getter: Callable,
    ) -> list[ExitSignal]:
        """Review all positions for exit signals.

        Args:
            positions: from AlpacaClient.get_positions()
            tech_signals: {"stocks": {...}, "crypto": {...}} from technical analyst
            market_data: {"stocks": {...}, "crypto": {...}} from market analyst
            bars_getter: callable(symbol, asset_type) -> pd.DataFrame
        """
        results = []

        for pos in positions:
            symbol = pos["symbol"]
            asset_type = self._detect_asset_type(symbol)
            bars_symbol = self._to_bars_symbol(symbol) if asset_type == "crypto" else symbol

            # Get or compute technical signal
            tech_signal = self._get_tech_signal(symbol, bars_symbol, asset_type, tech_signals, bars_getter)
            if tech_signal is None:
                print(f"  ⚠️  {symbol}: cannot analyze, skipping exit review")
                continue

            # Get market score
            market_score = self._get_market_score(symbol, asset_type, market_data)

            # Get bars for trailing stop
            bars = bars_getter(bars_symbol, asset_type)

            signal = self.review_position(pos, tech_signal, market_score, bars)
            results.append(signal)

        return results

    def _get_tech_signal(
        self,
        position_symbol: str,
        bars_symbol: str,
        asset_type: str,
        tech_signals: dict,
        bars_getter: Callable,
    ) -> Optional[TechnicalSignal]:
        """Get tech signal from cache or compute on-demand."""
        category = "crypto" if asset_type == "crypto" else "stocks"
        cached = tech_signals.get(category, {})

        # Try exact match first (position symbol or bars symbol)
        for try_sym in [position_symbol, bars_symbol]:
            if try_sym in cached:
                data = cached[try_sym]
                return TechnicalSignal(**data) if isinstance(data, dict) else data

        # Not in cache — compute on demand
        bars = bars_getter(bars_symbol, asset_type)
        if bars is not None and len(bars) >= 50:
            return self.tech_analyzer.analyze(bars, position_symbol, "1Day")

        return None

    def _get_market_score(self, symbol: str, asset_type: str, market_data: dict) -> float:
        """Get market score for a symbol, defaulting to 0."""
        category = "crypto" if asset_type == "crypto" else "stocks"
        return market_data.get(category, {}).get(symbol, {}).get("market_score", 0.0)

    @staticmethod
    def _detect_asset_type(symbol: str) -> str:
        """Detect if a position symbol is crypto or stock."""
        # Alpaca crypto positions use symbols like BTCUSD, ETHUSD
        if symbol.endswith("USD") and len(symbol) >= 6:
            base = symbol[:-3]
            if base in _CRYPTO_BASES:
                return "crypto"
        return "stock"

    @staticmethod
    def _to_bars_symbol(symbol: str) -> str:
        """Convert position symbol to bars API format (BTCUSD → BTC/USD)."""
        if symbol.endswith("USD") and len(symbol) >= 6:
            base = symbol[:-3]
            if base in _CRYPTO_BASES:
                return f"{base}/USD"
        return symbol
