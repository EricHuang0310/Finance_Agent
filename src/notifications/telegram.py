"""
Telegram Notification Module
Sends trading signals, alerts, and portfolio updates to Telegram.

Setup:
1. Open Telegram, search for @BotFather
2. Send /newbot, follow prompts to create your bot
3. Copy the bot token
4. Send any message to your new bot, then visit:
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   to find your chat_id
5. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to config/.env
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Optional

import httpx
from dotenv import load_dotenv


class TelegramNotifier:
    """Send trading alerts and reports via Telegram."""

    def __init__(self, env_path: str = "config/.env"):
        load_dotenv(env_path)

        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.bot_token and self.chat_id)

        if not self.enabled:
            print("⚠️  Telegram not configured. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env")
        else:
            print("✅ Telegram notifier initialized")

    # ──────────────────────────────────────────────
    # Core Send Methods
    # ──────────────────────────────────────────────

    def send(self, message: str, parse_mode: str = "Markdown") -> bool:
        """Send a message synchronously."""
        if not self.enabled:
            print(f"[TG disabled] {message[:80]}...")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    return True
                else:
                    print(f"❌ Telegram error: {resp.status_code} - {resp.text}")
                    return False
        except Exception as e:
            print(f"❌ Telegram send failed: {e}")
            return False

    async def send_async(self, message: str, parse_mode: str = "Markdown") -> bool:
        """Send a message asynchronously."""
        if not self.enabled:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                return resp.status_code == 200
        except Exception as e:
            print(f"❌ Telegram async send failed: {e}")
            return False

    # ──────────────────────────────────────────────
    # Trading Alert Templates
    # ──────────────────────────────────────────────

    def alert_signal(
        self,
        symbol: str,
        side: str,
        score: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        rsi: Optional[float] = None,
        trend: Optional[str] = None,
    ):
        """Send a trading signal alert."""
        emoji = "🟢 BUY" if side.lower() == "buy" else "🔴 SELL"
        score_bar = self._score_bar(score)

        msg = (
            f"{'━' * 30}\n"
            f"📡 *TRADING SIGNAL*\n"
            f"{'━' * 30}\n\n"
            f"{emoji} *{symbol}*\n\n"
            f"📊 Score: `{score:.3f}` {score_bar}\n"
            f"💰 Entry: `${entry_price:,.2f}`\n"
        )

        if stop_loss:
            msg += f"🛑 Stop Loss: `${stop_loss:,.2f}`\n"
        if take_profit:
            msg += f"🎯 Take Profit: `${take_profit:,.2f}`\n"
        if rsi:
            msg += f"📈 RSI: `{rsi:.1f}`\n"
        if trend:
            trend_emoji = {"bullish": "🐂", "bearish": "🐻", "neutral": "➡️"}.get(trend, "")
            msg += f"📉 Trend: {trend_emoji} `{trend}`\n"

        if stop_loss and take_profit and entry_price:
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            rr = reward / risk if risk > 0 else 0
            msg += f"⚖️ R:R = `{rr:.2f}`\n"

        msg += f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        self.send(msg)

    def alert_order_executed(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: Optional[float] = None,
        order_id: str = "",
    ):
        """Send order execution confirmation."""
        emoji = "✅" if side.lower() == "buy" else "📤"
        msg = (
            f"{emoji} *ORDER EXECUTED*\n\n"
            f"Symbol: *{symbol}*\n"
            f"Side: `{side.upper()}`\n"
            f"Qty: `{qty}`\n"
        )
        if price:
            msg += f"Price: `${price:,.2f}`\n"
        msg += (
            f"Order ID: `{order_id[:12]}...`\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send(msg)

    def alert_order_rejected(self, symbol: str, reason: str):
        """Send order rejection notification."""
        msg = (
            f"❌ *ORDER REJECTED*\n\n"
            f"Symbol: *{symbol}*\n"
            f"Reason: {reason}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send(msg)

    def alert_kill_switch(self, daily_pnl: float, daily_pnl_pct: float):
        """🚨 Emergency kill switch alert."""
        msg = (
            f"🚨🚨🚨 *KILL SWITCH ACTIVATED* 🚨🚨🚨\n\n"
            f"All positions closed. All orders cancelled.\n\n"
            f"Daily P&L: `${daily_pnl:,.2f}` (`{daily_pnl_pct:+.2f}%`)\n"
            f"Trading halted until manual restart.\n\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.send(msg)

    def alert_daily_limit(self, daily_pnl: float, daily_pnl_pct: float):
        """Daily loss limit reached."""
        msg = (
            f"⛔ *DAILY LOSS LIMIT REACHED*\n\n"
            f"Daily P&L: `${daily_pnl:,.2f}` (`{daily_pnl_pct:+.2f}%`)\n"
            f"No new trades will be opened today.\n\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send(msg)

    # ──────────────────────────────────────────────
    # Portfolio & Pipeline Reports
    # ──────────────────────────────────────────────

    def report_portfolio(self, account: dict, positions: list[dict]):
        """Send portfolio summary."""
        equity = account.get("portfolio_value", account.get("equity", 0))
        cash = account.get("cash", 0)
        pnl = equity - account.get("last_equity", equity)
        pnl_pct = (pnl / account.get("last_equity", equity) * 100) if account.get("last_equity") else 0

        msg = (
            f"{'━' * 30}\n"
            f"📊 *PORTFOLIO REPORT*\n"
            f"{'━' * 30}\n\n"
            f"💰 Equity: `${equity:,.2f}`\n"
            f"💵 Cash: `${cash:,.2f}`\n"
            f"📈 Day P&L: `${pnl:,.2f}` (`{pnl_pct:+.2f}%`)\n"
            f"📋 Positions: `{len(positions)}`\n"
        )

        if positions:
            msg += f"\n{'─' * 25}\n"
            for p in positions[:10]:  # Max 10 positions shown
                pl = p.get("unrealized_pl", 0)
                pl_pct = p.get("unrealized_plpc", 0) * 100
                emoji = "🟢" if pl >= 0 else "🔴"
                msg += (
                    f"{emoji} *{p['symbol']}*: "
                    f"{p['qty']} @ `${p.get('avg_entry_price', 0):,.2f}` "
                    f"→ `${pl:+,.2f}` (`{pl_pct:+.1f}%`)\n"
                )

        msg += f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        self.send(msg)

    def report_pipeline_summary(
        self,
        candidates: list[dict],
        approved: list[dict],
        rejected: list[dict],
    ):
        """Send pipeline execution summary."""
        msg = (
            f"{'━' * 30}\n"
            f"🤖 *PIPELINE SUMMARY*\n"
            f"{'━' * 30}\n\n"
            f"🔍 Candidates: `{len(candidates)}`\n"
            f"✅ Approved: `{len(approved)}`\n"
            f"❌ Rejected: `{len(rejected)}`\n"
        )

        if approved:
            msg += f"\n*Approved Trades:*\n"
            for t in approved[:5]:
                msg += (
                    f"  🎯 *{t['symbol']}* | "
                    f"Score: `{t.get('composite_score', 0):.3f}` | "
                    f"Qty: `{t.get('suggested_qty', 0)}`\n"
                )

        if rejected:
            msg += f"\n*Rejected:*\n"
            for t in rejected[:5]:
                reason = t.get("risk_assessment", {}).get("reason", "N/A")
                msg += f"  ⏭️ *{t['symbol']}* - {reason[:50]}\n"

        msg += f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        self.send(msg)

    def report_risk_status(self, risk_summary: dict):
        """Send risk status update."""
        msg = (
            f"🛡️ *RISK STATUS*\n\n"
            f"💰 Equity: `${risk_summary.get('equity', 0):,.2f}`\n"
            f"📊 Exposure: `{risk_summary.get('current_exposure_pct', 0):.1f}%` / "
            f"`{risk_summary.get('max_exposure_pct', 0):.0f}%`\n"
            f"📈 Day P&L: `{risk_summary.get('daily_pnl_pct', 0):+.2f}%`\n"
            f"📉 Drawdown: `{risk_summary.get('drawdown_from_peak_pct', 0):.2f}%` / "
            f"`{risk_summary.get('max_drawdown_pct', 0):.0f}%`\n"
            f"📋 Positions: `{risk_summary.get('position_count', 0)}` / "
            f"`{risk_summary.get('max_positions', 0)}`\n"
        )

        if risk_summary.get("kill_switch_active"):
            msg += "\n🚨 *KILL SWITCH ACTIVE*\n"
        if risk_summary.get("daily_limit_hit"):
            msg += "\n⛔ *DAILY LIMIT REACHED*\n"

        self.send(msg)

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _score_bar(score: float, width: int = 10) -> str:
        """Create a visual score bar."""
        normalized = (score + 1) / 2  # -1..1 → 0..1
        filled = int(normalized * width)
        return "▓" * filled + "░" * (width - filled)

    def test_connection(self) -> bool:
        """Test if bot can send messages."""
        return self.send("🤖 *Trading Bot Connected!*\nTelegram notifications active.")


# ──────────────────────────────────────────────
# Quick Test
# ──────────────────────────────────────────────

if __name__ == "__main__":
    notifier = TelegramNotifier()

    if notifier.enabled:
        # Test connection
        notifier.test_connection()

        # Test signal alert
        notifier.alert_signal(
            symbol="AAPL",
            side="buy",
            score=0.78,
            entry_price=185.50,
            stop_loss=178.20,
            take_profit=198.00,
            rsi=42.5,
            trend="bullish",
        )

        # Test portfolio report
        notifier.report_portfolio(
            account={"portfolio_value": 102500, "cash": 75000, "last_equity": 100000},
            positions=[
                {"symbol": "AAPL", "qty": 10, "avg_entry_price": 185.0,
                 "unrealized_pl": 350, "unrealized_plpc": 0.019},
                {"symbol": "NVDA", "qty": 5, "avg_entry_price": 130.0,
                 "unrealized_pl": -75, "unrealized_plpc": -0.012},
            ],
        )
        print("✅ Test messages sent! Check your Telegram.")
    else:
        print("⚠️  Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in config/.env to test")
        print("\nSetup steps:")
        print("1. Open Telegram → search @BotFather → /newbot")
        print("2. Copy bot token to .env as TELEGRAM_BOT_TOKEN")
        print("3. Send any message to your bot")
        print("4. Visit: https://api.telegram.org/bot<TOKEN>/getUpdates")
        print("5. Find chat.id and set as TELEGRAM_CHAT_ID in .env")
