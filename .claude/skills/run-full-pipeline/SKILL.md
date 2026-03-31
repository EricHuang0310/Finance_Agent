---
name: run-full-pipeline
description: Run the complete trading analysis pipeline. Use when user wants to execute the full screening → analysis → decision → risk → execution flow.
user-invocable: true
---

# 技能：完整交易 Pipeline

> 一鍵執行完整的多 Agent 交易分析與執行流程。

## 執行步驟

根據使用者需求選擇適當的命令：

### 僅分析（不下單）
```bash
python -m src.agents_launcher --run
```

### 分析 + 下單（Paper Trading）
```bash
python -m src.agents_launcher --run --trade
```

### 分析 + 下單 + Telegram 通知
```bash
python -m src.agents_launcher --run --trade --notify
```

## Pipeline 流程

```
Phase 0:   Symbol Screener        (dynamic watchlist 模式才執行)
Phase 1:   Market + Tech + Sentiment Analysis（並行）
Phase 1.5: Position Exit Review   (檢查現有持倉)
Phase 2:   Decision Engine        (加權評分 + regime 調整)
Phase 3:   Risk Manager           (硬性規則驗證)
Phase 4:   Executor               (先平倉、再開倉)
Phase 5:   Reporter               (Telegram 報告)
```

## 參數說明

| 參數 | 說明 |
|------|------|
| `--run` | 必須，啟動 pipeline |
| `--trade` | 啟用下單執行（預設僅分析） |
| `--notify` | 啟用 Telegram 通知 |

## 注意事項

- 預設為 Paper Trading（取決於 `config/.env` 中的 API key）
- `--trade` 會實際下單，確認前請先用僅分析模式檢查結果
- Pipeline 結果寫入 `shared_state/` 目錄
- 如需 Agent Teams 模式（含辯論），需設定 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=true`
