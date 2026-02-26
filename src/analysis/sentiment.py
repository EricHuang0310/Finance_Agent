"""
Sentiment Analysis Module
Uses Alpaca News API + VADER NLP to score news sentiment for trading signals.
"""

import math
from datetime import datetime, timedelta, timezone

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


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

    def analyze_symbol(self, symbol: str, days: int = 3) -> dict:
        """Fetch news for a symbol, score each article, return aggregate sentiment."""
        try:
            articles = self.client.get_news(symbol, days=days, limit=50)
        except Exception as e:
            print(f"    ⚠️  News fetch failed for {symbol}: {e}")
            return {
                "score": 0.0,
                "news_count": 0,
                "sentiment": "neutral",
                "top_headlines": [],
            }

        if not articles:
            return {
                "score": 0.0,
                "news_count": 0,
                "sentiment": "neutral",
                "top_headlines": [],
            }

        now = datetime.now(timezone.utc)
        weighted_scores = []
        weights = []
        scored_articles = []

        for article in articles:
            headline = getattr(article, "headline", "") or ""
            summary = getattr(article, "summary", "") or ""
            created_at = getattr(article, "created_at", None)

            # Score headline + summary (headline weighted more heavily)
            h_score = self.score_text(headline)
            s_score = self.score_text(summary) if summary else h_score
            article_score = h_score * 0.7 + s_score * 0.3

            # Time-decay weight: exponential decay over the window
            if created_at:
                try:
                    # Ensure both datetimes are tz-aware for comparison
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    age_hours = (now - created_at).total_seconds() / 3600
                except Exception:
                    age_hours = 0
            else:
                age_hours = days * 24  # oldest possible

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

        label = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"

        # Confidence based on article count — more data = higher confidence
        news_count = len(articles)
        if news_count == 0:
            confidence = 0.2
        elif news_count <= 3:
            confidence = 0.5
        elif news_count <= 9:
            confidence = 0.8
        else:
            confidence = 1.0

        return {
            "score": round(score, 4),
            "confidence": round(confidence, 2),
            "news_count": news_count,
            "sentiment": label,
            "top_headlines": top_headlines,
        }

    def analyze_all(self, stocks: list[str], crypto: list[str], days: int = 3) -> dict:
        """Run sentiment analysis for all watchlist symbols."""
        symbols_data = {}
        all_scores = []

        all_symbols = stocks + crypto
        for symbol in all_symbols:
            result = self.analyze_symbol(symbol, days=days)
            symbols_data[symbol] = result
            if result["news_count"] > 0:
                all_scores.append(result["score"])

            emoji = "🟢" if result["sentiment"] == "bullish" else "🔴" if result["sentiment"] == "bearish" else "🟡"
            print(f"  {emoji} {symbol}: score={result['score']:.4f} | "
                  f"news={result['news_count']} | {result['sentiment']}")

        # Market-level aggregation
        if all_scores:
            avg_score = sum(all_scores) / len(all_scores)
        else:
            avg_score = 0.0

        # Map avg_score (-1..1) to Fear & Greed (0..100)
        fear_greed = int(round((avg_score + 1.0) * 50))
        fear_greed = max(0, min(100, fear_greed))

        market_label = "bullish" if avg_score > 0.15 else "bearish" if avg_score < -0.15 else "neutral"

        return {
            "timestamp": datetime.now().isoformat(),
            "market_sentiment": market_label,
            "fear_greed_index": fear_greed,
            "symbols": symbols_data,
        }
