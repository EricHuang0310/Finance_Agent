# Agent 架構重組 — 進度追蹤

## Phase 1: 目錄結構 & Skills 建立（已完成）

- [x] **Step 1**: 建立新目錄結構
- [x] **Step 2**: 移動 agent spec 檔案到子目錄
- [x] **Step 3**: 撰寫 11 個 skill.md 技能檔
- [x] **Step 4**: 更新 agent spec 內容（加入可用技能引用 + 更新路徑）
- [x] **Step 5**: 重寫 AGENT_TEAMS_PROMPT（反映 teammate/subagent 分類）
- [x] **Step 6**: 更新 CLAUDE.md（架構說明）
- [x] **Step 7**: 驗證所有路徑引用正確

## Phase 2: agents/skills/ 清理 & 引用更新（已完成）

- [x] **Step 8**: 刪除 `agents/skills/` 目錄（已被 `.claude/skills/` 取代）
- [x] **Step 9**: 更新 18 個 agent spec 的技能引用（`../skills/xxx.md` → 文字描述指向 `.claude/skills/`）
- [x] **Step 10**: 更新 `AGENT_TEAMS_PROMPT` 中的 `agents/skills/` 引用
- [x] **Step 11**: 更新 `CLAUDE.md` 架構說明（移除 `agents/skills/`）
- [x] **Step 12**: 驗證（grep 無殘留引用 + `--prompt` 正常輸出）

---

## Phase 3: Code Review 發現的問題

### Critical（需立即修復）

- [x] **Bug-1**: Crypto 訂單 TimeInForce 錯誤 — `src/alpaca_client.py`
  - 新增 `_is_crypto_symbol()` 偵測函數
  - `place_market_order` 和 `place_bracket_order` 自動偵測 crypto → 用 GTC，stock → 用 DAY

- [x] **Bug-2**: `entry_price=None` 會導致 risk manager 崩潰 — `src/orchestrator.py` + `src/agents_launcher.py`
  - `run_risk_manager` 加 None guard，跳過缺少 entry_price 的候選
  - 所有 `entry_price:.2f` 格式化加條件保護

### High（重要邏輯錯誤）

- [x] **Bug-3**: `signal_score` 傳入永遠為 0 — `src/orchestrator.py:473`
  - 改為 `candidate.get("composite_score", 0)`（在 Bug-2 修復時一併修正）
  - `"score"` 不存在於 candidate，永遠返回 0
  - 修復：改為 `candidate.get("composite_score", 0)`

- [x] **Bug-4**: 決策閾值預設值不一致 — `src/orchestrator.py`
  - fallback 從 `0.65` 改為 `0.3`，與 settings.yaml 一致

- [x] **Bug-5**: EMA-200 只用 90 天數據計算 — `src/orchestrator.py` + `src/analysis/technical.py`
  - 技術分析和持倉審查的 `_get_bars` 改為 `lookback_days=300`（~200 交易日）
  - `_compute_score` 在 `num_bars < 200` 時降低 EMA 權重（0.25 → 0.10）
  - 市場分析保持 90 天（90d high/low range 語義不變）

- [x] **Bug-6**: `task_send_report` 傳錯資料結構 — `src/agents_launcher.py`
  - 用 symbol 合併 candidates（有 composite_score）和 risk assessments（有 approved/reason）
  - Telegram 報告現在能正確顯示分數

### Medium（功能缺失 / 品質問題）

- [x] **Bug-7**: Drawdown 保護是死碼 — `src/risk/manager.py`
  - 新增 `peak_equity` / `drawdown_from_peak_pct` 追蹤
  - Drawdown 超過 `max_drawdown_pct` 時觸發 kill switch
  - `get_risk_summary()` 現在回傳 `drawdown_from_peak_pct` 和 `max_drawdown_pct`

- [x] **Bug-8**: Memory 無上限 — `src/memory/situation_memory.py` + `src/orchestrator.py`
  - `SituationMemory` 新增 `max_entries` 參數 + `_prune()` 方法
  - `add()` / `add_batch()` 超過上限時自動刪除最舊記錄
  - Orchestrator 從 `config.memory.max_memories` 傳入上限值

