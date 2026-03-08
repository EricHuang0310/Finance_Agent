"""
Sentiment Analysis Module
Uses Alpaca News API + VADER NLP to score news sentiment for trading signals.
Includes catalyst identification, earnings detection, and signal/noise classification.
"""

import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

try:
    import yfinance as yf
    _HAS_YFINANCE = True
except ImportError:
    _HAS_YFINANCE = False

# Catalyst keyword patterns
_EARNINGS_KEYWORDS = re.compile(
    r'\b(earnings|quarterly results|revenue miss|revenue beat|EPS|guidance|'
    r'profit warning|earnings call|quarterly report)\b', re.IGNORECASE)
_FDA_KEYWORDS = re.compile(
    r'\b(FDA approval|FDA reject|drug approval|clinical trial|phase [123]|'
    r'PDUFA|NDA filing)\b', re.IGNORECASE)
_FOMC_KEYWORDS = re.compile(
    r'\b(FOMC|fed meeting|rate decision|rate hike|rate cut|fed chair|'
    r'federal reserve|interest rate)\b', re.IGNORECASE)
_BINARY_KEYWORDS = re.compile(
    r'\b(merger|acquisition|takeover|buyout|bankruptcy|delisting|'
    r'SEC investigation|class action|recall)\b', re.IGNORECASE)
_NOISE_KEYWORDS = re.compile(
    r'\b(top stocks to watch|best stocks|should you buy|investor alert|'
    r'press release|sponsored|promoted)\b', re.IGNORECASE)

# Hardcoded macro event awareness (approximate recurring dates)
# NOTE: dates should be populated from an external calendar if available
_MACRO_EVENTS = [
    {"event": "FOMC", "description": "Federal Reserve meeting", "impact": "high"},
    {"event": "CPI", "description": "Consumer Price Index release", "impact": "medium_high"},
    {"event": "NFP", "description": "Non-Farm Payrolls", "impact": "medium_high"},
]


