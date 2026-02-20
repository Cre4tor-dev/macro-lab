"""
scoring.py - Scoring engine combiné.

Pipeline :
  1. Sentiment score (dictionnaire financier pondéré + sqrt transformation)
  2. Relevance score (BM25 keyword matching sur taxonomie macro)
  3. Score combiné = 0.5 * sentiment_norm + 0.5 * relevance_norm
  4. Détection de thèmes critiques (boost + tags)
  5. Normalisation dynamique [0-100] sur corpus 7 jours
  6. Seuil adaptatif mean + 1.5σ
"""

import math
import re
import logging
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

# =============================================================================
# 1. DICTIONNAIRE DE SENTIMENT FINANCIER
# =============================================================================

SENTIMENT_DICT: dict[str, float] = {
    # EXTREME NEGATIVE
    "crash": -5.0, "meltdown": -5.0, "collapse": -5.0, "bankruptcy": -5.0,
    "default": -5.0, "insolvency": -5.0, "liquidation": -5.0,
    "panic": -4.8, "contagion": -4.8, "systemic": -4.7,
    "depression": -4.7, "turmoil": -4.6, "plunge": -4.6,
    "sanctions": -4.5, "war": -4.5, "conflict": -4.5,
    "shock": -4.5, "crisis": -4.5, "implosion": -4.5,
    "bloodbath": -4.5, "freeze": -4.4, "shutdown": -4.4,
    "downgrade": -4.3, "seizure": -4.3, "fraud": -4.2,
    "scandal": -4.2, "lawsuit": -4.2, "probe": -4.0,
    # STRONG NEGATIVE
    "recession": -4.0, "stagflation": -4.0, "deflation": -3.8,
    "inflation": -3.5, "layoffs": -3.5, "jobless": -3.5,
    "selloff": -3.5, "decline": -3.5, "slump": -3.5, "worst": -4.0,
    "loss": -3.5, "weak": -3.3, "slowdown": -3.3,
    "shortage": -3.2, "cut": -3.2, "tightening": -3.2,
    "ratehike": -3.0, "hike": -3.0, "tariffs": -3.0,
    "deficit": -3.0, "debt": -3.0, "uncertainty": -3.0,
    "volatility": -3.0, "risk": -2.8, "tension": -2.8,
    "strike": -2.8, "protest": -2.8, "drop": -2.7,
    "dip": -2.5, "downturn": -3.0,
    # MODERATE NEGATIVE
    "concern": -2.5, "pressure": -2.5, "fear": -2.5,
    "bearish": -2.5, "correction": -2.5, "fall": -2.5,
    "miss": -2.3, "underperform": -2.3, "cutback": -2.3,
    "slower": -2.2, "cooling": -2.0, "downtime": -2.0,
    "oversupply": -2.0, "oversold": -2.0,
    "volatile": -2.0, "exposed": -1.8,
    "fragile": -1.8, "cautious": -1.5,
    # MODERATE POSITIVE
    "steady": 2.5, "stable": 2.5, "progress": 2.5, "recover": 2.5,
    "hire": 2.3, "jobs": 2.3, "productive": 2.2, "efficient": 2.2,
    "opportunity": 2.2, "demand": 2.2, "healthy": 2.0, "solid": 2.0,
    "encourage": 2.0, "boost": 2.0, "uptrend": 2.0, "outperform": 2.0,
    # STRONG POSITIVE
    "gain": 3.5, "rise": 3.5, "climb": 3.5,
    "optimistic": 3.5, "confidence": 3.5,
    "improve": 3.3, "improvement": 3.3,
    "resilient": 3.3, "stability": 3.3,
    "support": 3.2, "backed": 3.2,
    "innovation": 3.2, "expand": 3.2,
    "acquisition": 3.2, "merger": 3.2,
    "investment": 3.2, "inflow": 3.2,
    "bullish": 3.0, "accelerate": 3.0,
    "momentum": 3.0, "robust": 3.0,
    # EXTREME POSITIVE
    "boom": 5.0, "recordhigh": 5.0, "alltimehigh": 5.0,
    "breakthrough": 4.8, "surge": 4.8, "soar": 4.8,
    "explode": 4.7, "skyrocket": 4.7,
    "stimulus": 4.5, "bailout": 4.5,
    "deal": 4.5, "agreement": 4.5,
    "victory": 4.5, "approval": 4.5,
    "upgrade": 4.3, "beat": 4.3,
    "windfall": 4.3, "profit": 4.2,
    "strong": 4.0, "growth": 4.0,
    "recovery": 4.0, "expansion": 4.0,
    "rally": 4.0, "bullrun": 4.0,
    # VERBS NEGATIVE
    "falls": -2.5, "fell": -2.5, "drops": -2.5, "dropped": -2.5,
    "declines": -2.5, "declined": -2.5, "slip": -2.3, "slips": -2.3,
    "slipped": -2.3, "edge lower": -2.0, "weaken": -2.5,
    "weakens": -2.5, "weakened": -2.5, "lower": -1.8,
    "under pressure": -2.5, "hit": -2.0, "drag": -2.0,
    "weigh": -2.0, "weighs": -2.0, "weighed": -2.0,
    # VERBS POSITIVE
    "rises": 2.5, "rose": 2.5, "gains": 2.5, "gained": 2.5,
    "advance": 2.5, "advances": 2.5, "advanced": 2.5,
    "climbs": 2.5, "climbed": 2.5, "edge higher": 2.0,
    "firm": 2.0, "firms": 2.0, "firmed": 2.0,
    "strengthen": 2.5, "strengthens": 2.5, "strengthened": 2.5,
    "higher": 1.8, "boosted": 2.5, "lifted": 2.5,
    # JOURNALISTIC
    "concerns": -2.0, "fears": -2.5, "worries": -2.3,
    "uncertain": -2.0, "headwinds": -2.5, "risk-off": -3.0,
    "caution": -1.5, "warns": -2.0, "warning": -2.0,
    "hopes": 2.0, "optimism": 2.5, "supportive": 2.0,
    "tailwind": 2.5, "upbeat": 2.5, "improves": 2.5, "signals": 1.5,
    # MACRO SPECIFIC
    "unemployment": -2.5, "employment": 2.5, "payrolls": 2.0,
    "surplus": 3.5, "easing": 2.5, "qe": 3.0, "qt": -3.0,
    "ratecut": 3.5, "ratecuts": 3.5, "ratehikes": -3.5,
    # BANKING / CREDIT
    "capitalraise": 2.5, "capitalshortfall": -4.0,
    "write-down": -4.2, "write-off": -4.2, "impairment": -3.8,
    "provision": -2.0, "solvent": 3.5, "insolvent": -5.0,
    "liquiditycrunch": -4.8, "margin call": -4.5,
    "creditcrunch": -4.5, "creditfreeze": -4.7,
    "spreadwidening": -3.8, "spreadtightening": 3.2,
    "illiquid": -3.5, "bankrun": -5.0, "depositflight": -4.5,
    "contagionrisk": -4.8, "systemicrisk": -4.8,
    # GEOPOLITICS
    "ceasefire": 4.0, "escalation": -4.0, "blockade": -4.0,
    "embargo": -4.0, "tensions": -3.0, "standoff": -3.0,
    # POLICY
    "hawkish": -3.5, "dovish": 3.5, "intervention": 2.0,
    "stabilization": 2.5, "independence": 2.5,
    # FX
    "capitalflight": -4.0, "devaluation": -4.0,
    "depreciation": -2.5, "appreciation": 2.5, "currencycrisis": -5.0,
    # COMMODITIES
    "opeccut": 3.5, "opecincrease": -3.0,
    "productioncut": 3.0, "productionhalt": -4.0,
    "demanddestruction": -4.5, "glut": -3.5,
    # DATA FRAMING
    "above expectations": 3.0, "softlanding": 4.5, "hardlanding": -4.8,
    "disinflation": 3.5, "stickyinflation": -3.8,
    "overheating": -3.5, "contraction": -4.0, "expanding": 3.0,
    # EQUITY
    "derisking": -3.5, "deleveraging": -4.0,
    "shortsqueeze": 4.5, "capitulation": -4.5,
    "breakout": 3.8, "breakdown": -3.8,
    "overvalued": -2.5, "undervalued": 2.5,
    # LIGHT DESCRIPTORS
    "rebound": 1.3, "rebounded": 1.3, "uptick": 1.2,
    "pullback": -1.3, "stalled": -1.2, "choppy": -1.2,
    "fragility": -1.3, "weakness": -1.5, "dragged": -1.5,
    "retreat": -1.3, "retreated": -1.3,
    "amid": -0.5, "despite": 0.2,
}

