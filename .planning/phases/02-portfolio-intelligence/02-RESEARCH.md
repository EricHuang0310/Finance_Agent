# Phase 2: Portfolio Intelligence - Research

**Researched:** 2026-04-03
**Domain:** Portfolio correlation analysis, position sizing optimization, trade journaling
**Confidence:** HIGH

## Summary

Phase 2 adds a Portfolio Strategist agent that gates new entries by analyzing cross-position correlations, and implements structured trade journals with lifecycle tracking. The codebase already has all the primitives needed: `_bar_cache` provides cached OHLCV data, `pandas.DataFrame.corr()` handles rolling correlation without new dependencies, `RiskAssessment` dataclass provides the post-processing hook, and `save_state_atomic()` handles safe JSON writes for the trade journal.

The Portfolio Strategist is a hybrid agent: a `task_portfolio_strategist()` code function computes the 20-day rolling correlation matrix from cached bar data, then an LLM (Sonnet) produces a narrative assessment of portfolio diversification quality and partial close suggestions. This fits the established pattern where quantitative work is done in task functions and LLM reasoning handles qualitative judgment.

**Primary recommendation:** Insert `task_portfolio_strategist()` after `task_risk_manager()` in the pipeline. It post-processes approved trades from `RiskAssessment`, reducing or rejecting positions whose correlation with existing holdings exceeds the threshold. Trade journal writes hook into `task_execute_trades()` (on fill) and `task_execute_exits()` (on close) using a new `trade_journal.json` file separate from the existing `trade_log.json`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** 20-day rolling window for correlation computation, matching existing screener lookback
- **D-04:** Journal entries at TWO lifecycle points: on fill (entry thesis, signals, scoring) and on close (exit data, P&L, holding period, outcome tag)
- **D-05:** Outcome tagging: Win (P&L > 0), Loss (P&L < 0), Scratch (|P&L| < 0.5%). R-multiple = P&L / initial risk (stop distance from entry)
- **D-06:** Pipeline placement at Claude's discretion
- **D-07:** Portfolio Strategist is hybrid: code for correlation + LLM for narrative (Sonnet tier)
- **D-07/P1:** Agent specs in Chinese, in `agents/` directory
- **D-09/P1:** Hybrid communication: SendMessage + JSON files
- **D-12/P1:** Graceful degradation: Portfolio Strategist failure should not halt pipeline
- **D-03:** Portfolio Strategist SHOULD suggest partial closes for concentrated portfolios

### Claude's Discretion
- Correlation computation method (price correlation, sector hybrid, or factor-based)
- Correlation threshold for flagging (0.7 suggested by research)
- Sizing adjustment strategy (reduce, reject, or reduce+warn)
- Pipeline placement (after or before Risk Manager)
- portfolio_construction.json schema details
- Trade journal storage format (new JSON file vs extending trade_log.json)
- How partial close suggestions integrate with Position Reviewer

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PORT-01 | Portfolio Strategist analyzes cross-position correlations before new positions are approved | Correlation computation via pandas DataFrame.corr() on 20-day rolling close prices from _bar_cache; no new dependencies needed |
| PORT-02 | Portfolio Strategist produces portfolio_construction.json with sizing adjustments to prevent approving highly correlated positions | New task function post-processes RiskAssessment approved trades, writes portfolio_construction.json via save_state_atomic() |
| PORT-03 | Portfolio Strategist runs after Risk Manager and before Executor, as an additional optimization layer | Insert between task_risk_manager() and task_execute_trades() in run_full_pipeline() and team_orchestrator Phase Group 4 |
| MEM-02 | Add structured trade journal with entry/exit prices, P&L, thesis, and outcome tagging | Hook into task_execute_trades() (on fill) and task_execute_exits() (on close); new trade_journal.json with R-multiple |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.0.1 (installed: 3.0.1) | DataFrame.corr() for rolling correlation matrix | Already in stack, native correlation support with Pearson/Spearman methods |
| numpy | 1.24+ (installed: 2.4.2) | Array operations for price matrix construction | Already in stack, np.corrcoef as fallback |
| pyyaml | 6.0+ | Config loading for new portfolio section | Already in stack |
| filelock | (installed) | Concurrent-safe trade journal writes | Already used by _log_trade() |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| scipy | N/A | NOT needed | pandas handles all correlation computation for a small portfolio (max 100 positions). Do NOT add scipy. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pandas.DataFrame.corr() | numpy.corrcoef() | pandas is cleaner for labeled correlation matrices with symbol names; numpy requires manual label management |
| Pearson correlation | Spearman rank correlation | Spearman is more robust to outliers but Pearson is standard for price returns; recommend Pearson as default |
| Separate trade_journal.json | Extending trade_log.json | Separate file avoids breaking existing trade_log consumers; cleaner lifecycle tracking |

