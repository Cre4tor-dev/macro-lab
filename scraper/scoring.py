"""
scoring.py - Intelligent scoring engine.

Pipeline:
  1. Keyword-weighted TF scoring on title + content
  2. BM25-style term saturation
  3. Theme detection (critical themes boost score)
  4. Dynamic normalization against 7-day corpus
  5. Adaptive threshold calculation
"""

import math
import re
from collections import Counter
from typing import Optional

# ---------------------------------------------------------------------------
# Keyword Taxonomy with weights
# ---------------------------------------------------------------------------

KEYWORD_WEIGHTS: dict[str, float] = {
    # Monetary policy
    "federal reserve": 3.0, "fed": 2.0, "rate cut": 3.5, "rate hike": 3.5,
    "interest rate": 2.5, "fomc": 3.0, "jerome powell": 2.5, "ecb": 2.5,
    "quantitative easing": 2.5, "qt": 1.5, "yield curve": 2.0,
    "boj": 2.0, "bank of england": 2.0, "pivot": 2.0, "inflation": 2.0,
    "cpi": 2.0, "pce": 2.0, "gdp": 1.5,

    # Markets
    "stock market": 2.5, "equities": 2.0, "s&p 500": 2.5, "nasdaq": 2.0,
    "dow jones": 1.5, "market crash": 4.0, "selloff": 3.0, "rally": 1.5,
    "bear market": 3.5, "bull market": 2.0, "correction": 2.5, "vix": 2.5,
    "volatility": 2.0, "earnings": 2.0, "ipo": 1.5, "derivatives": 1.5,
    "hedge fund": 1.5, "short selling": 2.0,

    # Geopolitics
    "war": 4.0, "invasion": 4.5, "conflict": 3.0, "military": 2.5,
    "sanctions": 3.5, "nato": 2.5, "ukraine": 3.0, "russia": 2.5,
    "china": 2.0, "taiwan": 3.5, "middle east": 2.5, "oil": 2.5,
    "energy crisis": 3.0, "geopolitical": 2.5,

    # Crisis keywords
    "crisis": 3.5, "default": 3.5, "bankruptcy": 3.0, "collapse": 4.0,
    "recession": 3.0, "stagflation": 3.0, "hyperinflation": 3.5,
    "bank run": 4.0, "contagion": 3.5, "systemic risk": 3.5,
    "debt ceiling": 3.0, "shutdown": 2.5,

    # General finance
    "merger": 1.5, "acquisition": 1.5, "tariff": 2.5, "trade war": 3.0,
    "dollar": 1.5, "currency": 1.5, "treasury": 2.0, "bond": 1.5,
    "commodity": 1.5, "gold": 1.5, "bitcoin": 1.5, "crypto": 1.5,
}

CRITICAL_THEMES: dict[str, list[str]] = {
    "war_conflict":       ["war", "invasion", "military strike", "airstrike", "nuclear"],
    "market_crash":       ["market crash", "circuit breaker", "trading halt", "black monday", "black swan"],
    "monetary_emergency": ["emergency rate cut", "emergency meeting", "fed emergency", "extraordinary measures"],
    "sovereign_default":  ["default", "debt restructuring", "imf bailout", "sovereign debt crisis"],
    "banking_crisis":     ["bank run", "bank failure", "fdic", "systemic collapse", "bank bailout"],
    "sanctions_major":    ["sanctions", "export controls", "asset freeze", "swift ban"],
    "geopolitical_shock": ["taiwan strait", "nuclear threat", "escalation", "invasion"],
    "recession":          ["recession", "gdp contraction", "economic downturn", "negative growth"],
    "inflation":          ["inflation surge", "cpi spike", "hyperinflation", "price surge"],
    "oil_energy":         ["oil price", "crude oil", "opec", "energy crisis", "oil shock"],
    "market_volatility":  ["vix spike", "volatility surge", "flash crash", "market selloff", "panic selling"],
    "central_bank":       ["rate decision", "central bank", "fomc meeting", "boj decision", "ecb decision"],
}

# BM25 parameters
BM25_K1 = 1.5
BM25_B = 0.75
AVG_DOC_LENGTH = 500  # calibrated for news articles


