---
name: run-market-analysis
description: Run market data collection + technical analysis + sentiment analysis on the current watchlist. Use when user wants a quick market overview without running the full trading pipeline.
user-invocable: true
---

# 技能：市場分析（三合一）

> 一次執行 Market Analyst + Technical Analyst + Sentiment Analyst，快速取得市場全貌。

## 執行步驟

用 Bash 工具執行以下 Python 腳本：

```bash
python -c "
from src.agents_launcher import task_market_analyst, task_technical_analyst, task_sentiment_analyst
import json

print('=' * 60)
print('  MARKET ANALYSIS (3-in-1)')
print('=' * 60)

market = task_market_analyst()
tech = task_technical_analyst()
sentiment = task_sentiment_analyst()

# Print summary
print()
print('=' * 60)
print('  SUMMARY')
print('=' * 60)
regime = market.get('market_regime', 'unknown')
print(f'  Market Regime: {regime}')
print(f'  Stocks analyzed: {len(tech.get(\"stocks\", {}))}')
print(f'  Crypto analyzed: {len(tech.get(\"crypto\", {}))}')
print(f'  Sentiment signals: {len(sentiment.get(\"stocks\", {})) + len(sentiment.get(\"crypto\", {}))}')
"
```

## 輸出

執行後產生 3 個 shared_state 檔案：
- `shared_state/market_overview.json` — 市場行情 + regime
- `shared_state/technical_signals.json` — 技術指標 + 動量評分
- `shared_state/sentiment_signals.json` — 情緒分數

## 用途場景

- 盤前快速掃描市場狀態
- 查看特定標的的技術 / 情緒信號
- 不需要下單，只想了解當前市場

## 注意事項

- 需要 Alpaca API key（`config/.env`）
- Watchlist 來自 `config/settings.yaml`
- 結果會覆蓋 `shared_state/` 中的舊資料