**Installation:**
```bash
# No new packages needed -- all dependencies already installed
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── portfolio/
│   ├── __init__.py
│   └── strategist.py      # PortfolioStrategist class: correlation + sizing
├── orchestrator.py          # Modified: no changes to class, pipeline uses task function
├── agents_launcher.py       # Modified: add task_portfolio_strategist(), journal hooks
└── utils/
    └── state_io.py          # Reuse save_state_atomic()

agents/
├── risk_mgmt/
│   └── portfolio_strategist.md   # New agent spec (Chinese, Sonnet tier)

config/
└── settings.yaml            # New portfolio: section
```

### Pattern 1: Hybrid Agent (Code + LLM)
**What:** Quantitative computation in a Python task function, qualitative narrative via LLM reasoning in the agent spec.
**When to use:** When the agent needs both deterministic calculations and judgment.
**Example:**
```python
# task_portfolio_strategist() in agents_launcher.py
def task_portfolio_strategist(assessed: list[dict]) -> list[dict]:
    """Hybrid agent: code computes correlation, LLM reasons about diversification."""
    orch = get_orchestrator()
    strategist = PortfolioStrategist(orch.config)

    # 1. Code path: compute correlation matrix from cached bars
    positions = orch.client.get_positions()
    approved = [t for t in assessed if t.get("approved")]
    
    correlation_result = strategist.analyze_correlations(
        approved_trades=approved,
        existing_positions=positions,
        bar_getter=orch._get_bars,
    )
    
    # 2. Code path: apply sizing adjustments
    adjusted = strategist.adjust_sizing(approved, correlation_result)
    
    # 3. Save portfolio_construction.json
    save_state_atomic(
        Path(orch.state_dir) / "portfolio_construction.json",
        correlation_result,
    )
    
    return adjusted  # Modified assessed list with sizing changes
```

### Pattern 2: Post-Risk-Manager Gate
**What:** Portfolio Strategist sits between Risk Manager and Executor, post-processing approved trades.
**When to use:** When adding an optimization layer that should not override hard risk limits.
**Why this placement:** Risk Manager enforces hard limits (kill switch, max exposure, sector concentration). Portfolio Strategist is an optimization layer that further reduces sizing or rejects based on portfolio-level correlation. This ordering ensures hard limits are never bypassed.

**Pipeline placement in run_full_pipeline():**
```python
# Phase 3: Risk assessment
assessed = task_risk_manager(candidates)

# Phase 3.5: Portfolio optimization (NEW)
try:
    assessed = task_portfolio_strategist(assessed)
except Exception as e:
    print(f"  Warning: Portfolio Strategist failed: {e}. Proceeding with risk-assessed trades.")
    # Graceful degradation per D-12

# Phase 4: Execute
approved = [t for t in assessed if t.get("approved")]
```

### Pattern 3: Trade Journal Lifecycle
**What:** Journal entries written at two lifecycle points, keyed by order_id for cross-referencing.
**When to use:** For the trade journal requirement (MEM-02).
**Example:**
```python
# On fill (inside task_execute_trades, after order placed):
journal_entry = {
    "order_id": result["id"],
    "symbol": trade["symbol"],
    "side": trade["side"],
    "entry_price": trade["entry_price"],
    "qty": trade["suggested_qty"],
    "stop_loss": trade.get("stop_loss"),
    "take_profit": trade.get("take_profit"),
    "initial_risk": abs(trade["entry_price"] - trade["stop_loss"]) if trade.get("stop_loss") else None,
    "entry_thesis": {
        "composite_score": trade.get("composite_score"),
        "sector": trade.get("sector"),
        "market_regime": trade.get("market_regime"),
        "cio_stance": trade.get("risk_assessment", {}).get("cio_stance"),
        "sizing_adjustments": trade.get("risk_assessment", {}).get("sizing_adjustments", []),
    },
    "filled_at": datetime.now().isoformat(),
    "status": "open",
}

# On close (inside task_execute_exits, after position closed):
# Look up the open journal entry by symbol, update:
journal_update = {
    "exit_price": candidate["current_price"],
    "exit_reason": candidate["exit_reason"],
    "closed_at": datetime.now().isoformat(),
    "pnl": (exit_price - entry_price) * qty * direction,
    "pnl_pct": pnl / (entry_price * qty),
    "holding_days": (close_date - fill_date).days,
    "r_multiple": pnl_per_share / initial_risk if initial_risk else None,
    "outcome": "win" if pnl > 0 else ("scratch" if abs(pnl_pct) < 0.005 else "loss"),
    "status": "closed",
}
```

