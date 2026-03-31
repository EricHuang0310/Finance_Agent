# Phase 1: Strategic Oversight & Agent Teams Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md -- this log preserves the alternatives considered.

**Date:** 2026-03-31
**Phase:** 01-strategic-oversight-agent-teams-foundation
**Areas discussed:** Team Topology, CIO Behavior Design, Agent Spec Format, Pipeline Orchestration

---

## Team Topology

### Team Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Single team, CIO as Lead | One TeamCreate per run. CIO orchestrates all phases. | x |
| Single team, Human as Lead | Human remains Lead, spawns CIO as teammate. | |
| You decide | Claude picks topology. | |

**User's choice:** Single team, CIO as Lead
**Notes:** CIO agent acts as Lead, human monitors.

### Teammate Lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| Phased spawning | Spawn 3-5 per phase group, shut down before next. | x |
| All at once | Spawn all at pipeline start. | |
| You decide | Claude determines timing. | |

**User's choice:** Phased spawning
**Notes:** Keeps active count low, saves tokens.

### Standalone Fallback

| Option | Description | Selected |
|--------|-------------|----------|
| Keep as fallback | Agent Teams default, standalone for quick tests. | x |
| Remove standalone | Agent Teams only. | |

**User's choice:** Keep as fallback

---

## CIO Behavior Design

### CIO Authority Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Narrow: stance + budget only | Sets stance and risk_budget_multiplier. No individual trade veto. | x |
| Broad: stance + individual veto | Also rejects specific candidates before Risk Manager. | |
| Advisory only | Produces outlook but downstream can ignore. | |

**User's choice:** Narrow: stance + budget only
**Notes:** Prevents compound rejection problem with Risk Manager.

### CIO Input Data

| Option | Description | Selected |
|--------|-------------|----------|
| Macro + regime + memory | Reads macro_outlook + regime + yesterday's EOD review. | x |
| Macro only | Only macro_outlook. | |
| You decide | Claude determines. | |

**User's choice:** Macro + regime + memory

### CIO Calibration

| Option | Description | Selected |
|--------|-------------|----------|
| Shadow mode first | 2 weeks generating directives, pipeline ignores. | |
| Live from day 1 | Directive takes effect immediately. | x |
| You decide | Claude determines. | |

**User's choice:** Live from day 1
**Notes:** Faster feedback. Prompt adjusted if stance skews after 2 weeks.

---

## Agent Spec Format

### Language

| Option | Description | Selected |
|--------|-------------|----------|
| Keep Chinese | All specs in Chinese for consistency. | x |
| Migrate to English | Convert all 12 + write new in English. | |
| Mixed | Keep existing Chinese, new in English. | |

**User's choice:** Keep Chinese

### Spec Location

| Option | Description | Selected |
|--------|-------------|----------|
| Keep agents/ dir | Existing directory structure. | x |
| Move to .claude/agents/ | Claude Code native directory. | |
| Both | Thin .claude/agents/ refs agents/. | |

**User's choice:** Keep agents/ dir

### Communication Pattern

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid | SendMessage for coordination, JSON for data. | x |
| SendMessage only | All via messages. | |
| You decide | Claude determines. | |

**User's choice:** Hybrid

---

## Pipeline Orchestration

### Pipeline Flow

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-market layer first | Macro -> CIO -> existing pipeline -> EOD Review. | x |
| CIO at every gate | CIO reviews at multiple checkpoints. | |
| You decide | Claude determines. | |

**User's choice:** Pre-market layer first

### Parallelization

| Option | Description | Selected |
|--------|-------------|----------|
| Research-validated groups | Macro parallel, Analysts parallel, Post-exec parallel. | x |
| Maximum parallel | Everything possible in parallel. | |
| You decide | Claude determines. | |

**User's choice:** Research-validated groups

### Error Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Graceful degradation | Only Risk Manager failure is hard stop. | x |
| Fail fast | Any failure stops pipeline. | |
| You decide | Claude determines. | |

**User's choice:** Graceful degradation

---

## Claude's Discretion

- Model tier assignment per specific agent
- JSON schemas for new state files
- CIO risk_budget_multiplier wiring into Decision Engine
- Memory corruption and race condition fix approach
- EOD confidence decay implementation

## Deferred Ideas

None
