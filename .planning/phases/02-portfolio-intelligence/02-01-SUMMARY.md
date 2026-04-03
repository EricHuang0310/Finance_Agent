---
phase: 02-portfolio-intelligence
plan: 01
subsystem: portfolio
tags: [pandas, correlation, pearson, portfolio-optimization, position-sizing]

# Dependency graph
requires:
  - phase: 01-strategic-oversight-agent-teams-foundation
    provides: "task_*() function pattern, RiskAssessment dataclass, save_state_atomic, _bar_cache, agents_launcher.py structure"
provides:
  - "PortfolioStrategist class with correlation matrix, sizing adjustments, partial close suggestions"
  - "task_portfolio_strategist() function in agents_launcher.py"
  - "portfolio: config section in settings.yaml"
  - "agents/risk_mgmt/portfolio_strategist.md agent spec (Chinese, Sonnet tier)"
affects: [02-02, 02-03, 03-portfolio-integration, pipeline-placement]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Hybrid agent: code computes correlation + LLM reasons about diversification", "Graduated response: reject at 0.9, reduce at 0.7", "Immutable dict pattern: shallow copy with {**trade}"]

key-files:
  created:
    - src/portfolio/__init__.py
    - src/portfolio/strategist.py
    - agents/risk_mgmt/portfolio_strategist.md
  modified:
    - config/settings.yaml
    - src/agents_launcher.py

key-decisions:
  - "Pearson correlation on daily returns (not raw prices) for stable correlation measurement"
  - "Same-direction positions penalised; opposite-direction treated as hedges (skipped)"
  - "Partial close targets the smaller position in a correlated pair"
  - "task_portfolio_strategist placed after task_risk_manager in agents_launcher.py"

patterns-established:
  - "Portfolio module pattern: src/portfolio/ package with strategist.py"
  - "Graduated correlation response: reject >= 0.9, reduce 30% at >= 0.7, pass < 0.7"
  - "Partial close suggestions compatible with exit_candidates format (source=portfolio_strategist)"

requirements-completed: [PORT-01, PORT-02]

# Metrics
duration: 195s
completed: 2026-04-03
---

# Phase 2 Plan 01: Portfolio Strategist Core Summary

**PortfolioStrategist class with 20-day Pearson correlation matrix, graduated sizing adjustments (reject at 0.9, reduce 30% at 0.7), and partial close suggestions for concentrated portfolios**

## Performance

- **Duration:** 195s
- **Started:** 2026-04-03T02:04:34Z
- **Completed:** 2026-04-03T02:07:49Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- PortfolioStrategist class with 4 core methods: compute_correlation_matrix, adjust_sizing, suggest_partial_closes, build_result
- task_portfolio_strategist() function integrated into agents_launcher.py with graceful degradation
- Portfolio config section with 7 configurable thresholds in settings.yaml
- Chinese agent spec for Portfolio Strategist (Sonnet tier) following existing pattern

## Task Commits

Each task was committed atomically:

1. **Task 1: Create PortfolioStrategist class and config** - `9aa8ea5` (feat)
2. **Task 2: Create task_portfolio_strategist() in agents_launcher.py** - `da63b6b` (feat)

## Files Created/Modified
- `src/portfolio/__init__.py` - Empty package marker
- `src/portfolio/strategist.py` - PortfolioStrategist class with correlation + sizing logic
- `agents/risk_mgmt/portfolio_strategist.md` - Agent spec in Chinese (Sonnet tier)
- `config/settings.yaml` - Added portfolio: section with 7 keys + portfolio-strategist model tier
- `src/agents_launcher.py` - Added task_portfolio_strategist() function after task_risk_manager

## Decisions Made
- Used Pearson correlation on daily returns (pct_change) rather than raw close prices for more stable correlation measurement
- Same-direction positions are penalised for high correlation; opposite-direction positions are treated as hedges and skipped from penalty
- Partial close suggestions target the smaller position in a correlated pair (by market_value)
- task_portfolio_strategist placed after task_risk_manager in code ordering; pipeline integration (run_full_pipeline) deferred to a later plan

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## Known Stubs

None - all methods are fully implemented with real logic. Pipeline integration (inserting into run_full_pipeline) is intentionally deferred to a later plan per the plan scope.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PortfolioStrategist is ready for pipeline integration (inserting task_portfolio_strategist into run_full_pipeline)
- Partial close suggestions output is compatible with exit_candidates format for executor integration
- Trade journal (MEM-02) can be built independently as the next plan

---
*Phase: 02-portfolio-intelligence*
*Completed: 2026-04-03*
