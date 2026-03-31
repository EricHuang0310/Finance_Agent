# Coding Conventions

**Analysis Date:** 2026-03-30

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python modules: `alpaca_client.py`, `situation_memory.py`, `position_reviewer.py`
- Subdirectory `__init__.py` files exist but are empty (used only as package markers)
- Configuration files: `settings.yaml`, `.env.example`

**Classes:**
- Use `PascalCase`: `TradingOrchestrator`, `AlpacaClient`, `TechnicalAnalyzer`, `SituationMemory`, `RiskManager`
- Analyzer/Manager suffix pattern for domain modules: `TechnicalAnalyzer`, `SentimentAnalyzer`, `FundamentalsAnalyzer`, `RiskManager`, `PositionReviewer`

**Functions:**
- Use `snake_case` for all functions and methods
- Public methods: `analyze()`, `screen_all()`, `assess_trade()`, `review_position()`
- Private methods: prefix with underscore `_compute_score()`, `_rsi()`, `_get_bars()`, `_detect_catalysts()`
- Task functions (called by agent teams): `task_*()` prefix: `task_symbol_screener()`, `task_prepare_debate_context()`, `task_save_reflections()`
- Orchestrator pipeline methods: `run_*()` prefix: `run_market_analyst()`, `run_technical_analyst()`, `run_risk_manager()`

**Variables:**
- Use `snake_case`: `exit_threshold`, `max_position_pct`, `regime_confidence`
- Config shortcuts stored as `self.<setting>` in `__init__`: e.g., `self.max_positions`, `self.min_price`
- Constants: `UPPER_SNAKE_CASE` for module-level constants: `ET`, `STATE_DIR`, `LOG_DIR`, `MEMORY_DIR`
- Private module-level constants with underscore prefix: `_HAS_YFINANCE`, `_HAS_TA`, `_SECTOR_AVG_PE`, `_REQUEST_DELAY`

**Dataclasses:**
- Use `PascalCase` with descriptive domain names: `TechnicalSignal`, `RiskAssessment`, `ExitSignal`, `FundamentalSignal`

## Code Style

**Formatting:**
- No formatter configured (no black, ruff, or autopep8)
- Indentation: 4 spaces (standard Python)
- Line length: generally under 120 characters, some lines exceed this
- String quotes: double quotes `"` used consistently throughout

**Linting:**
- No linter configured (no flake8, ruff, pylint, or mypy)
- Type hints are used on most function signatures but not universally enforced
- No static type checking

**Docstrings:**
- Triple-quoted docstrings on all classes and most public methods
- Module-level docstrings present on all `.py` files describing purpose
- Format: single-line summary for simple methods, multi-line with description for complex ones
- Example from `src/alpaca_client.py`:
  ```python
  def get_stock_bars(self, symbol: str, timeframe: str = "1Day", lookback_days: int = 90):
      """Fetch historical stock bars as a DataFrame."""
  ```
- Example from `src/risk/manager.py`:
  ```python
  def assess_trade(self, symbol: str, side: str, ...) -> RiskAssessment:
      """Assess whether a trade meets risk constraints."""
  ```

## Import Organization

**Order (observed pattern):**
1. Standard library imports (`json`, `os`, `math`, `re`, `datetime`, `pathlib`, `typing`)
2. Third-party imports (`pandas`, `numpy`, `yaml`, `httpx`, `vaderSentiment`, `rank_bm25`, `yfinance`)
3. Local imports (`from src.alpaca_client import AlpacaClient`, `from src.state_dir import get_state_dir`)

**No import sorting tool configured.** Imports are generally organized but not strictly enforced.

**Path Aliases:**
- None. All imports use full dotted paths: `from src.analysis.technical import TechnicalAnalyzer`
- `sys.path.insert(0, ...)` used in `src/agents_launcher.py` to ensure project root is importable

**Conditional imports for optional dependencies:**
```python
try:
    import yfinance as yf
    _HAS_YFINANCE = True
except ImportError:
    _HAS_YFINANCE = False
```
This pattern is used in `src/analysis/technical.py`, `src/analysis/sentiment.py`, `src/analysis/fundamentals.py`, and `src/orchestrator.py`.

## Error Handling

**Patterns:**

1. **Broad try/except with print + fallback** (most common):
   ```python
   try:
       bars = self._get_bars(symbol, "stock")
       # ... process
   except Exception as e:
       print(f"  {symbol}: Error - {e}")
   ```
   Used extensively in `src/orchestrator.py`, `src/analysis/screener.py`, `src/alpaca_client.py`

2. **Silenced exceptions with `pass`:**
   ```python
   except Exception:
       pass  # No open orders, or API doesn't support
   ```
   Used in `src/alpaca_client.py` line 166, `src/memory/situation_memory.py` line 120

