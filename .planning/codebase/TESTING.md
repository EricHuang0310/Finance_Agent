# Testing Patterns

**Analysis Date:** 2026-03-30

## Test Framework

**Runner:**
- None configured. No test framework is installed or referenced.

**Assertion Library:**
- None

**Run Commands:**
```bash
# No test commands exist. There are no tests to run.
```

## Current State: Zero Tests

The codebase has **zero automated tests**. This is explicitly acknowledged in `CLAUDE.md`:
> "There are no automated tests, linter, or formatter configured."

**Verification:**
- No test files found (`*.test.py`, `*_test.py`, `test_*.py`, `*.spec.py`)
- No `tests/` directory
- No `pytest.ini`, `pyproject.toml`, `setup.cfg`, or `tox.ini` with test configuration
- No `pytest`, `unittest`, or any test framework in `requirements.txt`
- No test-related scripts in `package.json` (which only contains `pptxgenjs` for presentation generation)

## Test File Organization

**Location:** N/A - no tests exist

**Recommended structure when adding tests:**
```
tests/
├── conftest.py              # Shared fixtures (mock AlpacaClient, sample bars DataFrame)
├── unit/
│   ├── test_technical.py    # TechnicalAnalyzer._rsi, _macd, _compute_score
│   ├── test_sentiment.py    # SentimentAnalyzer.score_text, _classify_headline, _detect_catalysts
│   ├── test_risk_manager.py # RiskManager.assess_trade (all rejection paths + sizing)
│   ├── test_position_reviewer.py  # Hard stops, soft scoring, partial close
│   ├── test_screener.py     # SymbolScreener._compute_metrics, filtering
│   ├── test_fundamentals.py # FundamentalsAnalyzer._build_signal
│   ├── test_situation_memory.py  # SituationMemory add/search/prune/persistence
│   ├── test_reflection.py   # Reflection helpers, performance attribution
│   └── test_debate_helpers.py    # Context assembly, result merging
├── integration/
│   ├── test_orchestrator.py # TradingOrchestrator pipeline with mocked API
│   └── test_alpaca_client.py # AlpacaClient with paper account
└── fixtures/
    ├── sample_bars.json     # Sample OHLCV DataFrame data
    ├── sample_signals.json  # Pre-computed technical signals
    └── sample_config.yaml   # Test configuration
```

## Mocking Requirements

**What MUST be mocked for unit tests:**
- `AlpacaClient` - all methods hit live Alpaca API (market data, orders, positions)
- `yfinance.Ticker` - external API calls in `src/analysis/fundamentals.py` and `src/analysis/sentiment.py`
- `httpx.Client` / `httpx.AsyncClient` - used in `src/notifications/telegram.py`
- `src.state_dir.get_state_dir()` - returns filesystem paths, creates directories
- File I/O for `shared_state/` JSON files
- `time.sleep()` in `src/analysis/fundamentals.py` (rate limiting delays)

**What NOT to mock:**
- `TechnicalAnalyzer` internal calculations (`_rsi`, `_macd`, `_bollinger_bands`, `_ema`, `_atr`) - these are pure math on pandas Series
- `RiskManager.assess_trade` logic - pure business rules, no I/O
- `SituationMemory` BM25 operations - pure in-memory computation
- `SentimentAnalyzer.score_text` - VADER is a local library, no API calls

## Test Priority Analysis

**High priority (pure logic, no I/O, high business value):**

1. **`src/analysis/technical.py` - `TechnicalAnalyzer._compute_score()`**
   - Composite scoring with 6 weighted components (RSI, MACD, EMA, BB, ADX, Volume)
   - Confidence calculation based on indicator agreement
   - Edge cases: insufficient data, extreme RSI values, ADX < 20 penalty
   - Input: numeric parameters. Output: `tuple[float, float]`

2. **`src/risk/manager.py` - `RiskManager.assess_trade()`**
   - 10+ rejection paths (kill switch, daily loss, max positions, max exposure, sector concentration, binary events, ADX filter, R:R ratio)
   - Position sizing with 4 adjustment factors (earnings, regime conflict, volatility, 90d proximity)
   - Input: trade parameters. Output: `RiskAssessment` dataclass

3. **`src/analysis/position_reviewer.py` - `PositionReviewer._check_hard_stops()`**
   - Breakeven stop, ATR gradient trailing stop, profit give-back
   - All use ATR-based calculations on position P&L
   - Critical for capital preservation

4. **`src/analysis/position_reviewer.py` - `PositionReviewer.review_position()` soft scoring**
   - 6-factor weighted scoring (trend 0.25, momentum 0.20, ATR trailing 0.20, market 0.10, time 0.15, events 0.10)
   - Threshold-based exit decision

5. **`src/memory/situation_memory.py` - `SituationMemory`**
   - Add/search/prune/persistence cycle
   - BM25 index rebuild
   - Max entries pruning (FIFO)

**Medium priority (some I/O but testable with mocks):**

6. **`src/analysis/sentiment.py` - `SentimentAnalyzer.analyze_symbol()`**
   - Time-decay weighted sentiment aggregation
   - Catalyst detection via regex
   - Signal vs noise classification
   - Needs mock for `self.client.get_news()`