# =============================================================================
# 2. TAXONOMIE DE RELEVANCE MACRO (BM25)
# =============================================================================

KEYWORD_WEIGHTS: dict[str, float] = {
    "federal reserve": 3.0, "fed": 2.0, "rate cut": 3.5, "rate hike": 3.5,
    "interest rate": 2.5, "fomc": 3.0, "jerome powell": 2.5, "ecb": 2.5,
    "quantitative easing": 2.5, "yield curve": 2.0, "boj": 2.0,
    "bank of england": 2.0, "inflation": 2.0, "cpi": 2.0, "gdp": 1.5,
    "stock market": 2.5, "equities": 2.0, "s&p 500": 2.5, "nasdaq": 2.0,
    "market crash": 4.0, "selloff": 3.0, "bear market": 3.5,
    "vix": 2.5, "volatility": 2.0, "earnings": 2.0,
    "war": 4.0, "invasion": 4.5, "conflict": 3.0, "military": 2.5,
    "sanctions": 3.5, "nato": 2.5, "ukraine": 3.0, "russia": 2.5,
    "china": 2.0, "taiwan": 3.5, "middle east": 2.5, "oil": 2.5,
    "energy crisis": 3.0, "geopolitical": 2.5,
    "crisis": 3.5, "default": 3.5, "bankruptcy": 3.0, "collapse": 4.0,
    "recession": 3.0, "stagflation": 3.0, "bank run": 4.0,
    "contagion": 3.5, "systemic risk": 3.5, "debt ceiling": 3.0,
    "tariff": 2.5, "trade war": 3.0, "treasury": 2.0, "bond": 1.5,
    "gold": 1.5, "bitcoin": 1.5, "crypto": 1.5,
}

