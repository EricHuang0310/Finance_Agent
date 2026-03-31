---
name: check-portfolio
description: Check current account balance, positions, and unrealized P&L from Alpaca. Use when user wants to see their portfolio status.
user-invocable: true
---

# 技能：帳戶與持倉狀態

> 查詢 Alpaca 帳戶餘額、持倉明細、未實現損益。

## 執行步驟

用 Bash 工具執行以下 Python 腳本：

```bash
python -c "
from src.alpaca_client import AlpacaClient

client = AlpacaClient()
account = client.get_account()
positions = client.get_positions()

print('=' * 60)
print('  PORTFOLIO STATUS')
print('=' * 60)
print(f'  Equity:     \${float(account[\"equity\"]):>12,.2f}')
print(f'  Cash:       \${float(account[\"cash\"]):>12,.2f}')
print(f'  Buying Power:\${float(account[\"buying_power\"]):>11,.2f}')

last_eq = float(account.get('last_equity', account['equity']))
daily_pnl = float(account['equity']) - last_eq
daily_pct = (daily_pnl / last_eq * 100) if last_eq > 0 else 0
sign = '+' if daily_pnl >= 0 else ''
print(f'  Day P&L:    {sign}\${daily_pnl:>11,.2f} ({sign}{daily_pct:.2f}%)')

print()
if not positions:
    print('  No open positions.')
else:
    print(f'  Open Positions ({len(positions)}):')
    print(f'  {\"Symbol\":<10} {\"Qty\":>8} {\"Side\":<6} {\"Entry\":>10} {\"Current\":>10} {\"P&L\":>12} {\"P&L%\":>8}')
    print('  ' + '-' * 66)
    for p in positions:
        sym = p['symbol']
        qty = float(p['qty'])
        side = p['side']
        entry = float(p['avg_entry_price'])
        current = float(p['current_price'])
        pl = float(p['unrealized_pl'])
        plpc = float(p['unrealized_plpc']) * 100
        sign = '+' if pl >= 0 else ''
        print(f'  {sym:<10} {qty:>8.2f} {side:<6} \${entry:>9.2f} \${current:>9.2f} {sign}\${pl:>10.2f} {sign}{plpc:>6.2f}%')

    total_pl = sum(float(p['unrealized_pl']) for p in positions)
    sign = '+' if total_pl >= 0 else ''
    print('  ' + '-' * 66)
    print(f'  {\"Total unrealized P&L:\":>48} {sign}\${total_pl:>10.2f}')
"
```

## 加上 Telegram 通知

如果使用者也想發送到 Telegram：

```bash
python -c "
from src.alpaca_client import AlpacaClient
from src.notifications.telegram import TelegramNotifier

client = AlpacaClient()
notifier = TelegramNotifier()
account = client.get_account()
positions = client.get_positions()
notifier.report_portfolio(account, positions)
print('Portfolio report sent to Telegram.')
"
```

## 注意事項

- 需要 Alpaca API key（`config/.env`）
- 顯示的是即時數據（非快取）
- Paper 和 Live 帳戶取決於 API key 類型
