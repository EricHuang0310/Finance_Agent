# Codebase Concerns

**Analysis Date:** 2026-03-30

## Tech Debt

**No Test Suite Whatsoever:**
- Issue: Zero automated tests exist in the project. `CLAUDE.md` explicitly states "There are no automated tests, linter, or formatter configured." For a system that executes real financial trades, this is a critical gap.
- Files: All files under `src/`
- Impact: Any refactoring or feature addition risks breaking trading logic silently. Regression in scoring, risk management, or order execution could cause financial loss.
- Fix approach: Add pytest with at minimum unit tests for `src/analysis/technical.py` (scoring logic), `src/risk/manager.py` (position sizing, kill switch), `src/orchestrator.py` (decision engine composite scoring), and `src/analysis/position_reviewer.py` (exit signal logic). Target the pure-computation methods first (no API mocking needed).

**No Linter or Formatter:**
- Issue: No black, ruff, isort, or any linting/formatting tool is configured. No `pyproject.toml`, no `setup.cfg`, no pre-commit hooks.
- Files: Project root (missing `pyproject.toml`, `.pre-commit-config.yaml`)
- Impact: Code style inconsistencies accumulate over time. No static analysis catches bugs before runtime.
- Fix approach: Add `pyproject.toml` with black + ruff + isort config. Add pre-commit hooks.

**Orchestrator God Object (1021 lines):**
- Issue: `TradingOrchestrator` class handles market analysis, technical analysis, sentiment dispatch, position exit review, risk management dispatch, decision engine scoring, trade execution, regime detection, bar caching, state persistence, and trade logging all in one class.
- Files: `src/orchestrator.py`
- Impact: Difficult to test individual concerns. Changes to one phase risk breaking others. The `generate_trade_plan` method alone is ~130 lines with a nested `_score_symbol` closure.
- Fix approach: Extract decision engine into `src/decision/engine.py`, extract execution into `src/execution/executor.py`, extract regime detection into `src/analysis/regime.py`. The orchestrator should only coordinate, not implement.

**Duplicated Exit Execution Logic:**
- Issue: Position closing logic exists in both `src/agents_launcher.py:task_execute_exits()` (lines 119-169) and `src/orchestrator.py:execute_exits()` (lines 441-489). They use different closing mechanisms: the launcher uses `client.close_position()` (preferred), the orchestrator uses `client.place_market_order()` with manual side calculation.
- Files: `src/agents_launcher.py`, `src/orchestrator.py`
- Impact: Behavior diverges between standalone and Agent Teams modes. The orchestrator path does not cancel pending orders before closing (the `close_position` API does).
- Fix approach: Consolidate into a single `execute_exit()` function in a shared module, always using `close_position()`.

**Duplicated `_LazyStateDir` Class:**
- Issue: The `_LazyStateDir` proxy class is copy-pasted in both `src/debate/helpers.py` (lines 21-31) and `src/memory/reflection.py` (lines 16-27).
- Files: `src/debate/helpers.py`, `src/memory/reflection.py`
- Impact: Any fix to the lazy resolution pattern must be applied in two places.
- Fix approach: Move `_LazyStateDir` into `src/state_dir.py` and export a singleton `STATE_DIR` from there.

**Global Mutable Singleton Pattern:**
- Issue: `src/agents_launcher.py` uses a module-level `_orchestrator_instance` global (line 43) with lazy initialization. This pattern makes testing impossible and creates hidden coupling.
- Files: `src/agents_launcher.py` (lines 43-51)
- Impact: Cannot run parallel tests, cannot inject mock orchestrator, state leaks between calls.
- Fix approach: Use dependency injection or a factory function that accepts configuration.

## Known Bugs