3. **ValueError for missing configuration:**
   ```python
   if not api_key or not api_secret:
       raise ValueError("ALPACA_API_KEY and ALPACA_API_SECRET must be set in config/.env")
   ```
   Used in `src/alpaca_client.py` line 29

4. **RuntimeError for operational failures:**
   ```python
   raise RuntimeError(f"Failed to close {symbol}: {e}")
   ```
   Used in `src/alpaca_client.py` line 173

5. **Graceful degradation with defaults:**
   ```python
   return {"regime": "transitional", "regime_confidence": 0.5}
   ```
   Used in `src/orchestrator.py` for regime detection failures

**No custom exception classes defined.** All exceptions use built-in types.

## Logging

**Framework:** `print()` statements exclusively. No `logging` module usage anywhere in the codebase.

**Patterns:**
- Emoji-prefixed status messages throughout: `print(f"  {symbol}: ${latest_close:.2f}")`
- Section headers with box-drawing characters:
  ```python
  print("\n" + "=" * 60)
  print(" AGENT 2: Technical Analyst - Computing Signals")
  print("=" * 60)
  ```
- Comment dividers within classes using Unicode box-drawing:
  ```python
  # ──────────────────────────────────────────────
  # Market Data
  # ──────────────────────────────────────────────
  ```
- Status emoji convention:
  - `checkmark` = success
  - `warning` = warning/degraded
  - `cross` = error/failure
  - Colored circles for sentiment: green = bullish, red = bearish, yellow = neutral

## Configuration

**Approach:** YAML config file + `.env` for secrets

**Configuration loading pattern:**
```python
# In __init__, load YAML and extract sub-dicts
with open(config_path, "r") as f:
    self.config = yaml.safe_load(f)
# Then extract with .get() and defaults
self.max_position_pct = risk_cfg.get("max_position_pct", 10.0) / 100
```

**Key config files:**
- `config/settings.yaml` - All tuneable parameters (watchlist, scoring weights, risk limits, exit rules, debate settings, memory settings)
- `config/.env` - API keys and secrets (Alpaca, Telegram, optional Finnhub/NewsAPI)
- `.env.example` - Template for required environment variables

**Environment variables loaded via:**
```python
from dotenv import load_dotenv
load_dotenv("config/.env")
api_key = os.getenv("ALPACA_API_KEY")
```

## Data Structures

**Dataclasses as DTOs:**
- All analysis results use `@dataclass` with a `to_dict()` method calling `dataclasses.asdict()`:
  - `TechnicalSignal` in `src/analysis/technical.py`
  - `RiskAssessment` in `src/risk/manager.py`
  - `ExitSignal` in `src/analysis/position_reviewer.py`
  - `FundamentalSignal` in `src/analysis/fundamentals.py`
- Dataclasses are NOT frozen (mutable). Fields have defaults where appropriate.

**Dict-based inter-agent communication:**
- Agents communicate via JSON files in `shared_state/YYYY-MM-DD/`
- All outputs serialized as plain dicts via `json.dump()`
- Downstream agents read with `json.load()`

**Return value convention:**
- Analysis methods return `dict` for aggregate results or `@dataclass` for single-symbol results
- Lists of dicts for batch results
- `Optional[T]` return type when data may be unavailable

## Module Design

**Exports:**
- No `__all__` defined in any module
- Empty `__init__.py` files in all packages (`src/`, `src/analysis/`, `src/risk/`, `src/notifications/`, `src/memory/`, `src/debate/`)
- All imports are explicit: `from src.analysis.technical import TechnicalAnalyzer`

**Singleton pattern:**
- `src/agents_launcher.py` uses a module-level singleton for `TradingOrchestrator`:
  ```python
  _orchestrator_instance = None
  def get_orchestrator() -> TradingOrchestrator:
      global _orchestrator_instance
      if _orchestrator_instance is None:
          _orchestrator_instance = TradingOrchestrator()
      return _orchestrator_instance
  ```

**Lazy state directory proxy:**
- Both `src/debate/helpers.py` and `src/memory/reflection.py` use a `_LazyStateDir` class to defer resolution of the daily state directory

## Function Design

**Size:** Most methods are 20-60 lines. `_compute_score` in `src/analysis/technical.py` and `assess_trade` in `src/risk/manager.py` are the longest at ~100 lines.

**Parameters:**
- Use keyword arguments with defaults for optional params
- Config values read from `self.<attr>` set in `__init__`
- Complex methods accept dicts (not typed objects) as inputs when reading from shared state

**Return Values:**
- Dataclasses for single-item results: `TechnicalSignal`, `RiskAssessment`, `ExitSignal`
- Dicts for aggregate/composite results
- `Optional[T]` when data may be unavailable
- Tuples for internal multi-value returns: `tuple[float, float]` from `_compute_score`

---

*Convention analysis: 2026-03-30*