- [x] **Bug-9**: Standalone 模式下單無 Telegram 通知 — `src/orchestrator.py`
  - `execute_trades()` 成功下單後加入 `alert_order_executed()`
  - 失敗時加入 `alert_order_rejected()`，與 Agent Teams 模式一致

- [x] **Bug-10**: Screener 繞過 bar cache — `src/analysis/screener.py` + `src/orchestrator.py`
  - Screener 新增 `bars_getter` 參數 + `_get_bars()` 方法
  - Orchestrator 注入 `self._get_bars` lambda，所有 API 呼叫經過快取

### Documentation

- [x] **Doc-1**: CLAUDE.md 模組路徑過時
  - 新增 `### Source Code Structure` 段落，列出完整 `src/` 目錄樹
  - 標註 decision engine 和 executor 是 `orchestrator.py` 的方法

---

## Phase 4: User-Invocable Skills 建立（已完成）

### `.claude/skills/` 盤點（15 個）

| Skill | 類型 | 用途 |
|-------|------|------|
| `fetch-market-data` | background | Market Analyst 背景知識 |
| `compute-technical-signals` | background | Technical Analyst 背景知識 |
| `analyze-sentiment` | background | Sentiment Analyst 背景知識 |
| `screen-symbols` | background | Symbol Screener 背景知識 |
| `fetch-fundamentals` | background | Fundamentals Analyst 背景知識 |
| `assess-risk` | background | Risk Manager 背景知識 |
| `review-positions` | background | Position Reviewer 背景知識 |
| `place-order` | background | Executor 背景知識 |
| `send-notification` | background | Reporter 背景知識 |
| `search-memory` | background | Reflection / Debate 背景知識 |
| `manage-shared-state` | background | 共用 shared_state 背景知識 |
| **`run-market-analysis`** | **user-invocable** | 三合一市場分析（Market + Tech + Sentiment） |
| **`run-position-review`** | **user-invocable** | 持倉健康檢查 + 退出建議 |
| **`run-full-pipeline`** | **user-invocable** | 完整 pipeline 執行 |
| **`check-portfolio`** | **user-invocable** | 帳戶餘額 + 持倉明細 |

- [x] **Sub-1**: `run-market-analysis` — 合併三個分析 agent 為一個可執行 skill
- [x] **Sub-2**: `run-position-review` — 持倉健康檢查（含自動取得前置數據）
- [x] **Sub-3**: `run-full-pipeline` — 完整 pipeline（支援 `--trade` / `--notify`）
- [x] **Sub-4**: `check-portfolio` — 帳戶 & 持倉狀態（支援 Telegram 發送）

---

## Phase 5: Subagent 自包含改造（已完成）

將 9 個 Subagent 的 agent spec 改造為自包含的 Task tool prompt，消除三層間接引用。

- [x] **Step 1**: 合併 10 個 non-user-invocable skill 內容進對應的 agent spec
  - 移除 `## 可用技能` 和 `## 執行模式` 段落
  - 新增 `## 輸入參數` 段落（從 skill 合併）
  - 9 個 agent spec 現在自包含：角色 + 評分邏輯 + 執行方式 + I/O schema
- [x] **Step 2**: 精簡 AGENT_TEAMS_PROMPT（~235 行 → ~105 行）
  - 改為引用 agent spec 文件路徑，不再內嵌 Python 代碼
  - Subagent phase 只需：讀取 spec → 附加輸入參數 → Task tool spawn
  - Teammate/Lead 相關段落保持不變
- [x] **Step 3**: 刪除 10 個 non-user-invocable skill 目錄
  - 刪除：fetch-market-data, compute-technical-signals, analyze-sentiment, screen-symbols, fetch-fundamentals, assess-risk, place-order, review-positions, send-notification, manage-shared-state
  - 保留 5 個 user-invocable skills：run-full-pipeline, check-portfolio, run-market-analysis, run-position-review, search-memory
- [x] **Step 4**: 更新 CLAUDE.md（Execution Modes 說明 + skill 數量 15→5）
