"""
Fundamentals Analysis Module
Fetches company financial data via yfinance for debate context.

This module does NOT produce a composite score — it generates human-readable
summaries that Claude Agent Team debate participants use as context.
"""

from dataclasses import dataclass, asdict
from typing import Optional

# yfinance is an optional dependency; only needed when Agent Teams debates are active.
try:
    import yfinance as yf
    _HAS_YFINANCE = True
except ImportError:
    _HAS_YFINANCE = False


# Crypto symbols that should skip fundamental analysis
_CRYPTO_BASES = {"BTC", "ETH", "SOL", "DOGE", "ADA", "DOT", "AVAX", "MATIC", "LINK", "XRP"}


@dataclass
class FundamentalSignal:
    """Fundamental data for a single symbol."""
    symbol: str
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    pb_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None
    free_cash_flow: Optional[float] = None
    market_cap: Optional[float] = None
    sector: str = "unknown"
    industry: str = "unknown"
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _is_crypto(symbol: str) -> bool:
    """Check if a symbol is a crypto pair (e.g. BTC/USD, BTCUSD)."""
    base = symbol.replace("/", "").replace("USD", "")
    return base in _CRYPTO_BASES


def _format_large_number(n: Optional[float]) -> str:
    if n is None:
        return "N/A"
    abs_n = abs(n)
    if abs_n >= 1e12:
        return f"${n/1e12:.1f}T"
    if abs_n >= 1e9:
        return f"${n/1e9:.1f}B"
    if abs_n >= 1e6:
        return f"${n/1e6:.1f}M"
    return f"${n:,.0f}"


class FundamentalsAnalyzer:
    """Fetches fundamental data from yfinance."""

    def analyze(self, symbol: str) -> Optional[FundamentalSignal]:
        """Fetch fundamental data for a single symbol.

        Returns None for crypto or if yfinance is unavailable.
        """
        if not _HAS_YFINANCE:
            return None

        if _is_crypto(symbol):
            return None

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
        except Exception as e:
            print(f"    ⚠️  Fundamentals fetch failed for {symbol}: {e}")
            return None

        pe = info.get("trailingPE")
        fwd_pe = info.get("forwardPE")
        pb = info.get("priceToBook")
        de = info.get("debtToEquity")
        rev_growth = info.get("revenueGrowth")
        earn_growth = info.get("earningsGrowth")
        fcf = info.get("freeCashflow")
        mcap = info.get("marketCap")
        sector = info.get("sector", "unknown")
        industry = info.get("industry", "unknown")

        # Build human-readable summary for debate agents
        parts = [f"{symbol} ({sector} / {industry})"]

        if pe is not None:
            parts.append(f"P/E: {pe:.1f}" + (f" (Fwd: {fwd_pe:.1f})" if fwd_pe else ""))
        if pb is not None:
            parts.append(f"P/B: {pb:.2f}")
        if de is not None:
            # yfinance returns D/E as percentage (e.g. 150 means 1.5x)
            parts.append(f"D/E: {de:.0f}%")
        if rev_growth is not None:
            parts.append(f"Revenue Growth: {rev_growth*100:+.1f}%")
        if earn_growth is not None:
            parts.append(f"Earnings Growth: {earn_growth*100:+.1f}%")
        if fcf is not None:
            parts.append(f"Free Cash Flow: {_format_large_number(fcf)}")
        if mcap is not None:
            parts.append(f"Market Cap: {_format_large_number(mcap)}")

        summary = " | ".join(parts)

        return FundamentalSignal(
            symbol=symbol,
            pe_ratio=pe,
            forward_pe=fwd_pe,
            pb_ratio=pb,
            debt_to_equity=de,
            revenue_growth=rev_growth,
            earnings_growth=earn_growth,
            free_cash_flow=fcf,
            market_cap=mcap,
            sector=sector,
            industry=industry,
            summary=summary,
        )

    def analyze_batch(self, symbols: list[str]) -> dict[str, Optional[FundamentalSignal]]:
        """Fetch fundamental data for multiple symbols."""
        results = {}
        for symbol in symbols:
            signal = self.analyze(symbol)
            results[symbol] = signal
            if signal:
                print(f"  📋 {signal.summary}")
            else:
                print(f"  ⏭️  {symbol}: skipped (crypto or unavailable)")
        return results