CRITICAL_THEMES: dict[str, list[str]] = {
    "war_conflict":       ["war", "invasion", "military strike", "airstrike", "nuclear"],
    "market_crash":       ["market crash", "circuit breaker", "trading halt", "black monday"],
    "monetary_emergency": ["emergency rate cut", "emergency meeting", "fed emergency"],
    "sovereign_default":  ["default", "debt restructuring", "imf bailout"],
    "banking_crisis":     ["bank run", "bank failure", "fdic", "systemic collapse"],
    "sanctions_major":    ["sanctions", "export controls", "asset freeze", "swift ban"],
    "geopolitical_shock": ["taiwan strait", "nuclear threat", "escalation", "invasion"],
    "recession":          ["recession", "gdp contraction", "economic downturn"],
    "inflation":          ["inflation surge", "cpi spike", "hyperinflation"],
    "oil_energy":         ["oil price", "crude oil", "opec", "energy crisis"],
    "market_volatility":  ["vix spike", "volatility surge", "flash crash", "market selloff"],
    "central_bank":       ["rate decision", "central bank", "fomc meeting", "ecb decision"],
}

BM25_K1 = 1.5
BM25_B  = 0.75
AVG_DOC_LENGTH = 500


# =============================================================================
# 3. FONCTIONS INTERNES
# =============================================================================

def _preprocess(text: str) -> str:
    text = re.sub(r'[\r\n]+', ' ', text)
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _tokenize(text: str) -> list[str]:
    """Unigrams + bigrams pour capturer les expressions multi-mots."""
    words = text.split()
    bigrams = [' '.join(words[i:i+2]) for i in range(len(words) - 1)]
    return words + bigrams


def _sentiment_score(title: str, content: str) -> tuple[float, str]:
    """
    Score de sentiment financier avec sqrt transformation.
    Title pèse 3x plus que le contenu.
    Retourne (raw_score, label).
    """
    # Titre 3x plus lourd
    combined = _preprocess((title + " ") * 3 + " " + content)
    tokens = _tokenize(combined)
    token_counts = Counter(tokens)

    raw = 0.0
    for token, count in token_counts.items():
        if token in SENTIMENT_DICT:
            raw += SENTIMENT_DICT[token] * count

    # Signed sqrt pour compresser les extrêmes
    if raw > 0:
        transformed = math.sqrt(raw)
    elif raw < 0:
        transformed = -math.sqrt(abs(raw))
    else:
        transformed = 0.0

    if raw >= 100:
        label = "Extreme Positive"
    elif raw >= 10:
        label = "Positive"
    elif raw <= -100:
        label = "Extreme Negative"
    elif raw <= -10:
        label = "Negative"
    else:
        label = "Neutral"

    return transformed, label


