"""
Risk Manager Module
Validates trades against portfolio constraints and sizes positions.
"""

from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class RiskAssessment:
    """Result of risk assessment for a trade candidate."""
    symbol: str
    approved: bool
    reason: str
    suggested_qty: int
    risk_reward_ratio: float
    position_size_pct: float
    sizing_adjustments: list = field(default_factory=list)
    sector: str = "unknown"
    original_qty: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class RiskManager:
    """Enforces risk constraints and sizes positions."""

    def __init__(self, config: dict):
        risk_cfg = config.get("risk", {})
        self.max_position_pct = risk_cfg.get("max_position_pct", 10.0) / 100
        self.max_exposure_pct = risk_cfg.get("max_exposure_pct", 60.0) / 100
        self.max_positions = risk_cfg.get("max_positions", 8)
        self.daily_loss_limit_pct = risk_cfg.get("daily_loss_limit_pct", 2.0) / 100
        self.kill_switch_pct = risk_cfg.get("kill_switch_pct", 3.0) / 100
        self.max_drawdown_pct = risk_cfg.get("max_drawdown_pct", 10.0) / 100
        self.min_risk_reward = risk_cfg.get("min_risk_reward", 1.5)
        self.max_sector_pct = risk_cfg.get("max_sector_pct", 30) / 100
        self.max_same_sector_same_direction = risk_cfg.get("max_same_sector_same_direction", 3)

        self.equity = 0.0
        self.cash = 0.0
        self.positions = []
        self.daily_pnl = 0.0
        self.daily_pnl_pct = 0.0
        self.peak_equity = 0.0
        self.drawdown_from_peak_pct = 0.0
        self.kill_switch_active = False

    def update_portfolio(self, account: dict, positions: list[dict]):
        """Update current portfolio state from Alpaca."""
        self.equity = float(account.get("equity", account.get("portfolio_value", 0)))
        self.cash = float(account.get("cash", 0))
        self.positions = positions

        last_equity = float(account.get("last_equity", self.equity))
        self.daily_pnl = self.equity - last_equity
        self.daily_pnl_pct = (self.daily_pnl / last_equity) if last_equity > 0 else 0

        # Track peak equity for drawdown calculation
        self.peak_equity = max(last_equity, self.equity)
        if self.peak_equity > 0:
            self.drawdown_from_peak_pct = (self.peak_equity - self.equity) / self.peak_equity
        else:
            self.drawdown_from_peak_pct = 0.0

        # Check kill switch
        if self.daily_pnl_pct <= -self.kill_switch_pct:
            self.kill_switch_active = True

        # Check max drawdown
        if self.drawdown_from_peak_pct >= self.max_drawdown_pct:
            self.kill_switch_active = True

    def _get_sector_exposure(self) -> dict:
        """Calculate per-sector exposure from current positions."""
        sector_exposure = {}
        for p in self.positions:
            sector = p.get("sector", "unknown")
            value = abs(float(p.get("market_value", 0)))
            sector_exposure[sector] = sector_exposure.get(sector, 0) + value
        return sector_exposure

    def _count_sector_direction(self, sector: str, side: str) -> int:
        """Count positions in same sector and direction."""
        count = 0
        for p in self.positions:
            if p.get("sector", "unknown") == sector and p.get("side") == side:
                count += 1
        return count

    def assess_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        signal_score: float = 0,
        catalyst_flag: Optional[str] = None,
        regime_conflict: bool = False,
        atr_pct: float = 0,
        sector: str = "unknown",
    ) -> RiskAssessment:
        """Assess whether a trade meets risk constraints."""
        sizing_adjustments = []

        # Kill switch check
        if self.kill_switch_active:
            return RiskAssessment(
                symbol=symbol, approved=False, reason="Kill switch active",
                suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
                sector=sector,
            )

        # Daily loss limit
        if self.daily_pnl_pct <= -self.daily_loss_limit_pct:
            return RiskAssessment(
                symbol=symbol, approved=False, reason="Daily loss limit reached",
                suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
                sector=sector,
            )

        # Look up existing position in same symbol
        existing_position = next((p for p in self.positions if p["symbol"] == symbol), None)
        existing_value = abs(float(existing_position.get("market_value", 0))) if existing_position else 0.0
        existing_exposure_pct = (existing_value / self.equity) if self.equity > 0 else 0.0

        # Max positions (only reject if this is a NEW symbol)
        if len(self.positions) >= self.max_positions:
            if existing_position is None:
                return RiskAssessment(
                    symbol=symbol, approved=False,
                    reason=f"Max positions ({self.max_positions}) reached",
                    suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
                    sector=sector,
                )

        # Reject if already at max single-position exposure for this symbol
        if existing_exposure_pct >= self.max_position_pct:
            return RiskAssessment(
                symbol=symbol, approved=False,
                reason=f"Already at max position for {symbol} ({existing_exposure_pct*100:.1f}%)",
                suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
                sector=sector,
            )

        # Total exposure check
        total_exposure = sum(abs(float(p.get("market_value", 0))) for p in self.positions)
        current_exposure_pct = total_exposure / self.equity if self.equity > 0 else 0

        if current_exposure_pct >= self.max_exposure_pct:
            return RiskAssessment(
                symbol=symbol, approved=False,
                reason=f"Max exposure ({self.max_exposure_pct*100:.0f}%) reached",
                suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
                sector=sector,
            )

        # Sector concentration check
        if sector != "unknown" and self.equity > 0:
            sector_exposure = self._get_sector_exposure()
            sector_value = sector_exposure.get(sector, 0)
            sector_pct = sector_value / self.equity
            if sector_pct >= self.max_sector_pct:
                return RiskAssessment(
                    symbol=symbol, approved=False,
                    reason=f"Sector {sector} at {sector_pct*100:.1f}% (max {self.max_sector_pct*100:.0f}%)",
                    suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
                    sector=sector,
                )

            # Same sector + same direction limit
            pos_side = "long" if side == "buy" else "short"
            same_count = self._count_sector_direction(sector, pos_side)
            if same_count >= self.max_same_sector_same_direction:
                return RiskAssessment(
                    symbol=symbol, approved=False,
                    reason=f"Max {self.max_same_sector_same_direction} same-sector same-direction "
                           f"positions in {sector}",
                    suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
                    sector=sector,
                )

        # Binary event rejection
        if catalyst_flag == "binary_event":
            return RiskAssessment(
                symbol=symbol, approved=False,
                reason="Binary event detected - position rejected",
                suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
                sector=sector,
            )

        # Risk-reward ratio
        risk_reward = 0.0
        if stop_loss_price and take_profit_price and entry_price:
            risk = abs(entry_price - stop_loss_price)
            reward = abs(take_profit_price - entry_price)
            risk_reward = reward / risk if risk > 0 else 0

            if risk_reward < self.min_risk_reward:
                return RiskAssessment(
                    symbol=symbol, approved=False,
                    reason=f"R:R {risk_reward:.2f} < min {self.min_risk_reward}",
                    suggested_qty=0, risk_reward_ratio=risk_reward, position_size_pct=0,
                    sector=sector,
                )

        # Position sizing — account for existing holdings in the same symbol
        max_position_value = self.equity * self.max_position_pct
        remaining_room = max(0, max_position_value - existing_value)
        suggested_qty = int(remaining_room / entry_price) if entry_price > 0 else 0
        original_qty = suggested_qty

        # Catalyst-aware sizing: earnings imminent → qty × 50%
        if catalyst_flag == "earnings_imminent" and suggested_qty > 0:
            adjusted = max(1, int(suggested_qty * 0.5))
            sizing_adjustments.append(f"earnings_imminent: {suggested_qty} → {adjusted}")
            suggested_qty = adjusted

        # Regime conflict: qty × 70%
        if regime_conflict and suggested_qty > 0:
            adjusted = max(1, int(suggested_qty * 0.7))
            sizing_adjustments.append(f"regime_conflict: {suggested_qty} → {adjusted}")
            suggested_qty = adjusted

        # Volatility-adjusted sizing via ATR/price
        if atr_pct > 0.05 and suggested_qty > 0:
            adjusted = max(1, int(suggested_qty * 0.5))
            sizing_adjustments.append(f"high_volatility(ATR/P={atr_pct*100:.1f}%): {suggested_qty} → {adjusted}")
            suggested_qty = adjusted
        elif atr_pct > 0.03 and suggested_qty > 0:
            adjusted = max(1, int(suggested_qty * 0.7))
            sizing_adjustments.append(f"elevated_volatility(ATR/P={atr_pct*100:.1f}%): {suggested_qty} → {adjusted}")
            suggested_qty = adjusted

        position_size_pct = (suggested_qty * entry_price / self.equity * 100) if self.equity > 0 else 0

        if suggested_qty <= 0:
            return RiskAssessment(
                symbol=symbol, approved=False,
                reason=f"Insufficient room (existing {symbol} exposure: {existing_exposure_pct*100:.1f}%)",
                suggested_qty=0, risk_reward_ratio=risk_reward, position_size_pct=0,
                sector=sector, original_qty=original_qty, sizing_adjustments=sizing_adjustments,
            )

        side_label = "shares" if side == "buy" else "shares (short)"
        adj_note = f" [{', '.join(sizing_adjustments)}]" if sizing_adjustments else ""
        return RiskAssessment(
            symbol=symbol,
            approved=True,
            reason=f"Approved: {suggested_qty} {side_label}, R:R={risk_reward:.2f}{adj_note}",
            suggested_qty=suggested_qty,
            risk_reward_ratio=round(risk_reward, 2),
            position_size_pct=round(position_size_pct, 2),
            sector=sector,
            original_qty=original_qty,
            sizing_adjustments=sizing_adjustments,
        )

    def get_risk_summary(self) -> dict:
        """Get current risk status summary."""
        total_exposure = sum(abs(float(p.get("market_value", 0))) for p in self.positions)
        exposure_pct = (total_exposure / self.equity * 100) if self.equity > 0 else 0

        # Sector exposure
        sector_exposure = {}
        if self.equity > 0:
            raw = self._get_sector_exposure()
            sector_exposure = {s: round(v / self.equity * 100, 1) for s, v in raw.items()}

        return {
            "equity": self.equity,
            "cash": self.cash,
            "current_exposure_pct": round(exposure_pct, 2),
            "max_exposure_pct": self.max_exposure_pct * 100,
            "daily_pnl_pct": round(self.daily_pnl_pct * 100, 2),
            "drawdown_from_peak_pct": round(self.drawdown_from_peak_pct * 100, 2),
            "max_drawdown_pct": self.max_drawdown_pct * 100,
            "position_count": len(self.positions),
            "max_positions": self.max_positions,
            "kill_switch_active": self.kill_switch_active,
            "daily_limit_hit": self.daily_pnl_pct <= -self.daily_loss_limit_pct,
            "sector_exposure": sector_exposure,
            "daily_loss_limit_hit": self.daily_pnl_pct <= -self.daily_loss_limit_pct,
        }