### Pattern 4: Partial Close Suggestions for Concentrated Portfolios
**What:** Portfolio Strategist identifies existing positions that contribute to portfolio concentration and suggests partial closes.
**When to use:** When the portfolio becomes overly correlated (D-03).
**Integration with Position Reviewer:** Output in the same format as `ExitSignal` with `exit_action: "partial_close"` so the executor can handle it identically.
```python
# Output format compatible with task_execute_exits():
partial_close_suggestion = {
    "symbol": "NVDA",
    "side": "long",
    "qty": 10,  # full qty
    "current_price": 850.0,
    "avg_entry_price": 800.0,
    "unrealized_pl": 500.0,
    "unrealized_plpc": 0.0625,
    "exit_action": "partial_close",
    "exit_reason": "Portfolio concentration: correlation with AMD=0.85, AVGO=0.78",
    "exit_score": 0.6,
    "partial_close_pct": 0.25,  # Suggest closing 25%
    "source": "portfolio_strategist",  # Distinguish from position_reviewer
}
```

### Anti-Patterns to Avoid
- **Overriding Risk Manager approvals:** Portfolio Strategist must NEVER approve a trade that Risk Manager rejected. It can only reduce or reject approved trades.
- **Recomputing bar data:** Use `orch._get_bars()` which hits the cache. Never call `orch.client.get_stock_bars()` directly.
- **Mutating assessed trade dicts in-place:** Create new dicts with updated fields per the project's immutability convention. (Note: the existing codebase does mutate dicts in `run_risk_manager()`, so follow the existing pattern for consistency within this module, but prefer returning new dicts in new code.)
- **Blocking pipeline on missing data:** If a symbol has < 20 days of bar data, skip it from correlation analysis rather than failing.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Correlation matrix | Custom loop computing pairwise correlations | `pandas.DataFrame.corr()` on a DataFrame of close prices | Handles NaN, efficient, returns labeled matrix |
| Atomic JSON writes | Manual temp-file-then-rename | `save_state_atomic()` from `src/utils/state_io` | Already battle-tested, handles directory creation |
| File locking for journal | Custom lock implementation | `filelock.FileLock` (already used in `_log_trade()`) | Proven concurrent safety |
| Position data | Manual portfolio tracking | `orch.client.get_positions()` | Always current from Alpaca API |
| Bar data fetching | Direct API calls | `orch._get_bars(symbol, "stock", "1Day", 20)` | Deduplicates calls via _bar_cache |

**Key insight:** The codebase already has all the infrastructure. This phase is about combining existing primitives (bar cache + positions API + atomic writes + task function pattern) into a new analytical layer.

## Common Pitfalls

### Pitfall 1: Stale Bar Cache for Correlation
**What goes wrong:** The bar cache is keyed by `(symbol, timeframe, lookback_days)`. Portfolio Strategist needs 20-day bars, but the screener already cached 20-day bars. If the screener used a different timeframe or lookback, there could be cache misses leading to extra API calls.
**Why it happens:** Different pipeline stages may request different lookback periods.
**How to avoid:** Always request `_get_bars(symbol, "stock", "1Day", 20)` consistently. The cache will hit if any prior stage already requested the same parameters. If not, it is a single additional API call per new symbol -- acceptable.
**Warning signs:** Slow portfolio strategist execution time.

### Pitfall 2: Sparse Correlation Matrix
**What goes wrong:** Some symbols may have < 20 days of data (IPOs, recent listings). Computing correlation with insufficient data points gives unreliable results.
**Why it happens:** The 20-day window requires at least 20 trading days of data.
**How to avoid:** Require a minimum of 15 data points for a valid correlation pair. If fewer, treat the pair as "unknown correlation" (do not penalize but flag).
**Warning signs:** NaN values in the correlation matrix.

