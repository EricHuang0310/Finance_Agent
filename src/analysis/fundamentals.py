"""
Fundamentals Analysis Module
Fetches company financial data via yfinance for debate context.

This module does NOT produce a composite score — it generates human-readable
summaries that Claude Agent Team debate participants use as context.

Rate-limit handling:
  - 2s delay between consecutive API calls
  - Exponential backoff retry (up to 3 attempts) on failures
  - Daily disk cache in shared_state to avoid redundant calls
"""

import json
import time
from dataclasses import dataclass, asdict
from typing import Optional

from src.state_dir import get_state_dir

# yfinance is an optional dependency; only needed when Agent Teams debates are active.
try:
    import yfinance as yf
    _HAS_YFINANCE = True
except ImportError:
    _HAS_YFINANCE = False

_REQUEST_DELAY = 2.0       # seconds between API calls
_MAX_RETRIES = 3           # retry attempts per symbol
_BACKOFF_BASE = 3.0        # base seconds for exponential backoff
_CACHE_FILENAME = "fundamentals_cache.json"



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
    """Fetches fundamental data from yfinance with rate-limit handling and daily cache."""

    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._cache_loaded = False

    # ── Daily disk cache ──────────────────────────────────

    def _cache_path(self):
        return get_state_dir() / _CACHE_FILENAME

    def _load_cache(self):
        """Load today's cache from disk (once per instance)."""
        if self._cache_loaded:
            return
        self._cache_loaded = True
        path = self._cache_path()
        if path.exists():
            try:
                self._cache = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def _save_cache(self):
        """Persist cache to disk."""
        try:
            self._cache_path().write_text(json.dumps(self._cache, default=str))
        except OSError:
            pass

    def _cache_get(self, symbol: str) -> Optional[dict]:
        self._load_cache()
        return self._cache.get(symbol)

    def _cache_put(self, symbol: str, info: dict):
        self._cache[symbol] = info
        self._save_cache()

    # ── yfinance fetch with retry ─────────────────────────

    def _fetch_info(self, symbol: str) -> Optional[dict]:
        """Fetch ticker.info with exponential backoff retry."""
        for attempt in range(_MAX_RETRIES):
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
                if info:
                    return info
            except Exception as e:
                wait = _BACKOFF_BASE * (2 ** attempt)
                print(f"    ⚠️  Fundamentals fetch failed for {symbol} "
                      f"(attempt {attempt + 1}/{_MAX_RETRIES}): {e}")
                if attempt < _MAX_RETRIES - 1:
                    print(f"    ⏳ Retrying in {wait:.0f}s …")
                    time.sleep(wait)
        return None

    # ── Core analysis ─────────────────────────────────────

    @staticmethod
    def _build_signal(symbol: str, info: dict) -> FundamentalSignal:
        """Build a FundamentalSignal from a yfinance info dict."""
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

        parts = [f"{symbol} ({sector} / {industry})"]
        if pe is not None:
            parts.append(f"P/E: {pe:.1f}" + (f" (Fwd: {fwd_pe:.1f})" if fwd_pe else ""))
        if pb is not None:
            parts.append(f"P/B: {pb:.2f}")
        if de is not None:
            parts.append(f"D/E: {de:.0f}%")
        if rev_growth is not None:
            parts.append(f"Revenue Growth: {rev_growth*100:+.1f}%")
        if earn_growth is not None:
            parts.append(f"Earnings Growth: {earn_growth*100:+.1f}%")
        if fcf is not None:
            parts.append(f"Free Cash Flow: {_format_large_number(fcf)}")
        if mcap is not None:
            parts.append(f"Market Cap: {_format_large_number(mcap)}")

        return FundamentalSignal(
            symbol=symbol, pe_ratio=pe, forward_pe=fwd_pe, pb_ratio=pb,
            debt_to_equity=de, revenue_growth=rev_growth,
            earnings_growth=earn_growth, free_cash_flow=fcf,
            market_cap=mcap, sector=sector, industry=industry,
            summary=" | ".join(parts),
        )

    def analyze(self, symbol: str) -> Optional[FundamentalSignal]:
        """Fetch fundamental data for a single symbol.

        Returns None if yfinance is unavailable.
        """
        if not _HAS_YFINANCE:
            return None

        # Check daily cache first
        cached = self._cache_get(symbol)
        if cached:
            print(f"    💾 {symbol}: using cached fundamentals")
            return self._build_signal(symbol, cached)

        info = self._fetch_info(symbol)
        if info is None:
            return None

        self._cache_put(symbol, info)
        return self._build_signal(symbol, info)

    def analyze_batch(self, symbols: list[str]) -> dict[str, Optional[FundamentalSignal]]:
        """Fetch fundamental data for multiple symbols with rate limiting."""
        results = {}
        for i, symbol in enumerate(symbols):
            # Rate-limit delay between API calls (skip for cached / first request)
            needs_api = self._cache_get(symbol) is None
            if needs_api and i > 0:
                print(f"    ⏳ Rate-limit delay ({_REQUEST_DELAY}s) …")
                time.sleep(_REQUEST_DELAY)

            signal = self.analyze(symbol)
            results[symbol] = signal
            if signal:
                print(f"  📋 {signal.summary}")
            else:
                print(f"  ⏭️  {symbol}: skipped (unavailable)")
        return results
