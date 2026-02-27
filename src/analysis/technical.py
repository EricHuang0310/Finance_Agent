"""
Technical Analysis Module
Calculates indicators and generates trading signals.
"""

from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd
import numpy as np


@dataclass
class TechnicalSignal:
    """Result of technical analysis for a single symbol."""
    symbol: str
    timeframe: str
    score: float  # -1.0 (strong sell) to 1.0 (strong buy)
    trend: str  # "bullish", "bearish", "neutral"
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    ema_20: float
    ema_50: float
    ema_200: float
    atr: float
    confidence: float = 1.0  # 0.0-1.0, indicator agreement level
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


class TechnicalAnalyzer:
    """Calculate technical indicators and generate composite scores."""

    def analyze(self, bars: pd.DataFrame, symbol: str, timeframe: str = "1Day") -> TechnicalSignal:
        """Run full technical analysis on a symbol's bar data."""
        close = bars["close"].astype(float)
        high = bars["high"].astype(float)
        low = bars["low"].astype(float)

        # Calculate indicators
        rsi = self._rsi(close)
        macd, macd_signal, macd_hist = self._macd(close)
        bb_upper, bb_middle, bb_lower = self._bollinger_bands(close)
        ema_20 = self._ema(close, 20)
        ema_50 = self._ema(close, 50)
        ema_200 = self._ema(close, 200)
        atr = self._atr(high, low, close)

        latest_close = float(close.iloc[-1])

        # Calculate composite score and confidence
        score, confidence = self._compute_score(
            rsi=rsi, macd=macd, macd_signal=macd_signal,
            close=latest_close, bb_upper=bb_upper, bb_lower=bb_lower,
            ema_20=ema_20, ema_50=ema_50, ema_200=ema_200,
            num_bars=len(close),
        )

        # Determine trend
        if ema_20 > ema_50 > ema_200:
            trend = "bullish"
        elif ema_20 < ema_50 < ema_200:
            trend = "bearish"
        else:
            trend = "neutral"

        # Calculate entry/stop/target for positive signals
        entry_price = latest_close
        stop_loss = None
        take_profit = None

        if score > 0.3:
            # BUY signal: stop below, target above
            stop_loss = round(latest_close - 2 * atr, 2)
            take_profit = round(latest_close + 3 * atr, 2)
        elif score < -0.3:
            # SELL/SHORT signal: stop above, target below
            stop_loss = round(latest_close + 2 * atr, 2)
            take_profit = round(latest_close - 3 * atr, 2)

        return TechnicalSignal(
            symbol=symbol,
            timeframe=timeframe,
            score=round(score, 4),
            trend=trend,
            confidence=round(confidence, 4),
            rsi=round(rsi, 2),
            macd=round(macd, 4),
            macd_signal=round(macd_signal, 4),
            macd_histogram=round(macd_hist, 4),
            bb_upper=round(bb_upper, 2),
            bb_middle=round(bb_middle, 2),
            bb_lower=round(bb_lower, 2),
            ema_20=round(ema_20, 2),
            ema_50=round(ema_50, 2),
            ema_200=round(ema_200, 2),
            atr=round(atr, 4),
            entry_price=round(entry_price, 2),
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def _compute_score(self, rsi, macd, macd_signal, close, bb_upper, bb_lower,
                       ema_20, ema_50, ema_200, num_bars: int = 90) -> tuple[float, float]:
        """Compute momentum/trend composite score from -1.0 to 1.0 plus confidence.

        Returns (score, confidence) where confidence indicates indicator agreement.
        Positive score = bullish momentum (buy), Negative = bearish momentum (short).
        """
        score = 0.0

        # Track each component's direction for confidence calculation
        component_signs = []

        # RSI momentum component (weight: 0.25)
        rsi_component = 0.0
        if 50 <= rsi <= 70:
            rsi_component = 0.25 * ((rsi - 50) / 20)
        elif 70 < rsi <= 80:
            rsi_component = 0.25 * 0.8
        elif rsi > 80:
            rsi_component = 0.25 * 0.3
        elif 30 <= rsi < 50:
            rsi_component = -0.25 * ((50 - rsi) / 20)
        elif 20 <= rsi < 30:
            rsi_component = -0.25 * 0.8
        elif rsi < 20:
            rsi_component = -0.25 * 0.3
        score += rsi_component
        if abs(rsi_component) > 0.01:
            component_signs.append(1 if rsi_component > 0 else -1)

        # MACD crossover (weight: 0.25)
        if macd > macd_signal:
            score += 0.25
            component_signs.append(1)
        else:
            score -= 0.25
            component_signs.append(-1)

        # Bollinger Band trend component (weight: 0.25)
        bb_component = 0.0
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            bb_position = (close - bb_lower) / bb_range
            if bb_position > 0.8:
                bb_component = 0.25 * min(1.0, (bb_position - 0.5) * 2)
            elif bb_position < 0.2:
                bb_component = -0.25 * min(1.0, (0.5 - bb_position) * 2)
        score += bb_component
        if abs(bb_component) > 0.01:
            component_signs.append(1 if bb_component > 0 else -1)

        # EMA alignment (weight: 0.25, reduced to 0.10 if insufficient data for EMA-200)
        ema_weight = 0.25 if num_bars >= 200 else 0.10
        if ema_20 > ema_50 > ema_200:
            score += ema_weight
            component_signs.append(1)
        elif ema_20 < ema_50 < ema_200:
            score -= ema_weight
            component_signs.append(-1)
        # Mixed EMA = no clear direction, no entry in component_signs

        # ── Confidence calculation ────────────────
        # Based on indicator direction agreement + data sufficiency
        if len(component_signs) >= 2:
            positive = sum(1 for s in component_signs if s > 0)
            negative = sum(1 for s in component_signs if s < 0)
            total = len(component_signs)
            majority = max(positive, negative)
            # All agree → 1.0, 3:1 → 0.8, 2:2 → 0.5, 1:3 → 0.3
            agreement_ratio = majority / total
            confidence = 0.3 + 0.7 * ((agreement_ratio - 0.5) / 0.5) if agreement_ratio > 0.5 else 0.3
        else:
            confidence = 0.3

        # Penalize insufficient data (< 50 bars)
        if num_bars < 50:
            confidence *= 0.6

        confidence = max(0.1, min(1.0, confidence))

        return max(-1.0, min(1.0, score)), confidence

    @staticmethod
    def _rsi(close: pd.Series, period: int = 14) -> float:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).ewm(alpha=1/period, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/period, adjust=False).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])

    @staticmethod
    def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1])

    @staticmethod
    def _bollinger_bands(close: pd.Series, period: int = 20, std_dev: int = 2):
        middle = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        return float(upper.iloc[-1]), float(middle.iloc[-1]), float(lower.iloc[-1])

    @staticmethod
    def _ema(close: pd.Series, period: int) -> float:
        return float(close.ewm(span=period, adjust=False).mean().iloc[-1])

    @staticmethod
    def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return float(atr.iloc[-1])