### Pitfall 3: Journal Entry Orphaning
**What goes wrong:** Fill journal entry is written but the trade is never closed (system crash, manual intervention, position transferred). The journal has permanent "open" entries.
**Why it happens:** Two-phase write pattern with no cleanup mechanism.
**How to avoid:** EOD Review (already running) should reconcile open journal entries against actual Alpaca positions. If a journal entry is "open" but the position no longer exists in Alpaca, mark it as "closed_unknown" with current market data.
**Warning signs:** Growing count of "open" journal entries that don't match Alpaca positions.

### Pitfall 4: Correlation Threshold Too Aggressive
**What goes wrong:** A threshold of 0.7 may reject too many trades in a correlated market (e.g., all tech stocks correlate > 0.7 during risk-on rallies). This creates a "no trades allowed" scenario.
**Why it happens:** Stock correlations increase during bull markets and especially during selloffs.
**How to avoid:** Use 0.7 as the default but implement a graduated response: 0.7-0.8 = reduce size by 30%, 0.8-0.9 = reduce by 50%, >0.9 = reject. Also consider the CIO stance: if aggressive, relax thresholds slightly.
**Warning signs:** Portfolio Strategist rejecting all approved trades consistently.

### Pitfall 5: Partial Close Conflicts with Position Reviewer
**What goes wrong:** Both Position Reviewer and Portfolio Strategist suggest partial closes for the same position, resulting in conflicting or double-close scenarios.
**Why it happens:** Two independent agents evaluate the same positions with different criteria.
**How to avoid:** Portfolio Strategist's partial close suggestions go into `portfolio_construction.json` as suggestions, not direct execution. The team prompt or pipeline decides which source to prioritize. Simple rule: Position Reviewer's exit signals take precedence (they're thesis-based); Portfolio Strategist's suggestions are additive.
**Warning signs:** Same symbol appearing in both exit_candidates and portfolio partial close suggestions.

## Code Examples

### Correlation Computation (Core Algorithm)
```python
import pandas as pd
from pathlib import Path

class PortfolioStrategist:
    def __init__(self, config: dict):
        port_cfg = config.get("portfolio", {})
        self.lookback_days = port_cfg.get("correlation_lookback_days", 20)
        self.corr_warn_threshold = port_cfg.get("correlation_warn_threshold", 0.7)
        self.corr_reject_threshold = port_cfg.get("correlation_reject_threshold", 0.9)
        self.corr_reduce_pct = port_cfg.get("correlation_reduce_pct", 0.3)
        self.min_data_points = port_cfg.get("min_correlation_data_points", 15)

    def compute_correlation_matrix(
        self,
        symbols: list[str],
        bar_getter,
    ) -> tuple[pd.DataFrame, dict]:
        """Compute pairwise Pearson correlation from daily close returns.
        
        Returns:
            (correlation_matrix, metadata) where metadata includes
            symbols_skipped and data_points per symbol.
        """
        close_prices = {}
        skipped = []
        
        for symbol in symbols:
            bars = bar_getter(symbol, "stock", "1Day", self.lookback_days)
            if bars is None or len(bars) < self.min_data_points:
                skipped.append(symbol)
                continue
            # bars is a pandas DataFrame with 'close' column
            close_prices[symbol] = bars["close"].values[-self.lookback_days:]
        
        if len(close_prices) < 2:
            return pd.DataFrame(), {"skipped": skipped, "reason": "insufficient symbols"}
        
        # Build DataFrame of returns (not prices) for correlation
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
```

### Sizing Adjustment Logic
```python
    def adjust_sizing(
        self,
        assessed: list[dict],
        existing_symbols: list[str],
        corr_matrix: pd.DataFrame,
    ) -> list[dict]:
        """Reduce or reject approved trades based on correlation with existing holdings."""
        result = []
        
        for trade in assessed:
            if not trade.get("approved"):
                result.append(trade)  # Pass through rejected trades unchanged
                continue
            
            symbol = trade["symbol"]
            if symbol not in corr_matrix.columns:
                result.append(trade)  # No correlation data, pass through
                continue
            
            # Check correlation with existing positions
            max_corr = 0.0
            correlated_with = []
            for existing in existing_symbols:
                if existing in corr_matrix.columns and existing != symbol:
                    corr_val = abs(corr_matrix.loc[symbol, existing])
                    if corr_val > max_corr:
                        max_corr = corr_val
                    if corr_val >= self.corr_warn_threshold:
                        correlated_with.append((existing, round(corr_val, 3)))
            
            # Apply graduated response
            adjusted_trade = {**trade}  # Shallow copy
            
            if max_corr >= self.corr_reject_threshold:
                adjusted_trade["approved"] = False
                adjusted_trade["portfolio_rejection"] = (
                    f"Correlation {max_corr:.2f} >= {self.corr_reject_threshold} "
                    f"with {correlated_with}"
                )
            elif max_corr >= self.corr_warn_threshold:
                reduction = self.corr_reduce_pct
                old_qty = adjusted_trade["suggested_qty"]
                new_qty = max(1, int(old_qty * (1 - reduction)))
                adjusted_trade["suggested_qty"] = new_qty
                sizing_adj = adjusted_trade.get("risk_assessment", {}).get("sizing_adjustments", [])
                sizing_adj.append(f"portfolio_correlation({max_corr:.2f}): {old_qty} -> {new_qty}")
                adjusted_trade["portfolio_correlation"] = {
                    "max_correlation": max_corr,
                    "correlated_with": correlated_with,
                    "action": "reduce",
                }
            
            result.append(adjusted_trade)
        
        return result
```

### Trade Journal Write Functions
```python
from pathlib import Path
from datetime import datetime
from filelock import FileLock
from src.utils.state_io import save_state_atomic

JOURNAL_PATH = Path("logs/trade_journal.json")
JOURNAL_LOCK = Path("logs/trade_journal.json.lock")


def journal_on_fill(trade: dict, order_result: dict) -> None:
    """Write journal entry when a trade is filled."""
    entry = {
        "order_id": order_result["id"],
        "symbol": trade["symbol"],
        "side": trade["side"],
        "qty": trade["suggested_qty"],
        "entry_price": trade["entry_price"],
        "stop_loss": trade.get("stop_loss"),
        "take_profit": trade.get("take_profit"),
        "initial_risk": (
            abs(trade["entry_price"] - trade["stop_loss"])
            if trade.get("stop_loss") else None
        ),
        "entry_thesis": {
            "composite_score": trade.get("composite_score"),
            "sector": trade.get("sector"),
            "signals_at_entry": trade.get("signals_summary", {}),
            "cio_stance": trade.get("risk_assessment", {}).get("cio_stance"),
            "portfolio_correlation": trade.get("portfolio_correlation"),
        },
        "filled_at": datetime.now().isoformat(),
        "status": "open",
    }
    _append_journal(entry)


def journal_on_close(candidate: dict, order_result: dict) -> None:
    """Update journal entry when a position is closed."""
    journal = _load_journal()
    
    # Find matching open entry by symbol
    for entry in reversed(journal):
        if entry["symbol"] == candidate["symbol"] and entry["status"] == "open":
            entry_price = entry["entry_price"]
            exit_price = candidate["current_price"]
            qty = entry["qty"]
            direction = 1 if entry["side"] == "buy" else -1
            pnl_per_share = (exit_price - entry_price) * direction
            pnl = pnl_per_share * qty
            pnl_pct = pnl_per_share / entry_price if entry_price else 0
            initial_risk = entry.get("initial_risk")
            
            entry["exit_price"] = exit_price
            entry["exit_reason"] = candidate.get("exit_reason", "unknown")
            entry["closed_at"] = datetime.now().isoformat()
            entry["pnl"] = round(pnl, 2)
            entry["pnl_pct"] = round(pnl_pct, 4)
            entry["r_multiple"] = (
                round(pnl_per_share / initial_risk, 2)
                if initial_risk and initial_risk > 0 else None
            )
            entry["outcome"] = _classify_outcome(pnl_pct)
            entry["holding_days"] = _compute_holding_days(
                entry["filled_at"], entry["closed_at"]
            )
            entry["status"] = "closed"
            entry["close_order_id"] = order_result["id"]
            break
    
    _save_journal(journal)


def _classify_outcome(pnl_pct: float) -> str:
    """Win/Loss/Scratch classification per D-05."""
    if abs(pnl_pct) < 0.005:  # < 0.5%
        return "scratch"
    return "win" if pnl_pct > 0 else "loss"
```

### Config Section
```yaml
# Add to config/settings.yaml
portfolio:
  # Correlation analysis
  correlation_lookback_days: 20       # Match screener lookback (D-01)
  correlation_warn_threshold: 0.7     # Flag correlated positions
  correlation_reject_threshold: 0.9   # Reject highly correlated positions
  correlation_reduce_pct: 0.30        # Reduce sizing by 30% when warned
  min_correlation_data_points: 15     # Skip symbols with < 15 days data
  # Partial close for concentration
  concentration_corr_threshold: 0.8   # Suggest partial close when existing portfolio is this correlated
  concentration_partial_pct: 0.25     # Suggest closing 25% of concentrated positions

# Add to model_tiers:
model_tiers:
  portfolio-strategist: sonnet        # D-07: Sonnet for narrative reasoning
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Individual position risk only | Portfolio-level correlation analysis | This phase | Prevents approving 5 correlated positions individually |
| Unstructured trade_log.json | Structured trade journal with R-multiple | This phase | Enables strategy learning in Phase 3 (MEM-03) |
| Exit decisions only from Position Reviewer | Dual source: Position Reviewer + Portfolio Strategist | This phase | Portfolio concentration triggers partial closes |

## Open Questions

1. **How to handle new-to-portfolio symbols with no existing correlation data?**
   - What we know: First trade of the day has no existing positions to correlate against. Subsequent trades build up the portfolio context.
   - What's unclear: Should the first approved trade always pass through the Portfolio Strategist unchecked?
   - Recommendation: If portfolio has 0 positions, skip correlation analysis entirely. If 1+ positions exist, correlate new candidates against them.

2. **Journal reconciliation for manually closed positions**
   - What we know: Positions can be closed manually via Alpaca dashboard, bypassing the pipeline.
   - What's unclear: How to detect and journal-close these orphaned entries.
   - Recommendation: EOD Review (already runs daily) should reconcile journal entries against Alpaca positions. Mark orphans as "closed_manual" with best-effort P&L from Alpaca data.

3. **Correlation with short positions**
   - What we know: The system supports both long and short positions. Two longs in correlated stocks increase risk. A long and short in correlated stocks is actually a hedge.
   - What's unclear: How to differentiate correlation risk from hedge benefit.
   - Recommendation: For same-direction positions (both long or both short), high correlation = risk. For opposite-direction positions, high correlation = hedge (beneficial). Factor the direction into the sizing adjustment logic.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pandas | Correlation matrix | Yes | 3.0.1 | -- |
| numpy | Array operations | Yes | 2.4.2 | -- |
| filelock | Journal concurrency | Yes | installed | -- |
| scipy | NOT needed | No | -- | pandas.DataFrame.corr() handles all needs |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Project Constraints (from CLAUDE.md)

- **No new framework dependencies** -- all correlation work uses existing pandas/numpy
- **Agent specs in Chinese** -- Portfolio Strategist spec must be in Chinese per D-07/P1
- **`shared_state/YYYY-MM-DD/` pattern** -- portfolio_construction.json follows this convention
- **`task_*()` function pattern** -- new task_portfolio_strategist() follows agents_launcher.py conventions
- **No tests configured** -- CLAUDE.md explicitly states no automated tests, linter, or formatter
- **Config in settings.yaml** -- new portfolio section follows existing YAML structure
- **Immutability preference** -- new code should return new dicts rather than mutating inputs
- **Graceful degradation** -- Portfolio Strategist failure must not halt pipeline (D-12/P1)
- **save_state_atomic()** -- use for all JSON state file writes
- **FileLock** -- use for concurrent-safe trade journal writes

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `src/orchestrator.py`, `src/risk/manager.py`, `src/agents_launcher.py`, `src/team_orchestrator.py`, `src/analysis/position_reviewer.py`, `src/utils/state_io.py`
- `config/settings.yaml` -- existing config structure, risk section, model tiers
- Agent spec pattern from `agents/strategic/cio.md` and `agents/risk_mgmt/risk_manager.md`
- pandas 3.0.1 `DataFrame.corr()` -- verified available via local Python environment
- numpy 2.4.2 `corrcoef` -- verified available

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` -- prior research validating Portfolio Strategist role and 0.7 correlation threshold
- `.planning/REQUIREMENTS.md` -- PORT-01, PORT-02, PORT-03, MEM-02 requirement definitions

### Tertiary (LOW confidence)
- Correlation threshold of 0.7 as default -- commonly cited in portfolio management literature but optimal value depends on market conditions. Configurable via settings.yaml.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed, no new dependencies
- Architecture: HIGH -- follows existing patterns exactly (task_* functions, agent specs, config structure, state files)
- Pitfalls: MEDIUM-HIGH -- correlation pitfalls well-understood, journal orphaning is a real risk mitigated by EOD reconciliation

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable -- no fast-moving dependencies)