7. **`src/analysis/screener.py` - `SymbolScreener._compute_metrics()`**
   - Pure computation: volume ratio, momentum, volatility, activity score
   - `screen_stocks()` filter chain needs integration test with mock bars

8. **`src/orchestrator.py` - `TradingOrchestrator.generate_trade_plan()`**
   - Regime-adjusted weight calculation
   - Confidence-weighted composite scoring
   - Candidate selection and sorting

**Lower priority (mostly I/O wrappers):**

9. **`src/alpaca_client.py`** - Thin wrapper around alpaca-py SDK
10. **`src/notifications/telegram.py`** - Message formatting (template correctness)
11. **`src/debate/helpers.py`** - JSON file assembly
12. **`src/memory/reflection.py`** - Performance attribution calculations

## Coverage Gaps (Everything)

**Current coverage: 0%**

**Most critical untested paths:**

| Area | Files | Risk |
|------|-------|------|
| Composite scoring | `src/analysis/technical.py` | Wrong scores lead to bad trades |
| Risk veto logic | `src/risk/manager.py` | Failed vetoes = unauthorized exposure |
| Hard stop exits | `src/analysis/position_reviewer.py` | Missed exits = capital loss |
| Position sizing | `src/risk/manager.py` | Oversized positions = excess risk |
| Kill switch | `src/risk/manager.py` | Failed kill switch = catastrophic loss |
| Memory pruning | `src/memory/situation_memory.py` | Memory leak if pruning breaks |
| Earnings detection | `src/analysis/sentiment.py` | Missing catalyst = surprise gap |

## Recommended Test Setup

**Install pytest and coverage:**
```bash
pip install pytest pytest-cov pytest-mock
```

**Minimal `pytest.ini` or `pyproject.toml` section:**
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

**Sample test for highest-priority target:**
```python
# tests/unit/test_technical.py
import pandas as pd
import pytest
from src.analysis.technical import TechnicalAnalyzer

@pytest.fixture
def analyzer():
    return TechnicalAnalyzer()

@pytest.fixture
def bullish_bars():
    """Create a DataFrame simulating a bullish trend."""
    # 100 bars with steadily rising close, high > close, low < close
    import numpy as np
    n = 100
    close = pd.Series(np.linspace(100, 130, n))
    high = close * 1.01
    low = close * 0.99
    volume = pd.Series([1_000_000] * n)
    return pd.DataFrame({"close": close, "high": high, "low": low, "volume": volume})

def test_bullish_trend_positive_score(analyzer, bullish_bars):
    signal = analyzer.analyze(bullish_bars, "TEST", "1Day")
    assert signal.score > 0, f"Expected positive score for bullish trend, got {signal.score}"
    assert signal.trend == "bullish"

def test_confidence_range(analyzer, bullish_bars):
    signal = analyzer.analyze(bullish_bars, "TEST", "1Day")
    assert 0.0 <= signal.confidence <= 1.0
```

**Sample test for risk manager:**
```python
# tests/unit/test_risk_manager.py
import pytest
from src.risk.manager import RiskManager

@pytest.fixture
def risk_mgr():
    config = {
        "risk": {
            "max_position_pct": 10,
            "max_exposure_pct": 60,
            "max_positions": 8,
            "daily_loss_limit_pct": 2,
            "kill_switch_pct": 3,
            "max_drawdown_pct": 10,
            "min_risk_reward": 1.5,
            "max_sector_pct": 30,
            "max_same_sector_same_direction": 3,
        },
        "entry_filters": {"min_adx": 15},
    }
    mgr = RiskManager(config)
    mgr.update_portfolio(
        {"equity": 100_000, "cash": 50_000, "last_equity": 100_000},
        [],
    )
    return mgr

def test_kill_switch_rejects_trade(risk_mgr):
    risk_mgr.kill_switch_active = True
    result = risk_mgr.assess_trade("AAPL", "buy", 150.0)
    assert not result.approved
    assert "Kill switch" in result.reason

def test_binary_event_rejected(risk_mgr):
    result = risk_mgr.assess_trade("AAPL", "buy", 150.0, catalyst_flag="binary_event")
    assert not result.approved
    assert "Binary event" in result.reason

def test_approved_trade_has_qty(risk_mgr):
    result = risk_mgr.assess_trade(
        "AAPL", "buy", 150.0,
        stop_loss_price=140.0, take_profit_price=170.0,
        adx=25,
    )
    assert result.approved
    assert result.suggested_qty > 0
```

## Quality Tooling Gaps

| Tool | Status | Recommendation |
|------|--------|----------------|
| Test framework | Missing | Add `pytest` + `pytest-cov` to `requirements.txt` |
| Linter | Missing | Add `ruff` for fast linting |
| Formatter | Missing | Add `black` for consistent formatting |
| Type checker | Missing | Add `mypy` or `pyright` for static type checking |
| Import sorter | Missing | `ruff` or `isort` |
| Pre-commit hooks | Missing | Add `.pre-commit-config.yaml` |
| CI pipeline | Missing | No GitHub Actions or other CI |

---

*Testing analysis: 2026-03-30*
