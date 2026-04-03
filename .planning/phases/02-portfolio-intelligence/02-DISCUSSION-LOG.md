# Phase 2: Portfolio Intelligence - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.

**Date:** 2026-04-03
**Phase:** 02-portfolio-intelligence
**Areas discussed:** Correlation Method, Sizing Adjustments, Trade Journal Schema, Pipeline Integration

---

## Correlation Method

### Computation Approach

| Option | Description | Selected |
|--------|-------------|----------|
| Rolling price correlation | 20-day Pearson on daily returns. Simple, proven. | |
| Sector + correlation hybrid | Price correlation + sector overlap check. | |
| You decide | Claude determines best approach. | x |

**User's choice:** You decide

### Lookback Window

| Option | Description | Selected |
|--------|-------------|----------|
| 20 trading days | ~1 month, matches screener lookback. | x |
| 60 trading days | ~3 months, more stable. | |
| You decide | Claude determines. | |

**User's choice:** 20 trading days

---

## Sizing Adjustments

### Action on Correlation

| Option | Description | Selected |
|--------|-------------|----------|
| Reduce qty of new position | Halve qty when >0.7 correlation. | |
| Reject new position entirely | Block trade if >0.7. | |
| Reduce + warn | Halve qty AND flag for monitoring. | |
| You decide | Claude determines strategy. | x |

**User's choice:** You decide

### Existing Position Rebalancing

| Option | Description | Selected |
|--------|-------------|----------|
| No, only gate new entries | Simpler scope. | |
| Yes, suggest partial closes | Suggest reducing if too concentrated. | x |

**User's choice:** Yes, suggest partial closes

---

## Trade Journal Schema

### Write Timing

| Option | Description | Selected |
|--------|-------------|----------|
| On fill + on close | Entry thesis at fill, exit data at close. | x |
| On close only | Single write on completion. | |
| You decide | Claude determines. | |

**User's choice:** On fill + on close

### Outcome Tagging

| Option | Description | Selected |
|--------|-------------|----------|
| Win/Loss/Scratch + R-multiple | Categorical + risk-adjusted metric. | x |
| Simple P&L only | Dollar and percentage P&L. | |
| You decide | Claude determines. | |

**User's choice:** Win/Loss/Scratch + R-multiple

---

## Pipeline Integration

### Placement

| Option | Description | Selected |
|--------|-------------|----------|
| After Risk Manager, before Executor | Risk approves first, then portfolio optimizes. | |
| Before Risk Manager | Portfolio context informs risk. | |
| You decide | Claude determines. | x |

**User's choice:** You decide

### Agent Type

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: code + LLM | Quantitative correlation + LLM portfolio narrative. Sonnet. | x |
| Code only (subagent) | Pure quantitative. Cheaper. | |
| You decide | Claude determines. | |

**User's choice:** Hybrid: code + LLM

---

## Claude's Discretion

- Correlation method, threshold, and flagging logic
- Sizing adjustment strategy
- Pipeline placement
- portfolio_construction.json schema
- Trade journal storage format
- Partial close integration with Position Reviewer

## Deferred Ideas

None
