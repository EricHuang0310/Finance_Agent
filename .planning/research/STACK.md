# Technology Stack: Trading Desk Role Additions

**Project:** Finance Agent Team v2 -- New Roles Milestone
**Researched:** 2026-03-30

## Recommended Stack

No new technology is required for adding trading desk roles. All new roles operate within the existing Claude Code Agent Teams framework using the established `shared_state/` JSON communication pattern.

### Core Framework (No Changes)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.11+ | Agent task functions and data processing | Existing stack, no reason to change |
| Claude Code Agent Teams | Current | TeamCreate/SendMessage for teammate agents | Already proven in debate pipeline |
| Alpaca API (alpaca-py) | Current | Market data + order execution | Existing broker integration |

### Model Tier Assignments for New Roles

| Role | Model | Monthly Est. Cost Impact | Rationale |
|------|-------|--------------------------|-----------|
| CIO / Head of Trading | Opus | High (~$2-5/run) | Highest-stakes strategic decision; needs deepest reasoning |
| Macro Strategist | Sonnet | Medium (~$0.50-1/run) | Cross-asset synthesis; strong analytical reasoning needed |
| EOD Review Analyst | Sonnet | Medium (~$0.50-1/run) | P&L attribution requires connecting multiple data points |
| Portfolio Strategist | Sonnet | Medium (~$0.50-1/run) | Cross-position correlation reasoning |
| Compliance Officer | Haiku | Low (~$0.05-0.10/run) | Rule-based checks, minimal reasoning |
| Morning Brief Coordinator | Sonnet | Medium (~$0.50-1/run) | Information synthesis |
| Execution Strategist | Haiku | Low (~$0.05-0.10/run) | Primarily rule-based order strategy |
| Sector/Thematic Specialist | Sonnet | Medium (~$0.50-1/run) | Domain reasoning per symbol |

**Estimated total cost increase per daily run (Phase 1 roles only: CIO + Macro + EOD):** $3-7 additional.

### Data Sources for New Roles

| Data Need | Source | New Dependency? |
|-----------|--------|-----------------|
| Bond yields (TLT, IEF) | Alpaca bars API | No -- already available via AlpacaClient |
| Dollar index proxy (UUP) | Alpaca bars API | No -- already fetched in market regime |
| VIX level | Alpaca bars API (VIXY proxy) or yfinance | No -- already used in regime detection |
| Sector ETF performance | Alpaca bars API (XLK, XLF, XLE, etc.) | No -- standard Alpaca symbols |
| Economic calendar | WebSearch or external API | Yes -- MINOR: could use free APIs (FRED, Trading Economics) or LLM knowledge |
| Overnight futures data | Not available via Alpaca free tier | Yes -- MINOR: could approximate from pre-market movers |
| Portfolio correlation matrix | pandas/numpy computation from existing bar data | No -- computation only |

### Supporting Libraries (Potentially New)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| fredapi | Latest | FRED economic data (yields, employment, GDP) | If Macro Strategist needs authoritative economic data beyond what Alpaca provides |
| scipy | Latest | Correlation matrix computation for Portfolio Strategist | If numpy's corrcoef is insufficient for rolling correlation windows |

**Neither is mandatory for Phase 1.** The Macro Strategist can start with Alpaca-available cross-asset data (SPY, TLT, UUP, GLD, VIX proxy) and LLM reasoning. FRED integration can be added if the macro outlook needs more depth.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| CIO model tier | Opus | Sonnet | CIO makes the highest-stakes daily decision (trade or not). Downgrading saves ~$1.50/run but risks lower decision quality on the most impactful call. Start with Opus, downgrade if ROI is negative. |
| Macro data source | Alpaca cross-asset bars | Bloomberg Terminal API | Cost prohibitive for a personal/small trading system. Alpaca bars for TLT/UUP/GLD provide sufficient macro signal for a momentum system. |
| Compliance implementation | Haiku subagent | Pure Python code module | Subagent approach allows adding new rules via prompt rather than code changes. However, if compliance stays simple (wash sales, PDT), a code module is equally valid and cheaper. |
| Economic calendar | LLM knowledge + WebSearch | Paid API (Trading Economics, Quandl) | For a daily one-shot system, the LLM can identify major upcoming events (FOMC, NFP, CPI) from its training data and a quick web search. A paid API adds recurring cost for marginal accuracy improvement. |

## Installation

```bash
# No new core dependencies needed for Phase 1
# Existing requirements.txt covers all needs

# Optional: if adding FRED data for Macro Strategist
pip install fredapi

# Optional: if adding scipy for Portfolio Strategist correlation
pip install scipy
```

## Sources

- Existing system: `requirements.txt`, `config/settings.yaml`
- [Alpaca API documentation](https://docs.alpaca.markets/) -- available data endpoints
- Claude API pricing for model tier cost estimates (training data, MEDIUM confidence on exact numbers)