**Peak Equity Tracking is Per-Session Only:**
- Symptoms: `RiskManager.peak_equity` (line 68 in `src/risk/manager.py`) is set to `max(last_equity, self.equity)` on each `update_portfolio()` call, but `last_equity` is Alpaca's previous-day close. If equity rose significantly intra-day and then dropped, the drawdown calculation only sees the current day's range, not the true peak.
- Files: `src/risk/manager.py` (lines 67-71)
- Trigger: Multi-day holding with intra-day peak followed by decline.
- Workaround: The kill switch at 3% daily loss provides a secondary safety net.

**Trade Log Race Condition:**
- Symptoms: `_log_trade()` in `src/orchestrator.py` (lines 983-1007) reads the entire `trade_log.json`, appends, and writes back. If two agent processes run concurrently (Agent Teams mode), they can overwrite each other's entries.
- Files: `src/orchestrator.py` (lines 983-1007)
- Trigger: Concurrent execution of exit orders and new entry orders in Agent Teams mode.
- Workaround: In practice, exits run before entries in the pipeline, so overlap is rare but possible.

**Memory Corruption Silently Ignored:**
- Symptoms: `SituationMemory.load()` in `src/memory/situation_memory.py` (lines 108-121) catches `json.JSONDecodeError` and `KeyError` with `pass`, silently starting fresh. Corrupted memory files lose all learned lessons without notification.
- Files: `src/memory/situation_memory.py` (lines 119-120)
- Trigger: Disk full, concurrent writes, or interrupted save.
- Workaround: None. Data is silently lost.

## Security Considerations

**API Credentials Stored as Instance Attributes:**
- Risk: `AlpacaClient` stores `self._api_key` and `self._api_secret` as plain-text instance attributes (line 35 in `src/alpaca_client.py`). These persist in memory and could be exposed via debugging tools, crash dumps, or serialization.
- Files: `src/alpaca_client.py` (lines 34-35)
- Current mitigation: Credentials loaded from `config/.env`, which is in `.gitignore`.
- Recommendations: Avoid storing secrets as instance attributes. Pass them directly to SDK constructors only. If needed later (for `NewsClient`), re-read from environment.

**Telegram Bot Token in Memory:**
- Risk: `TelegramNotifier` stores `self.bot_token` as a plain string attribute (line 31 in `src/notifications/telegram.py`).
- Files: `src/notifications/telegram.py` (line 31)
- Current mitigation: `.env` is gitignored.
- Recommendations: Read from env at send-time instead of caching.

**No Input Validation on Config:**
- Risk: `config/settings.yaml` values are used directly without validation. Setting `max_positions: -1` or `kill_switch_pct: 0` could disable safety mechanisms. Setting `max_position_pct: 200` would allow 200% exposure per position.
- Files: `src/risk/manager.py` (lines 31-40), `config/settings.yaml`
- Current mitigation: None. Config is trusted.
- Recommendations: Add a config validation layer at startup (e.g., using pydantic or manual bounds checking) that rejects nonsensical values.

**`max_positions: 100` in Config:**
- Risk: The current `config/settings.yaml` sets `max_positions: 100`, which is extremely high for a paper/live trading account. This effectively disables the position limit safety check.
- Files: `config/settings.yaml` (line 80)
- Current mitigation: Other limits (max_exposure_pct, max_position_pct) still apply.
- Recommendations: Reduce to a sensible default (8-15) or require explicit override.

## Performance Bottlenecks

**BM25 Index Rebuilt on Every Add:**
- Problem: `SituationMemory.add()` calls `_rebuild_index()` after every single entry, which re-tokenizes all documents and creates a new BM25Okapi instance.
- Files: `src/memory/situation_memory.py` (lines 51-56)
- Cause: No incremental index update; full rebuild every time.
- Improvement path: Use `add_batch()` for multiple entries. Or switch to an incremental index. At 500 entries max, this is acceptable but wastes CPU on each reflection save.