def tokenize(text: str) -> list[str]:
    """Lowercase and split into tokens."""
    return re.findall(r"[a-z0-9]+(?:[\s'&][a-z0-9]+)*", text.lower())


def compute_raw_score(title: str, content: str) -> tuple[float, list[str], list[str]]:
    """
    Compute raw relevance score using BM25-style term weighting.
    Returns (score, detected_themes, matched_keywords).
    """
    combined_text = (title.lower() + " ") * 3 + content.lower()
    doc_len = len(combined_text.split())

    score = 0.0
    matched_themes = []
    matched_keywords = []

    # --- Keyword scoring (BM25-style saturation) ---
    for phrase, weight in KEYWORD_WEIGHTS.items():
        count = combined_text.count(phrase)
        if count > 0:
            tf_norm = (count * (BM25_K1 + 1)) / (
                count + BM25_K1 * (1 - BM25_B + BM25_B * doc_len / AVG_DOC_LENGTH)
            )
            score += tf_norm * weight
            matched_keywords.append(phrase)

    # --- Critical theme detection ---
    for theme_name, keywords in CRITICAL_THEMES.items():
        for kw in keywords:
            if kw in combined_text:
                if theme_name not in matched_themes:
                    matched_themes.append(theme_name)
                score += 5.0
                break

    return round(score, 4), matched_themes, matched_keywords[:15]


def normalize_scores(articles: list[dict]) -> list[dict]:
    """
    Dynamic normalization: map raw scores to [0, 100] based on
    the distribution of the current 7-day corpus.
    Uses percentile normalization to be robust to outliers.
    """
    raw_scores = [a["score"] for a in articles if a["score"] > 0]

    if not raw_scores:
        return articles

    # Use 95th percentile as ceiling to handle outliers
    sorted_scores = sorted(raw_scores)
    n = len(sorted_scores)
    p95_idx = min(int(0.95 * n), n - 1)
    p5_idx = max(int(0.05 * n), 0)

    score_max = sorted_scores[p95_idx]
    score_min = sorted_scores[p5_idx]
    score_range = score_max - score_min

    for article in articles:
        if score_range > 0:
            normalized = (article["score"] - score_min) / score_range * 100
            article["score_normalized"] = round(max(0.0, min(100.0, normalized)), 2)
        else:
            article["score_normalized"] = 50.0

    return articles


def compute_dynamic_threshold(articles: list[dict]) -> float:
    """
    Compute adaptive alert threshold = mean + 1.5 * std of normalized scores.
    Ensures we only alert on genuinely unusual spikes.
    """
    scores = [a.get("score_normalized", 0) for a in articles]
    if not scores:
        return 75.0

    n = len(scores)
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / n
    std = math.sqrt(variance)

    threshold = mean + 1.5 * std
    return round(min(threshold, 95.0), 2)  # Cap at 95 to avoid never-alerting


def score_articles(articles: list[dict], existing_corpus: list[dict]) -> list[dict]:
    """
    Full scoring pipeline:
    1. Compute raw scores for new articles
    2. Combine with corpus
    3. Normalize globally
    4. Mark is_relevant based on threshold
    """
    # Step 1: Raw scoring
    for article in articles:
        raw, themes, keywords = compute_raw_score(article["title"], article["content"])
        article["score"] = raw
        article["themes"] = themes
        article["matched_keywords"] = keywords

    # Step 2: Combine new + existing for normalization
    all_articles = existing_corpus + articles
    all_articles = normalize_scores(all_articles)

    # Step 3: Adaptive threshold
    threshold = compute_dynamic_threshold(all_articles)

    # Step 4: Mark relevance
    for article in all_articles:
        norm_score = article.get("score_normalized", 0)
        has_critical = len(article.get("themes", [])) > 0
        article["is_relevant"] = (norm_score >= threshold) or has_critical
        article["alert_threshold"] = threshold

    return all_articles


def get_top_articles(articles: list[dict], top_n: int = 20) -> list[dict]:
    """Return top N articles sorted by normalized score descending."""
    scored = [a for a in articles if "score_normalized" in a]
    return sorted(scored, key=lambda x: x["score_normalized"], reverse=True)[:top_n]