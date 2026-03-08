"""
Multi-Agent Trading Orchestrator
Coordinates all agents, aggregates signals, and manages the trading pipeline.

Usage:
    python -m src.orchestrator          # Run analysis pipeline
    python -m src.orchestrator --trade   # Run analysis + execute trades (paper)
"""

import json
import os
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import yaml

from src.alpaca_client import AlpacaClient
from src.state_dir import get_state_dir, cleanup_old_state
from src.analysis.technical import TechnicalAnalyzer
from src.analysis.sentiment import SentimentAnalyzer
from src.analysis.screener import SymbolScreener
from src.analysis.position_reviewer import PositionReviewer
from src.analysis.fundamentals import FundamentalsAnalyzer
from src.risk.manager import RiskManager
from src.notifications.telegram import TelegramNotifier
from src.memory.situation_memory import SituationMemory

# yfinance for VIX data (optional, already used by fundamentals)
try:
    import yfinance as yf
    _HAS_YFINANCE = True
except ImportError:
    _HAS_YFINANCE = False

ET = ZoneInfo("America/New_York")


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
        self.screener = SymbolScreener(self.client, self.config,
                                       bars_getter=lambda sym, at, **kw: self._get_bars(sym, at, **kw))
        self.risk_manager = RiskManager(self.config)
        self.position_reviewer = PositionReviewer(self.config)
        self.notifier = TelegramNotifier()

        # Shared state paths (daily subfolder)
        self.state_dir = get_state_dir()
        os.environ["SHARED_STATE_DIR"] = str(self.state_dir)
        cleanup_old_state(keep_days=7)
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)

        # Fundamentals analyzer (optional — requires yfinance)
        self.fundamentals_analyzer = FundamentalsAnalyzer()

        # Memory banks (BM25-based, one per decision role)
        mem_cfg = self.config.get("memory", {})
        mem_dir = mem_cfg.get("storage_dir", "memory_store")
        max_mem = mem_cfg.get("max_memories", 500)
        self.bull_memory = SituationMemory("bull_memory", mem_dir, max_entries=max_mem)
        self.bear_memory = SituationMemory("bear_memory", mem_dir, max_entries=max_mem)
        self.research_judge_memory = SituationMemory("research_judge_memory", mem_dir, max_entries=max_mem)
        self.risk_judge_memory = SituationMemory("risk_judge_memory", mem_dir, max_entries=max_mem)
        self.decision_engine_memory = SituationMemory("decision_engine_memory", mem_dir, max_entries=max_mem)

        # Bar data cache to avoid duplicate API calls
        self._bar_cache = {}

        # Config shortcuts
        self.watchlist_mode = self.config.get("watchlist_mode", "static")
        self.watchlist_stocks = self.config.get("watchlist", {}).get("stocks", [])
        self.weights = self.config.get("scoring", {})
        self.decision_cfg = self.config.get("decision", {})
        self.regime_cfg = self.config.get("regime", {})

    # ══════════════════════════════════════════════
    # Agent 0: Symbol Screener (Phase 0)
    # ══════════════════════════════════════════════

    def run_symbol_screener(self) -> dict:
        """Dynamically screen the market for the best symbols to trade."""
        print("\n" + "=" * 60)
        print("🔎 AGENT 0: Symbol Screener - Discovering Symbols")
        print("=" * 60)

        result = self.screener.screen_all()

        # Update the watchlist used by all downstream agents
        self.watchlist_stocks = result["stocks"]

        print(f"\n  📋 Dynamic watchlist:")
        print(f"     Stocks ({len(result['stocks'])}): {', '.join(result['stocks'][:10])}"
              + (f" ... +{len(result['stocks'])-10} more" if len(result['stocks']) > 10 else ""))

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

        market_data = {"stocks": {}, "timestamp": datetime.now().isoformat()}

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

        # Detect market regime and include in market data (now returns dict)
        regime_result = self._detect_market_regime()
        market_data["market_regime"] = regime_result
        print(f"\n  📈 Market Regime: {regime_result['regime']} (confidence: {regime_result['regime_confidence']:.2f})")

        # Save to shared state
        self._save_state("market_overview.json", market_data)
        return market_data

    def _detect_market_regime(self) -> dict:
        """Determine market regime using SPY EMA alignment, VIX, and cross-asset signals.

        Returns dict with 'regime' (risk_on/risk_off/transitional) and 'regime_confidence' (0-1).
        """
        try:
            spy_bars = self._get_bars("SPY", "stock", lookback_days=250)
            if spy_bars is None or len(spy_bars) < 200:
                return {"regime": "transitional", "regime_confidence": 0.5}

            close = spy_bars["close"].astype(float)
            ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
            ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
            ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])

            # SPY EMA alignment (primary signal)
            if ema20 > ema50 > ema200:
                spy_regime = "risk_on"
                spy_confidence = 1.0
            elif ema20 < ema50 < ema200:
                spy_regime = "risk_off"
                spy_confidence = 1.0
            else:
                spy_regime = "transitional"
                spy_confidence = 0.5

            # VIX check via yfinance
            vix_force_threshold = self.regime_cfg.get("vix_force_risk_off", 35)
            vix_agrees = None  # None = no data, True/False = agrees with regime
            vix_value = None
            if _HAS_YFINANCE:
                try:
                    vix_ticker = yf.Ticker("^VIX")
                    vix_hist = vix_ticker.history(period="5d")
                    if vix_hist is not None and len(vix_hist) > 0:
                        vix_value = float(vix_hist["Close"].iloc[-1])
                        # Force risk_off if VIX extremely high
                        if vix_value > vix_force_threshold:
                            return {"regime": "risk_off", "regime_confidence": 1.0,
                                    "vix": vix_value, "vix_forced": True}
                        # VIX agreement check
                        if spy_regime == "risk_on" and vix_value < 20:
                            vix_agrees = True
                        elif spy_regime == "risk_off" and vix_value > 25:
                            vix_agrees = True
                        elif spy_regime == "risk_on" and vix_value > 25:
                            vix_agrees = False
                        elif spy_regime == "risk_off" and vix_value < 20:
                            vix_agrees = False
                except Exception:
                    pass

            # Cross-asset scanning (TLT, UUP)
            cross_symbols = self.regime_cfg.get("cross_asset_symbols", ["TLT", "UUP"])
            cross_agrees_count = 0
            cross_total = 0
            for cs in cross_symbols:
                try:
                    cs_bars = self._get_bars(cs, "stock", lookback_days=60)
                    if cs_bars is not None and len(cs_bars) >= 20:
                        cs_close = cs_bars["close"].astype(float)
                        cs_ema20 = float(cs_close.ewm(span=20, adjust=False).mean().iloc[-1])
                        cs_latest = float(cs_close.iloc[-1])
                        cross_total += 1
                        # TLT rising = bonds up = risk_off environment
                        # UUP rising = dollar strong = risk_off environment
                        cs_trend_up = cs_latest > cs_ema20
                        if spy_regime == "risk_off" and cs_trend_up:
                            cross_agrees_count += 1
                        elif spy_regime == "risk_on" and not cs_trend_up:
                            cross_agrees_count += 1
                        elif spy_regime == "transitional":
                            cross_agrees_count += 0.5
                except Exception:
                    pass

            # Compute regime_confidence: SPY alignment (60%) + VIX/cross-asset agreement (40%)
            agreement_score = 0.0
            agreement_sources = 0
            if vix_agrees is not None:
                agreement_score += 1.0 if vix_agrees else 0.0
                agreement_sources += 1
            if cross_total > 0:
                agreement_score += cross_agrees_count / cross_total
                agreement_sources += 1

            if agreement_sources > 0:
                agreement_pct = agreement_score / agreement_sources
            else:
                agreement_pct = 0.5  # No cross-asset data = neutral

            regime_confidence = spy_confidence * 0.6 + agreement_pct * 0.4
            regime_confidence = max(0.1, min(1.0, regime_confidence))

            result = {
                "regime": spy_regime,
                "regime_confidence": round(regime_confidence, 4),
            }
            if vix_value is not None:
                result["vix"] = round(vix_value, 2)
            return result

        except Exception:
            return {"regime": "transitional", "regime_confidence": 0.5}

    def _get_regime_weights(self, regime: str) -> dict:
        """Return scoring weights adjusted for the current market regime."""
        base_tech = self.weights.get("technical_analyst", 0.35)
        base_mkt = self.weights.get("market_analyst", 0.20)
        base_sent = self.weights.get("sentiment_analyst", 0.15)

        if regime == "risk_on":
            return {"tech": base_tech * 1.2, "market": base_mkt * 0.8, "sentiment": base_sent * 1.1}
        elif regime == "risk_off":
            return {"tech": base_tech, "market": base_mkt * 1.3, "sentiment": base_sent}
        elif regime == "transitional":
            return {"tech": base_tech * 0.9, "market": base_mkt * 0.9, "sentiment": base_sent * 0.9}
        return {"tech": base_tech * 0.9, "market": base_mkt * 0.9, "sentiment": base_sent * 0.9}

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

        signals = {"stocks": {}, "timestamp": datetime.now().isoformat()}

        # Stocks — use 300 days to get ~200 trading days for EMA-200 convergence
        for symbol in self.watchlist_stocks:
            try:
                bars = self._get_bars(symbol, "stock", lookback_days=300)
                if bars is not None and len(bars) >= 50:
                    signal = self.tech_analyzer.analyze(bars, symbol, "1Day")
                    signals["stocks"][symbol] = signal.to_dict()
                    emoji = "🟢" if signal.score > 0.3 else "🔴" if signal.score < -0.3 else "🟡"
                    print(f"  {emoji} {symbol}: score={signal.score:.3f} | "
                          f"trend={signal.trend} | RSI={signal.rsi:.1f} | ADX={signal.adx:.1f}")
                else:
                    print(f"  ⚠️  {symbol}: Insufficient data for analysis")
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
            days=3,
        )

        print(f"\n  📊 Market Sentiment: {sentiment['market_sentiment']} | "
              f"Fear & Greed: {sentiment['fear_greed_index']}/100")

        self._save_state("sentiment_signals.json", sentiment)
        return sentiment

    # ══════════════════════════════════════════════
    # Agent 3.5: Position Exit Review
    # ══════════════════════════════════════════════

    def run_position_exit_review(self, tech_signals: dict, market_data: dict,
                                  sentiment: dict = None) -> list[dict]:
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
            return self._get_bars(symbol, asset_type, lookback_days=300)

        results = self.position_reviewer.review_all(
            positions=positions,
            tech_signals=tech_signals,
            market_data=market_data,
            bars_getter=bars_getter,
            sentiment_data=sentiment,
        )

        exits = [r for r in results if r.exit_action == "close"]
        holds = [r for r in results if r.exit_action == "hold"]

        for r in results:
            if r.exit_action == "close":
                roi_pct = r.unrealized_plpc * 100
                urgency = f" [{r.exit_urgency}]" if hasattr(r, 'exit_urgency') else ""
                print(f"  📤 {r.symbol} ({r.side}): EXIT score={r.exit_score:.3f}{urgency} | "
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
        if summary.get("sector_exposure"):
            print(f"  🏭 Sector exposure: {summary['sector_exposure']}")

        if summary["kill_switch_active"]:
            print("  🚨 KILL SWITCH IS ACTIVE - NO TRADES ALLOWED")
            return []

        # Assess each candidate
        assessed = []
        for candidate in trade_candidates:
            if not candidate.get("entry_price"):
                print(f"  ⚠️  {candidate['symbol']}: missing entry price, skipping")
                continue

            assessment = self.risk_manager.assess_trade(
                symbol=candidate["symbol"],
                side=candidate.get("side", "buy"),
                entry_price=candidate["entry_price"],
                stop_loss_price=candidate.get("stop_loss"),
                take_profit_price=candidate.get("take_profit"),
                signal_score=candidate.get("composite_score", 0),
                catalyst_flag=candidate.get("catalyst_flag"),
                regime_conflict=candidate.get("regime_conflict", False),
                atr_pct=candidate.get("atr_pct", 0),
                sector=candidate.get("sector", "unknown"),
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
        """
        print("\n" + "=" * 60)
        print("🧠 Decision Engine - Aggregating Signals")
        print("=" * 60)

        min_buy = self.decision_cfg.get("min_score_to_buy", 0.3)
        min_sell = self.decision_cfg.get("min_score_to_sell", min_buy)
        candidates = []
        skipped_symbols = {}

        # Get regime info
        regime = "transitional"
        regime_confidence = 0.5
        if market_data:
            regime_data = market_data.get("market_regime", {})
            if isinstance(regime_data, dict):
                regime = regime_data.get("regime", "transitional")
                regime_confidence = regime_data.get("regime_confidence", 0.5)
            else:
                # Backward compatibility
                regime = regime_data if regime_data else "transitional"
                regime_confidence = 0.5

        rw = self._get_regime_weights(regime)
        print(f"  📈 Regime: {regime} (conf={regime_confidence:.2f}) → weights: tech={rw['tech']:.3f} mkt={rw['market']:.3f} sent={rw['sentiment']:.3f}")

        # Regime-adjusted thresholds
        effective_min_buy = min_buy
        effective_min_sell = min_sell
        if regime == "transitional":
            effective_min_buy = min_buy + 0.1
            effective_min_sell = min_sell + 0.1
        elif regime == "risk_off":
            effective_min_buy = max(min_buy, 0.6)

        def _score_symbol(symbol, signal, sent_data, mkt_score, asset_type):
            tech_score = signal.get("score", 0)
            tech_conf = signal.get("confidence", 1.0)
            sent_score = sent_data.get("score", 0) if sent_data else 0
            sent_conf = sent_data.get("confidence", 1.0) if sent_data else 0.2
            mkt_conf = regime_confidence

            # Signal conflict detection
            tech_dir = "bullish" if tech_score > 0.1 else "bearish" if tech_score < -0.1 else "neutral"
            sent_dir = "bullish" if sent_score > 0.1 else "bearish" if sent_score < -0.1 else "neutral"
            mkt_dir = "bullish" if mkt_score > 0.1 else "bearish" if mkt_score < -0.1 else "neutral"

            directions = [d for d in [tech_dir, sent_dir, mkt_dir] if d != "neutral"]
            if not directions:
                signal_alignment = "all_aligned"
            elif len(set(directions)) == 1:
                signal_alignment = "all_aligned"
            elif tech_dir != "neutral" and sent_dir != "neutral" and tech_dir != sent_dir:
                signal_alignment = "partial_conflict"
            else:
                signal_alignment = "partial_conflict"

            # Check regime conflict
            regime_conflict = False
            if regime == "risk_off" and tech_dir == "bullish":
                regime_conflict = True
                signal_alignment = "regime_conflict"
            elif regime == "risk_on" and tech_dir == "bearish":
                regime_conflict = True
                signal_alignment = "regime_conflict"

            # Confidence-weighted composite (regime-adjusted weights)
            weighted_tech = tech_score * rw["tech"] * tech_conf
            weighted_mkt = mkt_score * rw["market"] * mkt_conf
            weighted_sent = sent_score * rw["sentiment"] * sent_conf
            total_weight = rw["tech"] * tech_conf + rw["market"] * mkt_conf + rw["sentiment"] * sent_conf

            composite = (weighted_tech + weighted_mkt + weighted_sent) / total_weight if total_weight > 0 else 0

            # Signal alignment bonus/penalty
            if signal_alignment == "all_aligned":
                composite *= 1.05
            elif signal_alignment == "partial_conflict" and tech_dir != sent_dir and tech_dir != "neutral" and sent_dir != "neutral":
                composite *= 0.90

            composite = max(-1.0, min(1.0, composite))

            # Catalyst detection from sentiment
            catalyst_flag = None
            upcoming_earnings = sent_data.get("upcoming_earnings", False) if sent_data else False
            binary_event = sent_data.get("binary_event", False) if sent_data else False
            if upcoming_earnings:
                catalyst_flag = "earnings_imminent"
            elif binary_event:
                catalyst_flag = "binary_event"

            # Get sector from fundamentals cache if available
            sector = "unknown"
            try:
                fund_path = self.state_dir / "fundamentals_signals.json"
                if fund_path.exists():
                    import json as _json
                    with open(fund_path) as _f:
                        fund_data = _json.load(_f)
                    sym_fund = fund_data.get("signals", {}).get(symbol)
                    if sym_fund:
                        sector = sym_fund.get("sector", "unknown")
            except Exception:
                pass

            # ATR percentage for risk manager
            atr_pct = 0.0
            if signal.get("atr") and signal.get("entry_price") and signal["entry_price"] > 0:
                atr_pct = signal["atr"] / signal["entry_price"]

            if composite >= effective_min_buy or composite <= -effective_min_sell:
                side = "buy" if composite >= effective_min_buy else "sell"
                emoji = "🟢" if side == "buy" else "🔴"
                print(f"  {emoji} {symbol}: composite={composite:.3f} (conf: tech={tech_conf:.2f} sent={sent_conf:.2f} "
                      f"align={signal_alignment}) → {side.upper()} CANDIDATE")
                return {
                    "symbol": symbol,
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
                    "signal_alignment": signal_alignment,
                    "regime_conflict": regime_conflict,
                    "catalyst_flag": catalyst_flag,
                    "regime_confidence": regime_confidence,
                    "sector": sector,
                    "atr_pct": round(atr_pct, 4),
                }
            else:
                skipped_symbols[symbol] = f"composite={composite:.3f} below threshold"
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

        # Sort by absolute score (strongest signals first)
        candidates.sort(key=lambda x: abs(x["composite_score"]), reverse=True)

        self._save_state("decisions.json", {
            "timestamp": datetime.now().isoformat(),
            "market_regime": regime,
            "regime_confidence": regime_confidence,
            "candidates": candidates,
            "skipped_symbols": skipped_symbols,
            "min_score_threshold": effective_min_buy,
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
        now_et = datetime.now(ET)
        market_session = "regular"
        try:
            clock = self.client.is_market_open()
            if not clock["is_open"]:
                print(f"  ⚠️  Market is currently CLOSED. Next open: {clock['next_open']}")
                print(f"  ⚠️  Stock orders will be queued until market opens.")
                market_session = "closed"
        except Exception as e:
            print(f"  ⚠️  Could not check market hours: {e}")

        # Timing restrictions (Eastern Time): 9:30-9:45 and 15:45-16:00
        hour, minute = now_et.hour, now_et.minute
        in_restricted_window = (
            (hour == 9 and 30 <= minute < 45) or
            (hour == 15 and minute >= 45) or
            (hour == 16 and minute == 0)
        )

        tradeable = [t for t in approved_trades if t.get("approved")]

        if not tradeable:
            print("  📭 No approved trades to execute.")
            return

        for trade in tradeable:
            # Skip new entries during restricted windows (exits still allowed)
            if in_restricted_window and trade.get("action") != "close_position":
                print(f"  ⏳ {trade['symbol']}: Skipping new entry during restricted window "
                      f"({now_et.strftime('%H:%M')} ET)")
                continue

            # Liquidity pre-check
            mkt_info = None
            try:
                mkt_path = self.state_dir / "market_overview.json"
                if mkt_path.exists():
                    with open(mkt_path) as f:
                        mkt_info = json.load(f)
            except Exception:
                pass

            avg_vol = 0
            if mkt_info:
                avg_vol = mkt_info.get("stocks", {}).get(trade["symbol"], {}).get("avg_volume_20d", 0)

            estimated_slippage_bps = 5
            if avg_vol > 0 and trade.get("suggested_qty", 0) > 0:
                qty_ratio = trade["suggested_qty"] / avg_vol
                estimated_slippage_bps = 5 + qty_ratio * 1000

                if qty_ratio > 0.05:
                    print(f"  ❌ {trade['symbol']}: Qty ({trade['suggested_qty']}) > 5% of avg volume ({avg_vol}) - skipping")
                    continue
                elif qty_ratio > 0.01:
                    print(f"  ⚠️  {trade['symbol']}: Qty is {qty_ratio*100:.1f}% of avg volume - potential market impact")

            print(f"\n  📋 Trade Plan:")
            print(f"     Symbol: {trade['symbol']}")
            print(f"     Side: {trade['side'].upper()}")
            print(f"     Qty: {trade['suggested_qty']}")
            print(f"     Entry: ${trade['entry_price']:.2f}" if trade.get("entry_price") else "")
            print(f"     Stop Loss: ${trade['stop_loss']:.2f}" if trade.get("stop_loss") else "")
            print(f"     Take Profit: ${trade['take_profit']:.2f}" if trade.get("take_profit") else "")
            print(f"     Score: {trade['composite_score']:.3f}")
            print(f"     Est. Slippage: {estimated_slippage_bps:.1f} bps")

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

                # Log trade with slippage info
                trade_log_entry = dict(trade)
                trade_log_entry["estimated_slippage_bps"] = round(estimated_slippage_bps, 1)
                trade_log_entry["market_session"] = market_session
                self._log_trade(trade_log_entry, result)

                # Telegram notification
                self.notifier.alert_order_executed(
                    symbol=trade["symbol"],
                    side=trade["side"],
                    qty=trade["suggested_qty"],
                    price=trade.get("entry_price"),
                    order_id=result["id"],
                )

            except Exception as e:
                print(f"  ❌ Order failed: {e}")
                self.notifier.alert_order_rejected(trade["symbol"], str(e))

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

        # Step 3.5: Position exit review (now with sentiment data)
        exit_candidates = self.run_position_exit_review(tech_signals, market_data, sentiment)

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

        # Risk dashboard notification
        summary = self.risk_manager.get_risk_summary()
        self.notifier.report_risk_dashboard(summary)

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
            "estimated_slippage_bps": trade.get("estimated_slippage_bps"),
            "market_session": trade.get("market_session"),
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