class SentimentAnalyzer:
    """Fetches news via Alpaca and scores sentiment using VADER."""

    def __init__(self, alpaca_client):
        self.vader = SentimentIntensityAnalyzer()
        self.client = alpaca_client

    def score_text(self, text: str) -> float:
        """Run VADER on text, return compound score (-1.0 to 1.0)."""
        if not text:
            return 0.0
        return self.vader.polarity_scores(text)["compound"]

    def _classify_headline(self, headline: str) -> str:
        """Classify a headline as 'signal' or 'noise'."""
        if _NOISE_KEYWORDS.search(headline):
            return "noise"
        return "signal"

    def _detect_catalysts(self, headlines: list[str]) -> dict:
        """Scan headlines for catalyst keywords."""
        catalysts = []
        upcoming_earnings = False
        binary_event = False

        for h in headlines:
            if _EARNINGS_KEYWORDS.search(h):
                catalysts.append("earnings")
                upcoming_earnings = True
            if _FDA_KEYWORDS.search(h):
                catalysts.append("FDA")
                binary_event = True
            if _FOMC_KEYWORDS.search(h):
                catalysts.append("FOMC")
            if _BINARY_KEYWORDS.search(h):
                catalysts.append("binary_event")
                binary_event = True

        return {
            "catalysts": list(set(catalysts)),
            "upcoming_earnings": upcoming_earnings,
            "binary_event": binary_event,
        }

    def _get_earnings_date(self, symbol: str) -> str:
        """Try to get next earnings date from yfinance."""
        if not _HAS_YFINANCE:
            return None
        try:
            ticker = yf.Ticker(symbol)
            cal = ticker.calendar
            if cal is not None and not cal.empty:
                # calendar is a DataFrame with earnings date info
                if "Earnings Date" in cal.index:
                    date_val = cal.loc["Earnings Date"]
                    if hasattr(date_val, 'iloc'):
                        return str(date_val.iloc[0])
                    return str(date_val)
            return None
        except Exception:
            return None

    def analyze_symbol(self, symbol: str, days: int = 3) -> dict:
        """Fetch news for a symbol, score each article, return aggregate sentiment."""
        try:
            articles = self.client.get_news(symbol, days=days, limit=50)
        except Exception as e:
            print(f"    ⚠️  News fetch failed for {symbol}: {e}")
            return {
                "score": 0.0,
                "confidence": 0.1,
                "news_count": 0,
                "sentiment": "neutral",
                "top_headlines": [],
                "key_headlines": [],
                "signal_count": 0,
                "noise_count": 0,
                "catalysts": [],
                "upcoming_earnings": False,
                "earnings_imminent": False,
                "binary_event": False,
                "earnings_date": None,
                "data_source": "unavailable",
            }

        if not articles:
            return {
                "score": 0.0,
                "confidence": 0.2,
                "news_count": 0,
                "sentiment": "neutral",
                "top_headlines": [],
                "key_headlines": [],
                "signal_count": 0,
                "noise_count": 0,
                "catalysts": [],
                "upcoming_earnings": False,
                "earnings_imminent": False,
                "binary_event": False,
                "earnings_date": None,
            }

        now = datetime.now(timezone.utc)
        weighted_scores = []
        weights = []
        scored_articles = []
        all_headlines = []
        key_headlines = []
        signal_count = 0
        noise_count = 0

        for article in articles:
            headline = getattr(article, "headline", "") or ""
            summary = getattr(article, "summary", "") or ""
            created_at = getattr(article, "created_at", None)

            all_headlines.append(headline)

            # Score headline + summary (headline weighted more heavily)
            h_score = self.score_text(headline)
            s_score = self.score_text(summary) if summary else h_score
            article_score = h_score * 0.7 + s_score * 0.3

            # Classify signal vs noise
            classification = self._classify_headline(headline)
            if classification == "signal":
                signal_count += 1
            else:
                noise_count += 1

            key_headlines.append({
                "headline": headline,
                "sentiment": round(article_score, 4),
                "type": classification,
            })

            # Time-decay weight: exponential decay over the window
            if created_at:
                try:
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    age_hours = (now - created_at).total_seconds() / 3600
                except Exception:
                    age_hours = 0
            else:
                age_hours = days * 24

            decay = math.exp(-age_hours / (days * 24))
            weighted_scores.append(article_score * decay)
            weights.append(decay)
            scored_articles.append((abs(article_score), headline))

        # Weighted mean
        total_weight = sum(weights)
        if total_weight > 0:
            score = sum(weighted_scores) / total_weight
        else:
            score = 0.0

        score = max(-1.0, min(1.0, score))

        # Top headlines by absolute score
        scored_articles.sort(reverse=True)
        top_headlines = [h for _, h in scored_articles[:5]]

        if score > 0.4:
            label = "bullish"
        elif score > 0.15:
            label = "slightly_bullish"
        elif score >= -0.15:
            label = "neutral"
        elif score >= -0.4:
            label = "slightly_bearish"
        else:
            label = "bearish"

        # Confidence based on article count
        news_count = len(articles)
        if news_count == 0:
            confidence = 0.2
        elif news_count == 1:
            confidence = 0.3
        elif news_count <= 3:
            confidence = 0.5
        elif news_count <= 9:
            confidence = 0.8
        else:
            confidence = 1.0

        # Catalyst detection
        catalyst_info = self._detect_catalysts(all_headlines)

        # Earnings date and imminence check
        earnings_date = None
        earnings_imminent = False
        if catalyst_info["upcoming_earnings"]:
            earnings_date = self._get_earnings_date(symbol)
        if earnings_date:
            try:
                ed = datetime.strptime(earnings_date[:10], "%Y-%m-%d").date()
                days_until = (ed - datetime.now(timezone.utc).date()).days
                if 0 <= days_until <= 3:
                    earnings_imminent = True
            except (ValueError, TypeError):
                pass

        # Sort key_headlines by absolute sentiment (most impactful first), keep top 10
        key_headlines.sort(key=lambda x: abs(x["sentiment"]), reverse=True)
        key_headlines = key_headlines[:10]

        return {
            "score": round(score, 4),
            "confidence": round(confidence, 2),
            "news_count": news_count,
            "sentiment": label,
            "top_headlines": top_headlines,
            "key_headlines": key_headlines,
            "signal_count": signal_count,
            "noise_count": noise_count,
            "catalysts": catalyst_info["catalysts"],
            "upcoming_earnings": catalyst_info["upcoming_earnings"],
            "earnings_imminent": earnings_imminent,
            "binary_event": catalyst_info["binary_event"],
            "earnings_date": earnings_date,
        }

    def analyze_all(self, stocks: list[str], days: int = 3) -> dict:
        """Run sentiment analysis for all watchlist symbols."""
        symbols_data = {}
        all_scores = []

        for symbol in stocks:
            result = self.analyze_symbol(symbol, days=days)
            symbols_data[symbol] = result
            if result["news_count"] > 0:
                all_scores.append(result["score"])

            emoji = "🟢" if "bullish" in result["sentiment"] else "🔴" if "bearish" in result["sentiment"] else "🟡"
            catalyst_str = f" | catalysts: {result['catalysts']}" if result["catalysts"] else ""
            print(f"  {emoji} {symbol}: score={result['score']:.4f} | "
                  f"news={result['news_count']} (sig={result['signal_count']}/noise={result['noise_count']}) | "
                  f"{result['sentiment']}{catalyst_str}")

        # Market-level aggregation
        if all_scores:
            avg_score = sum(all_scores) / len(all_scores)
        else:
            avg_score = 0.0

        # Map avg_score (-1..1) to Fear & Greed (0..100)
        fear_greed = int(round((avg_score + 1.0) * 50))
        fear_greed = max(0, min(100, fear_greed))

        market_label = "bullish" if avg_score > 0.15 else "bearish" if avg_score < -0.15 else "neutral"

        # Macro events awareness
        upcoming_macro_events = []
        for event in _MACRO_EVENTS:
            upcoming_macro_events.append(event)

        result = {
            "timestamp": datetime.now().isoformat(),
            "market_sentiment": market_label,
            "fear_greed_index": fear_greed,
            "symbols": symbols_data,
            "upcoming_macro_events": upcoming_macro_events,
        }

        # Mark staleness when outside US market hours (Mon-Fri 9:30-16:00 ET)
        now_et = datetime.now(ZoneInfo("America/New_York"))
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        if now_et.weekday() >= 5 or now_et < market_open or now_et > market_close:
            result["staleness"] = "off_hours"

        return result
