"""
Technical Analysis Module
Calculates indicators and generates trading signals.
"""

from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd
import numpy as np

try:
    from ta.trend import ADXIndicator
    _HAS_TA = True
except ImportError:
    _HAS_TA = False


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
    adx: float = 0.0
    macd_histogram_trend: str = "flat"  # "expanding", "contracting", "flat"
    volume_confirmation: bool = False
    confidence: float = 1.0  # 0.0-1.0, indicator agreement level
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    data_warning: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class TechnicalAnalyzer:
    """Calculate technical indicators and generate composite scores."""

    def analyze(self, bars: pd.DataFrame, symbol: str, timeframe: str = "1Day") -> TechnicalSignal:
        """Run full technical analysis on a symbol's bar data."""
        close = bars["close"].astype(float)
        high = bars["high"].astype(float)
        low = bars["low"].astype(float)
        volume = bars["volume"].astype(float)

        num_bars = len(close)

        # Data quality check: single-bar move > 15%
        data_warning = None
        if num_bars >= 2:
            last_return = abs((float(close.iloc[-1]) - float(close.iloc[-2])) / float(close.iloc[-2]))
            if last_return > 0.15:
                data_warning = f"Single-bar move {last_return*100:.1f}% detected"

        # Calculate indicators
        rsi = self._rsi(close)
        macd, macd_signal, macd_hist = self._macd(close)
        bb_upper, bb_middle, bb_lower = self._bollinger_bands(close)
        ema_20 = self._ema(close, 20)
        ema_50 = self._ema(close, 50)
        ema_200 = self._ema(close, 200)
        atr = self._atr(high, low, close)

        # ADX
        adx = self._adx(high, low, close) if num_bars >= 20 else 0.0

        # MACD histogram trend (last 5 bars)
        macd_histogram_trend = self._macd_histogram_trend(close)

        # Volume confirmation
        volume_confirmation = self._volume_confirmation(close, volume)

        latest_close = float(close.iloc[-1])

        # Calculate composite score and confidence
        score, confidence = self._compute_score(
            rsi=rsi, macd=macd, macd_signal=macd_signal,
            close=latest_close, bb_upper=bb_upper, bb_lower=bb_lower,
            ema_20=ema_20, ema_50=ema_50, ema_200=ema_200,
            adx=adx, volume_confirmation=volume_confirmation,
            num_bars=num_bars,
        )

        # ADX < 20 → weak trend, penalize confidence
        if adx > 0 and adx < 20:
            confidence *= 0.7

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
            adx=round(adx, 2),
            macd_histogram_trend=macd_histogram_trend,
            volume_confirmation=volume_confirmation,
            entry_price=round(entry_price, 2),
            stop_loss=stop_loss,
            take_profit=take_profit,
            data_warning=data_warning,
        )

    def _compute_score(self, rsi, macd, macd_signal, close, bb_upper, bb_lower,
                       ema_20, ema_50, ema_200, adx=0, volume_confirmation=False,
                       num_bars: int = 90) -> tuple[float, float]:
        """Compute momentum/trend composite score from -1.0 to 1.0 plus confidence.

        Weights: RSI 0.20, MACD 0.20, EMA 0.20, BB 0.15, ADX 0.15, Volume 0.10
        """
        score = 0.0
        component_signs = []

        # RSI momentum component (weight: 0.20)
        rsi_component = 0.0
        if 50 <= rsi <= 70:
            rsi_component = 0.20 * ((rsi - 50) / 20)
        elif 70 < rsi <= 80:
            rsi_component = 0.20 * 0.8
        elif rsi > 80:
            rsi_component = 0.20 * 0.3
        elif 30 <= rsi < 50:
            rsi_component = -0.20 * ((50 - rsi) / 20)
        elif 20 <= rsi < 30:
            rsi_component = -0.20 * 0.8
        elif rsi < 20:
            rsi_component = -0.20 * 0.3
        score += rsi_component
        if abs(rsi_component) > 0.01:
            component_signs.append(1 if rsi_component > 0 else -1)

        # MACD crossover (weight: 0.20)
        if macd > macd_signal:
            score += 0.20
            component_signs.append(1)
        else:
            score -= 0.20
            component_signs.append(-1)

        # EMA alignment (weight: 0.20, reduced to 0.08 if insufficient data for EMA-200)
        ema_weight = 0.20 if num_bars >= 200 else 0.08
        if ema_20 > ema_50 > ema_200:
            score += ema_weight
            component_signs.append(1)
        elif ema_20 < ema_50 < ema_200:
            score -= ema_weight
            component_signs.append(-1)

        # Bollinger Band trend component (weight: 0.15)
        bb_component = 0.0
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            bb_position = (close - bb_lower) / bb_range
            if bb_position > 0.8:
                bb_component = 0.15 * min(1.0, (bb_position - 0.5) * 2)
            elif bb_position < 0.2:
                bb_component = -0.15 * min(1.0, (0.5 - bb_position) * 2)
        score += bb_component
        if abs(bb_component) > 0.01:
            component_signs.append(1 if bb_component > 0 else -1)

        # ADX trend strength (weight: 0.15)
        if adx > 0:
            adx_component = 0.0
            if adx > 25:
                # Strong trend — amplify the existing score direction
                trend_dir = 1 if score > 0 else -1 if score < 0 else 0
                adx_component = 0.15 * trend_dir * min(1.0, (adx - 25) / 25)
            elif adx < 20:
                # Weak trend — dampen toward zero
                adx_component = 0.0
            score += adx_component
            if abs(adx_component) > 0.01:
                component_signs.append(1 if adx_component > 0 else -1)

        # Volume confirmation (weight: 0.10)
        if volume_confirmation:
            vol_dir = 1 if score > 0 else -1 if score < 0 else 0
            score += 0.10 * vol_dir
            if vol_dir != 0:
                component_signs.append(vol_dir)

        # ── Confidence calculation ────────────────
        if len(component_signs) >= 2:
            positive = sum(1 for s in component_signs if s > 0)
            negative = sum(1 for s in component_signs if s < 0)
            total = len(component_signs)
            majority = max(positive, negative)
            agreement_ratio = majority / total
            confidence = 0.3 + 0.7 * ((agreement_ratio - 0.5) / 0.5) if agreement_ratio > 0.5 else 0.3
        else:
            confidence = 0.3

        # Penalize insufficient data (< 50 bars)
        if num_bars < 50:
            confidence *= 0.6

        confidence = max(0.1, min(1.0, confidence))

        return max(-1.0, min(1.0, score)), confidence

    def _adx(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
        """Calculate ADX using ta library or fallback."""
        if _HAS_TA and len(close) >= period + 1:
            try:
                indicator = ADXIndicator(high=high, low=low, close=close, window=period)
                adx_series = indicator.adx()
                val = adx_series.iloc[-1]
                return float(val) if not pd.isna(val) else 0.0
            except Exception:
                return 0.0
        return 0.0

    def _macd_histogram_trend(self, close: pd.Series, window: int = 5) -> str:
        """Analyze MACD histogram direction over recent bars."""
        if len(close) < 30:
            return "flat"
        _, _, hist_series = self._macd_series(close)
        recent = hist_series.tail(window).values
        recent = [float(x) for x in recent if not pd.isna(x)]
        if len(recent) < 3:
            return "flat"
        diffs = [recent[i] - recent[i-1] for i in range(1, len(recent))]
        avg_diff = sum(diffs) / len(diffs)
        if avg_diff > 0.01:
            return "expanding"
        elif avg_diff < -0.01:
            return "contracting"
        return "flat"

    def _volume_confirmation(self, close: pd.Series, volume: pd.Series) -> bool:
        """Check if volume confirms price direction (last bar)."""
        if len(close) < 2 or len(volume) < 2:
            return False
        price_up = float(close.iloc[-1]) > float(close.iloc[-2])
        vol_up = float(volume.iloc[-1]) > float(volume.iloc[-2])
        return price_up == vol_up

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
    def _macd_series(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        """Return full MACD series (not just last values)."""
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

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
