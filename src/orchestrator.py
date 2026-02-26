"""
Multi-Agent Trading Orchestrator
Coordinates all agents, aggregates signals, and manages the trading pipeline.

Usage:
    python -m src.orchestrator          # Run analysis pipeline
    python -m src.orchestrator --trade   # Run analysis + execute trades (paper)
"""

import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from src.alpaca_client import AlpacaClient
from src.analysis.technical import TechnicalAnalyzer
from src.analysis.sentiment import SentimentAnalyzer
from src.analysis.screener import SymbolScreener
from src.analysis.position_reviewer import PositionReviewer
from src.analysis.fundamentals import FundamentalsAnalyzer
from src.risk.manager import RiskManager
from src.notifications.telegram import TelegramNotifier
from src.memory.situation_memory import SituationMemory


class TradingOrchestrator:
    """
    Lead Agent: coordinates all specialist agents and makes final decisions.

    Pipeline:
    1. Market Analyst  → Fetch data for watchlist
    2. Technical Analyst → Calculate indicators & signals
    3. Sentiment Agent  → (Placeholder) News sentiment scoring
    4. Risk Manager     → Validate trades, size positions
    5. Decision Engine  → Aggregate scores, generate trade plan
    6. Executor         → Place orders (with human confirmation)
    """

    def __init__(self, config_path: str = "config/settings.yaml"):
        # Load config
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        # Initialize components
        self.client = AlpacaClient()
        self.tech_analyzer = TechnicalAnalyzer()
        self.sentiment_analyzer = SentimentAnalyzer(self.client)
        self.screener = SymbolScreener(self.client, self.config)
        self.risk_manager = RiskManager(self.config)
        self.position_reviewer = PositionReviewer(self.config)
        self.notifier = TelegramNotifier()

        # Shared state paths
        self.state_dir = Path("shared_state")
        self.state_dir.mkdir(exist_ok=True)
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)

        # Fundamentals analyzer (optional — requires yfinance)
        self.fundamentals_analyzer = FundamentalsAnalyzer()

        # Memory banks (BM25-based, one per decision role)
        mem_dir = self.config.get("memory", {}).get("storage_dir", "memory_store")
        self.bull_memory = SituationMemory("bull_memory", mem_dir)
        self.bear_memory = SituationMemory("bear_memory", mem_dir)
        self.research_judge_memory = SituationMemory("research_judge_memory", mem_dir)
        self.risk_judge_memory = SituationMemory("risk_judge_memory", mem_dir)
        self.decision_engine_memory = SituationMemory("decision_engine_memory", mem_dir)

        # Bar data cache to avoid duplicate API calls
        self._bar_cache = {}

        # Config shortcuts
        self.watchlist_mode = self.config.get("watchlist_mode", "static")
        self.watchlist_stocks = self.config.get("watchlist", {}).get("stocks", [])
        self.watchlist_crypto = self.config.get("watchlist", {}).get("crypto", [])
        self.weights = self.config.get("scoring", {})
        self.decision_cfg = self.config.get("decision", {})

    # ══════════════════════════════════════════════
    # Agent 0: Symbol Screener (Phase 0)
    # ══════════════════════════════════════════════

    def run_symbol_screener(self) -> dict:
        """Dynamically screen the market for the best symbols to trade."""
        print("\n" + "=" * 60)
        print("🔎 AGENT 0: Symbol Screener - Discovering Symbols")
        print("=" * 60)

        result = self.screener.screen_all()

        # Update the watchlists used by all downstream agents
        self.watchlist_stocks = result["stocks"]
        self.watchlist_crypto = result["crypto"]

        print(f"\n  📋 Dynamic watchlist:")
        print(f"     Stocks ({len(result['stocks'])}): {', '.join(result['stocks'][:10])}"
              + (f" ... +{len(result['stocks'])-10} more" if len(result['stocks']) > 10 else ""))
        print(f"     Crypto ({len(result['crypto'])}): {', '.join(result['crypto'])}")

        # Print top 5 by activity score
        details = result.get("details", {})
        top_5 = sorted(details.items(), key=lambda x: x[1]["activity_score"], reverse=True)[:5]
        print(f"\n  🏆 Top 5 by activity score:")
        for sym, d in top_5:
            print(f"     {sym:8s} | score={d['activity_score']:.3f} | "
                  f"momentum={d['momentum_pct']:+.1f}% | vol_ratio={d['volume_ratio']:.1f}x")

        self._save_state("dynamic_watchlist.json", result)
        return result

    # ══════════════════════════════════════════════
    # Agent 1: Market Analyst
    # ══════════════════════════════════════════════

    def run_market_analyst(self) -> dict:
        """Fetch market data for all watchlist symbols."""
        print("\n" + "=" * 60)
        print("🔍 AGENT 1: Market Analyst - Fetching Data")
        print("=" * 60)

        market_data = {"stocks": {}, "crypto": {}, "timestamp": datetime.now().isoformat()}

        for symbol in self.watchlist_stocks:
            try:
                bars = self._get_bars(symbol, "stock")
                if bars is not None and len(bars) > 0:
                    latest_close = float(bars["close"].iloc[-1])
                    latest_volume = int(bars["volume"].iloc[-1])
                    avg_volume_20d = int(bars["volume"].tail(20).mean())
                    high_90d = float(bars["high"].max())
                    low_90d = float(bars["low"].min())

                    # Compute market context score
                    vol_ratio = latest_volume / max(avg_volume_20d, 1)
                    range_90d = high_90d - low_90d
                    range_position = (latest_close - low_90d) / range_90d if range_90d > 0 else 0.5
                    vol_score = min(1.0, (vol_ratio - 1.0) * 0.5) if vol_ratio > 1.0 else max(-0.5, (vol_ratio - 1.0))
                    range_score = (range_position - 0.5)  # Near top -> positive (breakout), near bottom -> negative (downtrend)
                    market_score = 0.5 * vol_score + 0.5 * range_score
                    market_score = max(-1.0, min(1.0, market_score))

                    market_data["stocks"][symbol] = {
                        "bars_count": len(bars),
                        "latest_close": latest_close,
                        "latest_volume": latest_volume,
                        "high_90d": high_90d,
                        "low_90d": low_90d,
                        "avg_volume_20d": avg_volume_20d,
                        "market_score": round(market_score, 4),
                    }
                    print(f"  ✅ {symbol}: ${latest_close:.2f} | mkt_score={market_score:.3f}")
                else:
                    print(f"  ⚠️  {symbol}: No data")
            except Exception as e:
                print(f"  ❌ {symbol}: Error - {e}")

        for symbol in self.watchlist_crypto:
            try:
                bars = self._get_bars(symbol, "crypto")
                if bars is not None and len(bars) > 0:
                    latest_close = float(bars["close"].iloc[-1])
                    latest_volume = float(bars["volume"].iloc[-1])
                    avg_volume_20d = float(bars["volume"].tail(20).mean())
                    high_90d = float(bars["high"].max())
                    low_90d = float(bars["low"].min())

                    vol_ratio = latest_volume / max(avg_volume_20d, 1)
                    range_90d = high_90d - low_90d
                    range_position = (latest_close - low_90d) / range_90d if range_90d > 0 else 0.5
                    vol_score = min(1.0, (vol_ratio - 1.0) * 0.5) if vol_ratio > 1.0 else max(-0.5, (vol_ratio - 1.0))
                    range_score = (range_position - 0.5)  # Near top -> positive (breakout), near bottom -> negative (downtrend)
                    market_score = 0.5 * vol_score + 0.5 * range_score
                    market_score = max(-1.0, min(1.0, market_score))

                    market_data["crypto"][symbol] = {
                        "bars_count": len(bars),
                        "latest_close": latest_close,
                        "latest_volume": latest_volume,
                        "high_90d": high_90d,
                        "low_90d": low_90d,
                        "avg_volume_20d": avg_volume_20d,
                        "market_score": round(market_score, 4),
                    }
                    print(f"  ✅ {symbol}: ${latest_close:,.2f} | mkt_score={market_score:.3f}")
                else:
                    print(f"  ⚠️  {symbol}: No data")
            except Exception as e:
                print(f"  ❌ {symbol}: Error - {e}")

        # Detect market regime and include in market data
        market_data["market_regime"] = self._detect_market_regime()
        print(f"\n  📈 Market Regime: {market_data['market_regime']}")

        # Save to shared state
        self._save_state("market_overview.json", market_data)
        return market_data

    def _detect_market_regime(self) -> str:
        """Determine market regime (risk_on / risk_off / neutral) using SPY EMA alignment."""
        try:
            spy_bars = self._get_bars("SPY", "stock", lookback_days=250)
            if spy_bars is None or len(spy_bars) < 200:
                return "neutral"

            close = spy_bars["close"].astype(float)
            ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
            ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
            ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])

            if ema20 > ema50 > ema200:
                return "risk_on"
            elif ema20 < ema50 < ema200:
                return "risk_off"
            return "neutral"
        except Exception:
            return "neutral"

    def _get_regime_weights(self, regime: str) -> dict:
        """Return scoring weights adjusted for the current market regime.

        Implements the regime adjustment specified in decision_engine.md.
        """
        base_tech = self.weights.get("technical_analyst", 0.35)
        base_mkt = self.weights.get("market_analyst", 0.20)
        base_sent = self.weights.get("sentiment_analyst", 0.15)

        if regime == "risk_on":
            return {"tech": base_tech * 1.2, "market": base_mkt * 0.8, "sentiment": base_sent * 1.1}
        elif regime == "risk_off":
            return {"tech": base_tech, "market": base_mkt * 1.3, "sentiment": base_sent}
        return {"tech": base_tech, "market": base_mkt, "sentiment": base_sent}

    # ══════════════════════════════════════════════
    # Fundamentals Analyst (Phase 2.5 — Top-N only)
    # ══════════════════════════════════════════════

    def run_fundamentals_analyst(self, symbols: list[str]) -> dict:
        """Fetch fundamental data for debate candidates (Top-N symbols only)."""
        print("\n" + "=" * 60)
        print("📋 Fundamentals Analyst - Fetching Data for Top-N Debate Candidates")
        print("=" * 60)

        results = self.fundamentals_analyzer.analyze_batch(symbols)
        output = {
            "timestamp": datetime.now().isoformat(),
            "signals": {
                sym: sig.to_dict() if sig else None
                for sym, sig in results.items()
            },
        }
        self._save_state("fundamentals_signals.json", output)
        return output

    # ══════════════════════════════════════════════
    # Agent 2: Technical Analyst
    # ══════════════════════════════════════════════

    def run_technical_analyst(self) -> dict:
        """Run technical analysis on all symbols."""
        print("\n" + "=" * 60)
        print("📊 AGENT 2: Technical Analyst - Computing Signals")
        print("=" * 60)

        signals = {"stocks": {}, "crypto": {}, "timestamp": datetime.now().isoformat()}

        # Stocks
        for symbol in self.watchlist_stocks:
            try:
                bars = self._get_bars(symbol, "stock")
                if bars is not None and len(bars) >= 50:
                    signal = self.tech_analyzer.analyze(bars, symbol, "1Day")
                    signals["stocks"][symbol] = signal.to_dict()
                    emoji = "🟢" if signal.score > 0.3 else "🔴" if signal.score < -0.3 else "🟡"
                    print(f"  {emoji} {symbol}: score={signal.score:.3f} | "
                          f"trend={signal.trend} | RSI={signal.rsi:.1f}")
                else:
                    print(f"  ⚠️  {symbol}: Insufficient data for analysis")
            except Exception as e:
                print(f"  ❌ {symbol}: Error - {e}")

        # Crypto
        for symbol in self.watchlist_crypto:
            try:
                bars = self._get_bars(symbol, "crypto")
                if bars is not None and len(bars) >= 50:
                    signal = self.tech_analyzer.analyze(bars, symbol, "1Day")
                    signals["crypto"][symbol] = signal.to_dict()
                    emoji = "🟢" if signal.score > 0.3 else "🔴" if signal.score < -0.3 else "🟡"
                    print(f"  {emoji} {symbol}: score={signal.score:.3f} | "
                          f"trend={signal.trend} | RSI={signal.rsi:.1f}")
            except Exception as e:
                print(f"  ❌ {symbol}: Error - {e}")

        self._save_state("technical_signals.json", signals)
        return signals

    # ══════════════════════════════════════════════
    # Agent 3: Sentiment Analyst
    # ══════════════════════════════════════════════

    def run_sentiment_analyst(self) -> dict:
        """Run sentiment analysis using Alpaca News + VADER NLP."""
        print("\n" + "=" * 60)
        print("💭 AGENT 3: Sentiment Analyst - Analyzing News")
        print("=" * 60)

        sentiment = self.sentiment_analyzer.analyze_all(
            stocks=self.watchlist_stocks,
            crypto=self.watchlist_crypto,
            days=3,
        )

        print(f"\n  📊 Market Sentiment: {sentiment['market_sentiment']} | "
              f"Fear & Greed: {sentiment['fear_greed_index']}/100")

        self._save_state("sentiment_signals.json", sentiment)
        return sentiment

    # ══════════════════════════════════════════════
    # Agent 3.5: Position Exit Review
    # ══════════════════════════════════════════════

    def run_position_exit_review(self, tech_signals: dict, market_data: dict) -> list[dict]:
        """Review existing positions for exit signals."""
        print("\n" + "=" * 60)
        print("🔄 AGENT 3.5: Position Exit Review")
        print("=" * 60)

        positions = self.client.get_positions()
        if not positions:
            print("  📭 No open positions to review.")
            return []

        print(f"  Reviewing {len(positions)} position(s)...")

        def bars_getter(symbol, asset_type):
            return self._get_bars(symbol, asset_type)

        results = self.position_reviewer.review_all(
            positions=positions,
            tech_signals=tech_signals,
            market_data=market_data,
            bars_getter=bars_getter,
        )

        exits = [r for r in results if r.exit_action == "close"]
        holds = [r for r in results if r.exit_action == "hold"]

        for r in results:
            if r.exit_action == "close":
                roi_pct = r.unrealized_plpc * 100
                print(f"  📤 {r.symbol} ({r.side}): EXIT score={r.exit_score:.3f} | "
                      f"P&L={roi_pct:+.2f}% | {r.exit_reason}")
            else:
                print(f"  ✅ {r.symbol} ({r.side}): HOLD score={r.exit_score:.3f}")

        self._save_state("exit_review.json", {
            "timestamp": datetime.now().isoformat(),
            "positions_reviewed": len(positions),
            "exits_flagged": len(exits),
            "exits": [e.to_dict() for e in exits],
            "holds": [h.to_dict() for h in holds],
        })

        # Convert ExitSignals to dicts for executor
        exit_candidates = []
        for e in exits:
            exit_candidates.append({
                "symbol": e.symbol,
                "side": e.side,
                "qty": e.qty,
                "avg_entry_price": e.avg_entry_price,
                "current_price": e.current_price,
                "unrealized_pl": e.unrealized_pl,
                "unrealized_plpc": e.unrealized_plpc,
                "exit_score": e.exit_score,
                "exit_reason": e.exit_reason,
            })

        return exit_candidates

    def execute_exits(self, exit_candidates: list[dict]):
        """Execute position closures and notify via Telegram."""
        print("\n" + "=" * 60)
        print("📤 Executing Position Exits")
        print("=" * 60)

        for candidate in exit_candidates:
            symbol = candidate["symbol"]
            close_side = "sell" if candidate["side"] == "long" else "buy"

            try:
                print(f"  📤 Closing {symbol} ({candidate['side']}): "
                      f"qty={candidate['qty']} @ ~${candidate['current_price']:.2f}")

                result = self.client.place_market_order(
                    symbol=symbol,
                    qty=candidate["qty"],
                    side=close_side,
                )

                print(f"  ✅ Closed: {result['id']} | Status: {result['status']}")

                # Telegram notification with ROI
                self.notifier.alert_position_closed(
                    symbol=symbol,
                    side=candidate["side"],
                    qty=candidate["qty"],
                    avg_entry_price=candidate["avg_entry_price"],
                    exit_price=candidate["current_price"],
                    unrealized_pl=candidate["unrealized_pl"],
                    unrealized_plpc=candidate["unrealized_plpc"],
                    exit_reason=candidate["exit_reason"],
                    order_id=result["id"],
                )

                # Log trade
                self._log_trade({
                    "symbol": symbol,
                    "side": close_side,
                    "suggested_qty": candidate["qty"],
                    "entry_price": candidate["current_price"],
                    "composite_score": candidate.get("exit_score", 0),
                    "action": "close_position",
                    "exit_reason": candidate["exit_reason"],
                }, result)

            except Exception as e:
                print(f"  ❌ Failed to close {symbol}: {e}")
                self.notifier.alert_order_rejected(symbol, f"Exit failed: {e}")

    # ══════════════════════════════════════════════
    # Agent 4: Risk Manager
    # ══════════════════════════════════════════════

    def run_risk_manager(self, trade_candidates: list[dict]) -> list[dict]:
        """Run risk assessment on trade candidates."""
        print("\n" + "=" * 60)
        print("🛡️  AGENT 4: Risk Manager - Validating Trades")
        print("=" * 60)

        # Update portfolio state
        account = self.client.get_account()
        positions = self.client.get_positions()
        self.risk_manager.update_portfolio(account, positions)

        # Print portfolio status
        summary = self.risk_manager.get_risk_summary()
        print(f"  💰 Equity: ${summary['equity']:,.2f} | "
              f"Cash: ${summary['cash']:,.2f}")
        print(f"  📊 Exposure: {summary['current_exposure_pct']:.1f}% / "
              f"{summary['max_exposure_pct']:.0f}%")
        print(f"  📈 Daily P&L: {summary['daily_pnl_pct']:+.2f}% | "
              f"Positions: {summary['position_count']}/{summary['max_positions']}")

        if summary["kill_switch_active"]:
            print("  🚨 KILL SWITCH IS ACTIVE - NO TRADES ALLOWED")
            return []

        # Assess each candidate
        assessed = []
        for candidate in trade_candidates:
            assessment = self.risk_manager.assess_trade(
                symbol=candidate["symbol"],
                side=candidate.get("side", "buy"),
                entry_price=candidate["entry_price"],
                stop_loss_price=candidate.get("stop_loss"),
                take_profit_price=candidate.get("take_profit"),
                signal_score=candidate.get("score", 0),
            )

            candidate["risk_assessment"] = assessment.to_dict()
            candidate["approved"] = assessment.approved
            candidate["suggested_qty"] = assessment.suggested_qty

            emoji = "✅" if assessment.approved else "❌"
            print(f"  {emoji} {candidate['symbol']}: {assessment.reason}")
            assessed.append(candidate)

        self._save_state("risk_assessment.json", {
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "assessments": [c["risk_assessment"] for c in assessed],
        })

        return assessed

    # ══════════════════════════════════════════════
    # Decision Engine
    # ══════════════════════════════════════════════

    def generate_trade_plan(self, tech_signals: dict, sentiment: dict, market_data: dict = None) -> list[dict]:
        """
        Aggregate signals from all agents and generate trade candidates.

        Uses market regime-adjusted weights and confidence-weighted scoring.
        Scoring weights (from config, adjusted by regime):
        - Technical: 35% base
        - Market (trend context): 20% base
        - Sentiment: 15% base
        - Risk: 30% (veto power, not in scoring)
        """
        print("\n" + "=" * 60)
        print("🧠 Decision Engine - Aggregating Signals")
        print("=" * 60)

        min_buy = self.decision_cfg.get("min_score_to_buy", 0.65)
        min_sell = self.decision_cfg.get("min_score_to_sell", min_buy)
        candidates = []

        # Get regime-adjusted weights
        regime = "neutral"
        if market_data:
            regime = market_data.get("market_regime", "neutral")
        rw = self._get_regime_weights(regime)
        print(f"  📈 Regime: {regime} → weights: tech={rw['tech']:.3f} mkt={rw['market']:.3f} sent={rw['sentiment']:.3f}")

        def _score_symbol(symbol, signal, sent_data, mkt_score, asset_type):
            tech_score = signal.get("score", 0)
            tech_conf = signal.get("confidence", 1.0)
            sent_score = sent_data.get("score", 0) if sent_data else 0
            sent_conf = sent_data.get("confidence", 1.0) if sent_data else 0.2
            mkt_conf = 1.0  # Market score is always based on full bar data

            # Confidence-weighted composite (regime-adjusted weights)
            weighted_tech = tech_score * rw["tech"] * tech_conf
            weighted_mkt = mkt_score * rw["market"] * mkt_conf
            weighted_sent = sent_score * rw["sentiment"] * sent_conf
            total_weight = rw["tech"] * tech_conf + rw["market"] * mkt_conf + rw["sentiment"] * sent_conf

            composite = (weighted_tech + weighted_mkt + weighted_sent) / total_weight if total_weight > 0 else 0
            composite = max(-1.0, min(1.0, composite))

            order_symbol = symbol.replace("/", "") if asset_type == "crypto" else symbol

            if composite >= min_buy or composite <= -min_sell:
                side = "buy" if composite >= min_buy else "sell"
                emoji = "🟢" if side == "buy" else "🔴"
                print(f"  {emoji} {symbol}: composite={composite:.3f} (conf: tech={tech_conf:.2f} sent={sent_conf:.2f}) → {side.upper()} CANDIDATE")
                return {
                    "symbol": order_symbol,
                    "asset_type": asset_type,
                    "side": side,
                    "composite_score": round(composite, 4),
                    "tech_score": tech_score,
                    "tech_confidence": tech_conf,
                    "sentiment_score": sent_score,
                    "sentiment_confidence": sent_conf,
                    "market_score": mkt_score,
                    "entry_price": signal.get("entry_price"),
                    "stop_loss": signal.get("stop_loss"),
                    "take_profit": signal.get("take_profit"),
                    "trend": signal.get("trend"),
                    "rsi": signal.get("rsi"),
                }
            else:
                print(f"  ⏭️  {symbol}: composite={composite:.3f} → Skip")
                return None

        # Process stocks
        for symbol, signal in tech_signals.get("stocks", {}).items():
            sent_data = sentiment.get("symbols", {}).get(symbol, {})
            mkt_score = 0.0
            if market_data:
                mkt_score = market_data.get("stocks", {}).get(symbol, {}).get("market_score", 0.0)
            result = _score_symbol(symbol, signal, sent_data, mkt_score, "stock")
            if result:
                candidates.append(result)

        # Process crypto
        for symbol, signal in tech_signals.get("crypto", {}).items():
            sent_data = sentiment.get("symbols", {}).get(symbol, {})
            mkt_score = 0.0
            if market_data:
                mkt_score = market_data.get("crypto", {}).get(symbol, {}).get("market_score", 0.0)
            result = _score_symbol(symbol, signal, sent_data, mkt_score, "crypto")
            if result:
                candidates.append(result)

        # Sort by absolute score (strongest signals first)
        candidates.sort(key=lambda x: abs(x["composite_score"]), reverse=True)

        self._save_state("decisions.json", {
            "timestamp": datetime.now().isoformat(),
            "market_regime": regime,
            "candidates": candidates,
            "min_score_threshold": min_buy,
        })

        return candidates

    # ══════════════════════════════════════════════
    # Agent 5: Executor
    # ══════════════════════════════════════════════

    def execute_trades(self, approved_trades: list[dict], require_confirmation: bool = True):
        """Execute approved trades with optional human confirmation."""
        print("\n" + "=" * 60)
        print("⚡ AGENT 5: Executor - Placing Orders")
        print("=" * 60)

        # Market hours check
        try:
            clock = self.client.is_market_open()
            if not clock["is_open"]:
                print(f"  ⚠️  Market is currently CLOSED. Next open: {clock['next_open']}")
                print(f"  ⚠️  Stock orders will be queued until market opens. Crypto unaffected.")
        except Exception as e:
            print(f"  ⚠️  Could not check market hours: {e}")

        tradeable = [t for t in approved_trades if t.get("approved")]

        if not tradeable:
            print("  📭 No approved trades to execute.")
            return

        for trade in tradeable:
            print(f"\n  📋 Trade Plan:")
            print(f"     Symbol: {trade['symbol']}")
            print(f"     Side: {trade['side'].upper()}")
            print(f"     Qty: {trade['suggested_qty']}")
            print(f"     Entry: ${trade['entry_price']:.2f}")
            print(f"     Stop Loss: ${trade['stop_loss']:.2f}" if trade.get("stop_loss") else "")
            print(f"     Take Profit: ${trade['take_profit']:.2f}" if trade.get("take_profit") else "")
            print(f"     Score: {trade['composite_score']:.3f}")

            if require_confirmation:
                confirm = input(f"\n  ❓ Execute this trade? (y/n): ").strip().lower()
                if confirm != "y":
                    print(f"  ⏭️  Skipped {trade['symbol']}")
                    continue

            try:
                if trade.get("stop_loss") and trade.get("take_profit"):
                    result = self.client.place_bracket_order(
                        symbol=trade["symbol"],
                        qty=trade["suggested_qty"],
                        side=trade["side"],
                        stop_loss_price=trade["stop_loss"],
                        take_profit_price=trade["take_profit"],
                    )
                else:
                    result = self.client.place_market_order(
                        symbol=trade["symbol"],
                        qty=trade["suggested_qty"],
                        side=trade["side"],
                    )

                print(f"  ✅ Order placed: {result['id']} | Status: {result['status']}")

                # Log trade
                self._log_trade(trade, result)

            except Exception as e:
                print(f"  ❌ Order failed: {e}")

    # ══════════════════════════════════════════════
    # Full Pipeline
    # ══════════════════════════════════════════════

    def run_pipeline(self, execute: bool = False):
        """Run the complete multi-agent analysis and trading pipeline."""
        print("\n" + "🚀" * 20)
        print("  MULTI-AGENT TRADING SYSTEM")
        print(f"  Mode: {'PAPER' if self.client.is_paper else '⚠️ LIVE'}")
        print(f"  Watchlist: {self.watchlist_mode.upper()}")
        print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("🚀" * 20)

        # Step 0: Dynamic symbol screening (if enabled)
        if self.watchlist_mode == "dynamic":
            self.run_symbol_screener()

        # Step 1: Market data
        market_data = self.run_market_analyst()

        # Step 2: Technical analysis
        tech_signals = self.run_technical_analyst()

        # Step 3: Sentiment analysis
        sentiment = self.run_sentiment_analyst()

        # Step 3.5: Position exit review
        exit_candidates = self.run_position_exit_review(tech_signals, market_data)

        # Execute exits BEFORE new entries (frees capital & position slots)
        if execute and exit_candidates:
            self.execute_exits(exit_candidates)

        # Step 4: Generate trade plan
        candidates = self.generate_trade_plan(tech_signals, sentiment, market_data)

        if not candidates:
            print("\n📭 No trade candidates meet the threshold. Pipeline complete.")
            if not exit_candidates:
                self.notifier.send("📭 *Pipeline Complete*\nNo trade candidates meet threshold.")
            return

        # Step 5: Risk assessment
        assessed = self.run_risk_manager(candidates)

        # Step 6: Execute new entries (if enabled)
        if execute:
            require_confirm = self.decision_cfg.get("require_human_confirm", True)
            self.execute_trades(assessed, require_confirmation=require_confirm)
        else:
            approved = [t for t in assessed if t.get("approved")]
            print(f"\n📊 Pipeline Complete: {len(approved)} trades approved (execution disabled)")
            print("   Run with --trade flag to execute orders")

        # Telegram notifications
        approved = [t for t in assessed if t.get("approved")]
        rejected = [t for t in assessed if not t.get("approved")]

        for trade in approved:
            self.notifier.alert_signal(
                symbol=trade["symbol"],
                side=trade.get("side", "buy"),
                score=trade.get("composite_score", 0),
                entry_price=trade.get("entry_price", 0),
                stop_loss=trade.get("stop_loss"),
                take_profit=trade.get("take_profit"),
                rsi=trade.get("rsi"),
                trend=trade.get("trend"),
            )

        self.notifier.report_pipeline_summary(candidates, approved, rejected)

        account = self.client.get_account()
        positions = self.client.get_positions()
        self.notifier.report_portfolio(account, positions)

        # Final summary
        self._print_summary(assessed)

    def _print_summary(self, trades: list[dict]):
        """Print final pipeline summary."""
        print("\n" + "=" * 60)
        print("📋 PIPELINE SUMMARY")
        print("=" * 60)

        approved = [t for t in trades if t.get("approved")]
        rejected = [t for t in trades if not t.get("approved")]

        if approved:
            print(f"\n  ✅ Approved ({len(approved)}):")
            for t in approved:
                print(f"     {t['symbol']:8s} | Score: {t['composite_score']:.3f} | "
                      f"Qty: {t['suggested_qty']}")

        if rejected:
            print(f"\n  ❌ Rejected ({len(rejected)}):")
            for t in rejected:
                reason = t.get("risk_assessment", {}).get("reason", "Unknown")
                print(f"     {t['symbol']:8s} | Score: {t['composite_score']:.3f} | {reason}")

    # ══════════════════════════════════════════════
    # Utilities
    # ══════════════════════════════════════════════

    def _get_bars(self, symbol: str, asset_type: str, timeframe: str = "1Day", lookback_days: int = 90):
        """Fetch bars with caching to avoid duplicate API calls."""
        cache_key = (symbol, timeframe, lookback_days)
        if cache_key in self._bar_cache:
            return self._bar_cache[cache_key]
        if asset_type == "crypto":
            bars = self.client.get_crypto_bars(symbol, timeframe, lookback_days)
        else:
            bars = self.client.get_stock_bars(symbol, timeframe, lookback_days)
        if bars is not None:
            self._bar_cache[cache_key] = bars
        return bars

    def _save_state(self, filename: str, data: dict):
        """Save data to shared state directory."""
        path = self.state_dir / filename
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _log_trade(self, trade: dict, result: dict):
        """Append trade to trade log."""
        log_path = self.log_dir / "trade_log.json"
        logs = []
        if log_path.exists():
            with open(log_path) as f:
                logs = json.load(f)

        logs.append({
            "timestamp": datetime.now().isoformat(),
            "symbol": trade["symbol"],
            "side": trade["side"],
            "qty": trade["suggested_qty"],
            "entry_price": trade["entry_price"],
            "stop_loss": trade.get("stop_loss"),
            "take_profit": trade.get("take_profit"),
            "score": trade["composite_score"],
            "order_id": result["id"],
            "order_status": result["status"],
        })

        with open(log_path, "w") as f:
            json.dump(logs, f, indent=2, default=str)


# ══════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent Trading System")
    parser.add_argument("--trade", action="store_true", help="Enable trade execution")
    parser.add_argument("--config", default="config/settings.yaml", help="Config file path")
    args = parser.parse_args()

    orchestrator = TradingOrchestrator(config_path=args.config)
    orchestrator.run_pipeline(execute=args.trade)