**Sequential Symbol Processing:**
- Problem: Market analyst, technical analyst, and sentiment analyst each iterate over watchlist symbols sequentially. With 20+ symbols and API rate limits, this creates a ~2-3 minute pipeline.
- Files: `src/orchestrator.py` (lines 141-173, 337-351), `src/analysis/sentiment.py`
- Cause: Simple for-loop over symbols with synchronous API calls.
- Improvement path: Use `concurrent.futures.ThreadPoolExecutor` for parallel API calls within each analyst phase. Respect API rate limits with a semaphore.

**Fundamentals Analyzer 2-Second Delays:**
- Problem: `_REQUEST_DELAY = 2.0` seconds between each yfinance call, with up to 3 retries per symbol. For 3 debate candidates, this is a minimum 6-second delay.
- Files: `src/analysis/fundamentals.py` (line 28)
- Cause: Conservative rate limiting for yfinance.
- Improvement path: Use disk cache (already implemented via `fundamentals_cache.json`) to skip repeat calls within the same day. Reduce delay to 1s with retry-on-429.

## Fragile Areas

**Decision Engine Scoring Logic:**
- Files: `src/orchestrator.py` (lines 604-712, the `_score_symbol` closure)
- Why fragile: 130-line nested function with confidence weighting, regime adjustment, signal alignment detection, catalyst detection, and sector lookup all interleaved. No unit tests protect any of this logic.
- Safe modification: Extract `_score_symbol` into a standalone function in a separate module with explicit inputs/outputs. Write parameterized tests for each scoring path.
- Test coverage: Zero.

**Shared State File-Based Communication:**
- Files: `src/state_dir.py`, all modules reading from `shared_state/YYYY-MM-DD/`
- Why fragile: Agents communicate via JSON files on disk with no locking, no schema validation, and no versioning. If a producer writes a partial file while a consumer reads, the consumer gets corrupted data (caught as JSONDecodeError and silently swallowed).
- Safe modification: Use atomic writes (write to temp file, then rename). Add JSON schema validation for each state file type.
- Test coverage: Zero.

**Position Reviewer Hard Stop Rules:**
- Files: `src/analysis/position_reviewer.py` (lines 94-200+)
- Why fragile: Complex multi-factor exit scoring with hard stops, soft scoring, ATR gradient tiers, partial close logic, and give-back rules. Over 500 lines with intricate conditional logic. A single wrong comparison operator could cause premature exits or hold losers.
- Safe modification: Each hard stop rule should be an isolated, tested function. Currently they are all in one `_check_hard_stops` method.
- Test coverage: Zero.

## Scaling Limits

**File-Based State Store:**
- Current capacity: Works fine for single-user, single-run pipelines.
- Limit: Concurrent agent processes reading/writing the same JSON files will corrupt data. No file locking mechanism.
- Scaling path: Replace with SQLite (for single-machine) or Redis (for distributed) if scaling to concurrent pipeline runs.

**Memory Bank Size:**
- Current capacity: 500 entries per bank, 5 banks = 2,500 total entries.
- Limit: BM25 index rebuild time grows linearly. At 500 entries with tokenization, each rebuild is O(n) but still fast (~10ms). Acceptable for now.
- Scaling path: If max_memories grows beyond ~5000, consider pre-built index persistence or switch to a vector DB.

## Dependencies at Risk

**yfinance (Unofficial Yahoo Finance API):**
- Risk: yfinance scrapes Yahoo Finance. Yahoo has historically broken this by changing their endpoints. The library can stop working without notice.
- Impact: Fundamentals analysis (`src/analysis/fundamentals.py`), VIX data for regime detection (`src/orchestrator.py`), and earnings date lookup (`src/analysis/sentiment.py`) all fail.
- Migration plan: The code already handles `ImportError` gracefully with `_HAS_YFINANCE` flags. Could replace with Alpha Vantage, Polygon.io, or Finnhub APIs for fundamentals.

**vaderSentiment (Rule-Based NLP):**
- Risk: VADER is a simple rule-based sentiment analyzer from 2014, not trained on financial text. It misclassifies financial jargon (e.g., "short" as negative, "bearish outlook" not weighted properly).
- Impact: Sentiment scores may be inaccurate for financial headlines, though the weight is only 0.15 in composite scoring.
- Migration plan: Replace with FinBERT or a financial-domain LLM-based sentiment scorer for more accurate results.