def _relevance_score(title: str, content: str) -> tuple[float, list[str], list[str]]:
    """
    Score de relevance macro via BM25 + détection thèmes critiques.
    Retourne (score, themes, matched_keywords).
    """
    combined = (title.lower() + " ") * 3 + content.lower()
    doc_len = len(combined.split())

    score = 0.0
    matched_keywords = []
    matched_themes = []

    for phrase, weight in KEYWORD_WEIGHTS.items():
        count = combined.count(phrase)
        if count > 0:
            tf_norm = (count * (BM25_K1 + 1)) / (
                count + BM25_K1 * (1 - BM25_B + BM25_B * doc_len / AVG_DOC_LENGTH)
            )
            score += tf_norm * weight
            matched_keywords.append(phrase)

    for theme_name, keywords in CRITICAL_THEMES.items():
        for kw in keywords:
            if kw in combined:
                if theme_name not in matched_themes:
                    matched_themes.append(theme_name)
                score += 5.0
                break

    return score, matched_themes, matched_keywords[:15]


# =============================================================================
# 4. NORMALISATION DYNAMIQUE
# =============================================================================

def _normalize_to_100(values: list[float]) -> tuple[float, float]:
    """Retourne (min_p5, max_p95) pour normalisation percentile."""
    if not values:
        return 0.0, 1.0
    s = sorted(values)
    n = len(s)
    p5  = s[max(int(0.05 * n), 0)]
    p95 = s[min(int(0.95 * n), n - 1)]
    return p5, max(p95, p5 + 0.001)


def normalize_scores(articles: list[dict]) -> list[dict]:
    """Normalise score_combined → score_normalized [0-100] sur corpus complet."""
    raw_vals = [a.get("score_combined", 0.0) for a in articles]
    p5, p95 = _normalize_to_100(raw_vals)
    rng = p95 - p5

    for a in articles:
        val = a.get("score_combined", 0.0)
        normalized = (val - p5) / rng * 100 if rng > 0 else 50.0
        a["score_normalized"] = round(max(0.0, min(100.0, normalized)), 2)

    return articles


def compute_dynamic_threshold(articles: list[dict]) -> float:
    """Seuil adaptatif = mean + 1.5σ des scores normalisés."""
    scores = [a.get("score_normalized", 0) for a in articles]
    if not scores:
        return 75.0
    n = len(scores)
    mean = sum(scores) / n
    std = math.sqrt(sum((s - mean) ** 2 for s in scores) / n)
    return round(min(mean + 1.5 * std, 95.0), 2)


# =============================================================================
# 5. INTERFACE PUBLIQUE (inchangée pour les autres fichiers)
# =============================================================================

def score_articles(articles: list[dict], existing_corpus: list[dict]) -> list[dict]:
    """
    Pipeline complet sur le corpus.
    Produit sur chaque article :
      - score_sentiment   : score signé (négatif/positif)
      - sentiment_label   : "Positive" / "Negative" / "Neutral" / "Extreme ..."
      - score_relevance   : score BM25 brut
      - score_combined    : combinaison des deux
      - score_normalized  : [0-100] relatif au corpus 7 jours
      - themes            : liste de thèmes critiques détectés
      - matched_keywords  : mots-clés BM25 détectés (pour tooltip)
      - alert_threshold   : seuil dynamique du run
      - is_relevant       : bool
    """
    for article in articles:
        title   = article.get("title", "")
        content = article.get("content", "")

        # Sentiment
        sent_score, sent_label = _sentiment_score(title, content)
        article["score_sentiment"]  = round(sent_score, 4)
        article["sentiment_label"]  = sent_label

        # Relevance BM25
        rel_score, themes, keywords = _relevance_score(title, content)
        article["score_relevance"]  = round(rel_score, 4)
        article["themes"]           = themes
        article["matched_keywords"] = keywords

        # Score combiné : on prend la valeur absolue du sentiment
        # (un article très négatif est aussi pertinent qu'un très positif)
        # et on ajoute la relevance. Pondération 40% sentiment / 60% relevance.
        article["score_combined"] = round(
            0.4 * abs(sent_score) + 0.6 * rel_score, 4
        )
        # Conserver score brut pour compatibilité
        article["score"] = article["score_combined"]

    # Normalisation globale
    articles = normalize_scores(articles)

    # Seuil adaptatif
    threshold = compute_dynamic_threshold(articles)

    for article in articles:
        norm = article.get("score_normalized", 0)
        article["is_relevant"]     = norm >= threshold or len(article.get("themes", [])) > 0
        article["alert_threshold"] = threshold

    return articles


def get_top_articles(articles: list[dict], top_n: int = 20) -> list[dict]:
    """Top N articles par score normalisé décroissant."""
    scored = [a for a in articles if "score_normalized" in a]
    return sorted(scored, key=lambda x: x["score_normalized"], reverse=True)[:top_n]