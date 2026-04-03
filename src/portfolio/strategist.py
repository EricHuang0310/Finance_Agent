"""
Portfolio Strategist Module
Analyzes cross-position correlations, applies graduated sizing adjustments,
and suggests partial closes for concentrated portfolios.
"""

from datetime import datetime, timezone

import pandas as pd


class PortfolioStrategist:
    """Computes cross-position correlations and optimizes portfolio sizing.

    Reads configuration from the ``portfolio`` section of settings.yaml.
    All thresholds are configurable; see config/settings.yaml for defaults.
    """

    def __init__(self, config: dict):
        port_cfg = config.get("portfolio", {})
        self.lookback_days: int = port_cfg.get("correlation_lookback_days", 20)
        self.corr_warn_threshold: float = port_cfg.get("correlation_warn_threshold", 0.7)
        self.corr_reject_threshold: float = port_cfg.get("correlation_reject_threshold", 0.9)
        self.corr_reduce_pct: float = port_cfg.get("correlation_reduce_pct", 0.30)
        self.min_data_points: int = port_cfg.get("min_correlation_data_points", 15)
        self.concentration_corr_threshold: float = port_cfg.get("concentration_corr_threshold", 0.8)
        self.concentration_partial_pct: float = port_cfg.get("concentration_partial_pct", 0.25)

    # ── Correlation Computation ─────────────────────────────────

    def compute_correlation_matrix(
        self,
        symbols: list[str],
        bar_getter,
    ) -> tuple[pd.DataFrame, dict]:
        """Compute pairwise Pearson correlation from daily close returns.

        Args:
            symbols: List of ticker symbols to include in the matrix.
            bar_getter: Callable with signature
                ``(symbol, asset_type, timeframe, lookback_days) -> pd.DataFrame | None``.

        Returns:
            ``(correlation_matrix, metadata)`` where *metadata* includes
            ``symbols_included``, ``symbols_skipped``, ``data_points``,
            ``method``, and ``lookback_days``.
        """
        close_prices: dict[str, pd.Series] = {}
        skipped: list[str] = []

        for symbol in symbols:
            bars = bar_getter(symbol, "stock", "1Day", self.lookback_days)
            if bars is None or len(bars) < self.min_data_points:
                skipped.append(symbol)
                continue
            # bars is a pandas DataFrame with a 'close' column
            close_prices[symbol] = bars["close"].values[-self.lookback_days:]

        if len(close_prices) < 2:
            return pd.DataFrame(), {
                "symbols_included": list(close_prices.keys()),
                "symbols_skipped": skipped,
                "data_points": 0,
                "method": "pearson",
                "lookback_days": self.lookback_days,
                "reason": "insufficient_symbols",
            }

        # Build DataFrame of daily returns (not raw prices) for correlation
        price_df = pd.DataFrame(close_prices)
        returns_df = price_df.pct_change().dropna()

        corr_matrix = returns_df.corr(method="pearson")

        metadata = {
            "symbols_included": list(close_prices.keys()),
            "symbols_skipped": skipped,
            "data_points": len(returns_df),
            "method": "pearson",
            "lookback_days": self.lookback_days,
        }

        return corr_matrix, metadata

    # ── Sizing Adjustments ──────────────────────────────────────

    def adjust_sizing(
        self,
        assessed: list[dict],
        existing_symbols: list[str],
        corr_matrix: pd.DataFrame,
    ) -> list[dict]:
        """Reduce or reject approved trades based on correlation with existing holdings.

        Implements a graduated response:
        - ``>= corr_reject_threshold`` (default 0.9): reject the trade
        - ``>= corr_warn_threshold`` (default 0.7): reduce quantity by ``corr_reduce_pct``

        Only *same-direction* positions are penalised. Opposite-direction
        positions (natural hedges) are skipped.

        Returns a **new** list of dicts -- originals are never mutated.
        """
        result: list[dict] = []

        for trade in assessed:
            if not trade.get("approved"):
                result.append(trade)  # pass through rejected trades unchanged
                continue

            symbol = trade["symbol"]
            if symbol not in corr_matrix.columns:
                result.append(trade)  # no correlation data, pass through
                continue

            max_corr = 0.0
            correlated_with: list[tuple[str, float]] = []

            trade_side = trade.get("side", "buy")

            for existing in existing_symbols:
                if existing not in corr_matrix.columns or existing == symbol:
                    continue
                corr_val = abs(corr_matrix.loc[symbol, existing])
                if corr_val > max_corr:
                    max_corr = corr_val
                if corr_val >= self.corr_warn_threshold:
                    correlated_with.append((existing, round(corr_val, 3)))

            # Shallow copy -- never mutate the original dict
            adjusted_trade = {**trade}

            if max_corr >= self.corr_reject_threshold:
                adjusted_trade["approved"] = False
                adjusted_trade["portfolio_rejection"] = (
                    f"Correlation {max_corr:.2f} >= {self.corr_reject_threshold} "
                    f"with {correlated_with}"
                )
                adjusted_trade["portfolio_correlation"] = {
                    "max_correlation": round(max_corr, 3),
                    "correlated_with": correlated_with,
                    "action": "reject",
                }
            elif max_corr >= self.corr_warn_threshold:
                old_qty = adjusted_trade["suggested_qty"]
                new_qty = max(1, int(old_qty * (1 - self.corr_reduce_pct)))
                adjusted_trade["suggested_qty"] = new_qty

                # Append to existing sizing_adjustments list if present
                sizing_adj = list(
                    adjusted_trade.get("risk_assessment", {}).get("sizing_adjustments", [])
                )
                sizing_adj.append(
                    f"portfolio_correlation({max_corr:.2f}): {old_qty} -> {new_qty}"
                )
                # Write the augmented list back onto a copy of risk_assessment
                if "risk_assessment" in adjusted_trade:
                    adjusted_trade["risk_assessment"] = {
                        **adjusted_trade["risk_assessment"],
                        "sizing_adjustments": sizing_adj,
                    }

                adjusted_trade["portfolio_correlation"] = {
                    "max_correlation": round(max_corr, 3),
                    "correlated_with": correlated_with,
                    "action": "reduce",
                }

            result.append(adjusted_trade)

        return result

    # ── Partial Close Suggestions ───────────────────────────────

    def suggest_partial_closes(
        self,
        existing_positions: list[dict],
        corr_matrix: pd.DataFrame,
    ) -> list[dict]:
        """Identify existing positions that contribute to portfolio concentration.

        For pairs of same-direction positions whose correlation exceeds
        ``concentration_corr_threshold``, suggest a partial close on the
        smaller position.

        Returns a list of exit-candidate-compatible dicts (may be empty).
        """
        if corr_matrix.empty or len(existing_positions) < 2:
            return []

        suggestions: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()

        for i, pos_a in enumerate(existing_positions):
            sym_a = pos_a.get("symbol", "")
            if sym_a not in corr_matrix.columns:
                continue

            for j, pos_b in enumerate(existing_positions):
                if j <= i:
                    continue
                sym_b = pos_b.get("symbol", "")
                if sym_b not in corr_matrix.columns:
                    continue

                pair_key = tuple(sorted((sym_a, sym_b)))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                corr_val = abs(corr_matrix.loc[sym_a, sym_b])
                if corr_val < self.concentration_corr_threshold:
                    continue

                # Same-direction check (both long or both short)
                side_a = pos_a.get("side", "long")
                side_b = pos_b.get("side", "long")
                if side_a != side_b:
                    continue  # opposite directions = hedge, not concentration

                # Suggest partial close on the smaller position (by market_value)
                mv_a = abs(float(pos_a.get("market_value", 0)))
                mv_b = abs(float(pos_b.get("market_value", 0)))
                target = pos_a if mv_a <= mv_b else pos_b
                partner = pos_b if mv_a <= mv_b else pos_a

                suggestions.append({
                    "symbol": target.get("symbol", ""),
                    "side": target.get("side", "long"),
                    "qty": abs(int(float(target.get("qty", 0)))),
                    "current_price": float(target.get("current_price", 0)),
                    "avg_entry_price": float(target.get("avg_entry_price", 0)),
                    "unrealized_pl": float(target.get("unrealized_pl", 0)),
                    "unrealized_plpc": float(target.get("unrealized_plpc", 0)),
                    "exit_action": "partial_close",
                    "exit_reason": (
                        f"Portfolio concentration: correlation with "
                        f"{partner.get('symbol', '')}={corr_val:.2f}"
                    ),
                    "exit_score": 0.6,
                    "partial_close_pct": self.concentration_partial_pct,
                    "source": "portfolio_strategist",
                })

        return suggestions

    # ── Result Builder ──────────────────────────────────────────

    def build_result(
        self,
        corr_matrix: pd.DataFrame,
        metadata: dict,
        adjustments: list[dict],
        partial_close_suggestions: list[dict],
        cio_stance: str = "neutral",
    ) -> dict:
        """Build the ``portfolio_construction.json`` content dict.

        Args:
            corr_matrix: Pearson correlation matrix DataFrame.
            metadata: Correlation computation metadata.
            adjustments: List of adjusted trade dicts (output of ``adjust_sizing``).
            partial_close_suggestions: Output of ``suggest_partial_closes``.
            cio_stance: Current CIO trading stance.

        Returns:
            Dict ready for ``save_state_atomic``.
        """
        # Summarise adjustments
        rejected = [
            t for t in adjustments
            if not t.get("approved") and t.get("portfolio_rejection")
        ]
        reduced = [
            t for t in adjustments
            if t.get("portfolio_correlation", {}).get("action") == "reduce"
        ]

        corr_dict = corr_matrix.to_dict() if not corr_matrix.empty else {}

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cio_stance": cio_stance,
            "correlation_matrix": corr_dict,
            "metadata": metadata,
            "adjustments_summary": {
                "total_trades": len(adjustments),
                "rejected_by_correlation": len(rejected),
                "reduced_by_correlation": len(reduced),
                "rejected_details": [
                    {"symbol": t["symbol"], "reason": t.get("portfolio_rejection", "")}
                    for t in rejected
                ],
                "reduced_details": [
                    {
                        "symbol": t["symbol"],
                        "max_correlation": t.get("portfolio_correlation", {}).get("max_correlation"),
                        "correlated_with": t.get("portfolio_correlation", {}).get("correlated_with"),
                    }
                    for t in reduced
                ],
            },
            "partial_close_suggestions": partial_close_suggestions,
        }