**No Pinned Versions:**
- Risk: `requirements.txt` uses `>=` for all dependencies. A breaking update to `alpaca-py`, `pandas`, or `yfinance` could silently break the system.
- Impact: Non-reproducible builds. `pip install -r requirements.txt` on different days may produce different behavior.
- Migration plan: Pin exact versions with `pip freeze > requirements.txt` or use `poetry.lock` / `pip-tools`.

## Missing Critical Features

**No Order Confirmation/Fill Tracking:**
- Problem: After placing an order, the system only logs the order ID and initial status. It never checks if the order was filled, partially filled, or rejected by the exchange.
- Blocks: Cannot calculate actual fill prices, cannot detect stuck orders, cannot reconcile portfolio state.
- Files: `src/orchestrator.py` (lines 822-844), `src/agents_launcher.py` (lines 219-236)

**No Retry Logic for Order Placement:**
- Problem: If an order submission fails due to a transient API error, the system prints an error and moves on. No retry mechanism exists.
- Blocks: Transient network issues cause missed trades.
- Files: `src/orchestrator.py` (line 855), `src/agents_launcher.py` (line 250)

**No Graceful Shutdown:**
- Problem: If the pipeline is interrupted mid-execution (Ctrl+C, crash), partially executed trades are not rolled back or logged consistently.
- Blocks: Manual intervention required to reconcile state after crashes.

## Test Coverage Gaps

**All Business Logic is Untested:**
- What's not tested: Every module in `src/` has zero test coverage.
- Files: All files under `src/`
- Risk: Financial trading logic changes cannot be validated without manual testing against live/paper APIs.
- Priority: **Critical** - The following should be tested first (ordered by risk):
  1. `src/risk/manager.py` - Kill switch, position sizing, exposure limits
  2. `src/orchestrator.py:generate_trade_plan()` - Composite scoring, regime adjustment
  3. `src/analysis/position_reviewer.py` - Exit signal scoring, hard stop rules
  4. `src/analysis/technical.py` - Indicator calculations, score computation
  5. `src/memory/situation_memory.py` - BM25 search, persistence, pruning

## Error Handling Anti-Patterns

**Silent Exception Swallowing:**
- Issue: At least 12 locations across the codebase catch `except Exception:` and do nothing (`pass`) or return a default value. This masks bugs and makes debugging impossible.
- Files:
  - `src/orchestrator.py` lines 233, 257, 286, 671, 788 - Regime detection, sector lookup, market data reads
  - `src/alpaca_client.py` line 166 - Cancel orders silently fails
  - `src/analysis/screener.py` lines 83, 90 - Discovery endpoints silently fail
  - `src/analysis/sentiment.py` lines 105, 188 - Earnings date, age calculation
  - `src/analysis/position_reviewer.py` line 514 - Unknown failure
  - `src/analysis/technical.py` line 256 - ADX calculation
- Impact: When things go wrong, there is no logging, no alerting, and no way to diagnose the failure after the fact.
- Fix approach: Replace bare `except Exception: pass` with `except Exception as e: logger.warning(...)` at minimum. Use Python's `logging` module instead of `print()` throughout.

**`print()` Instead of `logging`:**
- Issue: The entire codebase uses `print()` for output, including error messages, warnings, and debug info. No log levels, no log files, no structured logging.
- Files: Every file in `src/`
- Impact: Cannot filter by severity, cannot redirect to files, cannot integrate with monitoring tools. In Agent Teams mode, print output from subprocesses may be lost.
- Fix approach: Replace `print()` with `logging` module. Use `logging.WARNING` for recoverable errors, `logging.ERROR` for failures, `logging.INFO` for pipeline progress.

---

*Concerns audit: 2026-03-30*
