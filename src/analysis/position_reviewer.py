"""
Position Exit Review Module
Evaluates existing positions to determine if they should be closed
based on momentum/trend signals.
"""

from dataclasses import dataclass, asdict, field
from typing import Optional, Callable

import pandas as pd

from src.analysis.technical import TechnicalAnalyzer, TechnicalSignal


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
    exit_urgency: str = "normal"  # "high" if exit_score >= 0.7
    holding_days: int = 0
    exit_score_breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class PositionReviewer:
    """Evaluates existing positions for exit signals using momentum/trend criteria."""

    def __init__(self, config: dict):
        exit_cfg = config.get("position_exit", {})
        self.exit_threshold = exit_cfg.get("exit_threshold", 0.5)
        self.atr_multiplier = exit_cfg.get("atr_multiplier", 2.0)
        self.trailing_lookback_bars = exit_cfg.get("trailing_lookback_bars", 10)
        self.max_positions = config.get("risk", {}).get("max_positions", 8)

        self.tech_analyzer = TechnicalAnalyzer()

    def review_position(
        self,
        position: dict,
        tech_signal: TechnicalSignal,
        market_score: float,
        bars: pd.DataFrame,
        sentiment_data: dict = None,
    ) -> ExitSignal:
        """Evaluate a single position for exit.

        Weights: trend 0.30, momentum 0.20, ATR trailing 0.20,
                 market 0.10, time_decay 0.10, event_risk 0.10
        """
        is_long = position["side"] == "long"
        exit_score = 0.0
        reasons = []
        breakdown = {}

        # Compute holding days
        holding_days = 0
        if position.get("avg_entry_price") and position.get("change_today") is not None:
            # Approximate holding days from position data if available
            pass
        # Use created_at if available
        if position.get("created_at"):
            try:
                from datetime import datetime, timezone
                created = position["created_at"]
                if isinstance(created, str):
                    # Parse ISO format
                    created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                holding_days = (now - created).days
            except Exception:
                pass

        # ── 1. Trend Reversal (weight: 0.30) ──
        trend_contribution = 0.0
        if is_long and tech_signal.score < 0:
            trend_contribution = 0.30 * min(1.0, abs(tech_signal.score))
            reasons.append(f"trend reversed (score={tech_signal.score:.2f})")
        elif not is_long and tech_signal.score > 0:
            trend_contribution = 0.30 * min(1.0, abs(tech_signal.score))
            reasons.append(f"trend reversed (score={tech_signal.score:.2f})")
        exit_score += trend_contribution
        breakdown["trend_reversal"] = round(trend_contribution, 4)

        # ── 2. Momentum Weakening (weight: 0.20) ──
        momentum_contribution = 0.0
        if is_long:
            if tech_signal.rsi < 50:
                rsi_component = min(1.0, (50 - tech_signal.rsi) / 20)
                momentum_contribution += 0.10 * rsi_component
                reasons.append(f"RSI weakened ({tech_signal.rsi:.1f})")
            if tech_signal.trend != "bullish":
                momentum_contribution += 0.10
                reasons.append(f"EMA alignment broken (trend={tech_signal.trend})")
        else:
            if tech_signal.rsi > 50:
                rsi_component = min(1.0, (tech_signal.rsi - 50) / 20)
                momentum_contribution += 0.10 * rsi_component
                reasons.append(f"RSI weakened ({tech_signal.rsi:.1f})")
            if tech_signal.trend != "bearish":
                momentum_contribution += 0.10
                reasons.append(f"EMA alignment broken (trend={tech_signal.trend})")
        exit_score += momentum_contribution
        breakdown["momentum_weakening"] = round(momentum_contribution, 4)

        # ── 3. Trailing Stop via ATR (weight: 0.20) ──
        trailing_contribution = 0.0
        if bars is not None and len(bars) >= self.trailing_lookback_bars:
            closes = bars["close"].astype(float)
            recent = closes.tail(self.trailing_lookback_bars)
            current_price = position["current_price"]

            if is_long:
                recent_high = float(recent.max())
                trailing_stop = recent_high - self.atr_multiplier * tech_signal.atr
                if current_price < trailing_stop:
                    breach_pct = (trailing_stop - current_price) / max(trailing_stop, 0.01)
                    trailing_contribution = 0.20 * min(1.0, breach_pct * 10 + 0.5)
                    reasons.append(f"trailing stop breached (${trailing_stop:.2f})")
            else:
                recent_low = float(recent.min())
                trailing_stop = recent_low + self.atr_multiplier * tech_signal.atr
                if current_price > trailing_stop:
                    breach_pct = (current_price - trailing_stop) / max(trailing_stop, 0.01)
                    trailing_contribution = 0.20 * min(1.0, breach_pct * 10 + 0.5)
                    reasons.append(f"trailing stop breached (${trailing_stop:.2f})")
        exit_score += trailing_contribution
        breakdown["atr_trailing_stop"] = round(trailing_contribution, 4)

        # ── 4. Market Context Deterioration (weight: 0.10) ──
        market_contribution = 0.0
        if is_long and market_score < -0.2:
            market_contribution = 0.10 * min(1.0, abs(market_score))
            reasons.append(f"market context bearish ({market_score:.2f})")
        elif not is_long and market_score > 0.2:
            market_contribution = 0.10 * min(1.0, abs(market_score))
            reasons.append(f"market context bullish ({market_score:.2f})")
        exit_score += market_contribution
        breakdown["market_context"] = round(market_contribution, 4)

        # ── 5. Time Decay (weight: 0.10) ──
        time_decay_contribution = 0.0
        if holding_days > 20:
            time_decay_contribution = 0.10
        elif holding_days > 10:
            time_decay_contribution = 0.06
        elif holding_days > 5:
            time_decay_contribution = 0.03
        if time_decay_contribution > 0:
            exit_score += time_decay_contribution
            reasons.append(f"time decay ({holding_days}d held)")
        breakdown["time_decay"] = round(time_decay_contribution, 4)

        # ── 6. Event Risk (weight: 0.10) ──
        event_contribution = 0.0
        if sentiment_data:
            sym_sent = sentiment_data.get("symbols", {}).get(position["symbol"], {})
            if sym_sent.get("upcoming_earnings"):
                event_contribution = 0.07
                reasons.append("upcoming earnings")
            if sym_sent.get("binary_event"):
                event_contribution = 0.10
                reasons.append("binary event risk")
        exit_score += event_contribution
        breakdown["event_risk"] = round(event_contribution, 4)

        exit_score = min(1.0, exit_score)
        exit_action = "close" if exit_score >= self.exit_threshold else "hold"
        exit_reason = "; ".join(reasons) if reasons else "holding - trend intact"
        exit_urgency = "high" if exit_score >= 0.7 else "normal"

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
            exit_urgency=exit_urgency,
            holding_days=holding_days,
            exit_score_breakdown=breakdown,
        )

    def review_all(
        self,
        positions: list[dict],
        tech_signals: dict,
        market_data: dict,
        bars_getter: Callable,
        sentiment_data: dict = None,
    ) -> list[ExitSignal]:
        """Review all positions for exit signals."""
        results = []

        for pos in positions:
            symbol = pos["symbol"]

            # Get or compute technical signal
            tech_signal = self._get_tech_signal(symbol, symbol, "stock", tech_signals, bars_getter)
            if tech_signal is None:
                print(f"  ⚠️  {symbol}: cannot analyze, skipping exit review")
                continue

            # Get market score
            market_score = self._get_market_score(symbol, "stock", market_data)

            # Get bars for trailing stop
            bars = bars_getter(symbol, "stock")

            signal = self.review_position(pos, tech_signal, market_score, bars, sentiment_data)
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
        category = "stocks"
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
        return market_data.get("stocks", {}).get(symbol, {}).get("market_score", 0.0)
