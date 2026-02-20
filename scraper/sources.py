"""
sources.py - Multi-source scraper returning standardized article dicts.
Add new sources by implementing the BaseSource interface.
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import time
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MacroLabBot/1.0; +https://github.com/yourusername/macro-lab)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

ARTICLE_SCHEMA = {
    "source": "",
    "title": "",
    "link": "",
    "published_date": "",
    "scrape_timestamp": "",
    "content": "",
    "score": 0.0,
    "themes": [],
    "is_relevant": False,
}


def make_article(**kwargs) -> dict:
    article = dict(ARTICLE_SCHEMA)
    article.update(kwargs)
    article["scrape_timestamp"] = datetime.now(timezone.utc).isoformat()
    return article


def fetch_full_content(url: str, timeout: int = 10) -> str:
    """Fetch and extract main text content from an article URL."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove boilerplate
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        # Try article body selectors in priority order
        candidates = [
            soup.find("article"),
            soup.find(class_=lambda c: c and "article-body" in c.lower()),
            soup.find(class_=lambda c: c and "story-body" in c.lower()),
            soup.find(id=lambda i: i and "article" in i.lower()),
            soup.find("main"),
        ]

        for candidate in candidates:
            if candidate:
                text = candidate.get_text(separator=" ", strip=True)
                if len(text) > 200:
                    return text[:8000]  # Cap at ~8k chars to keep RAM low

        # Fallback: all paragraphs
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text(strip=True) for p in paragraphs)
        return text[:8000]

    except Exception as e:
        logger.warning(f"Failed to fetch content from {url}: {e}")
        return ""


class BloombergSource:
    NAME = "Bloomberg"
    FEEDS = [
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://feeds.bloomberg.com/economics/news.rss",
        "https://feeds.bloomberg.com/politics/news.rss",
    ]
    def fetch(self) -> list[dict]:
        articles = []
        for feed_url in self.FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:15]:
                    pub_date = entry.get("published", entry.get("updated", ""))
                    summary = entry.get("summary", "")
                    articles.append(make_article(
                        source=self.NAME,
                        title=entry.get("title", "").strip(),
                        link=entry.get("link", ""),
                        published_date=pub_date,
                        content=summary,
                    ))
                    time.sleep(0.2)
            except Exception as e:
                logger.error(f"Bloomberg feed {feed_url} error: {e}")
        return articles


class EconomistSource:
    NAME = "Economist"
    FEEDS = [
        "https://www.economist.com/finance-and-economics/rss.xml",
        "https://www.economist.com/business/rss.xml",
        "https://www.economist.com/international/rss.xml",
    ]

    def fetch(self) -> list[dict]:
        articles = []
        for feed_url in self.FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:15]:
                    pub_date = entry.get("published", entry.get("updated", ""))
                    summary = entry.get("summary", "")
                    articles.append(make_article(
                        source=self.NAME,
                        title=entry.get("title", "").strip(),
                        link=entry.get("link", ""),
                        published_date=pub_date,
                        content=summary,
                    ))
            except Exception as e:
                logger.error(f"Economist feed {feed_url} error: {e}")
        return articles


# Registry – add sources here as you expand
ACTIVE_SOURCES = [
    BloombergSource(),
    EconomistSource(),
]

def deduplicate_articles(articles: list[dict]) -> list[dict]:
    seen = set()
    unique_articles = []
    for art in articles:
        identifier = (art["link"].split("?")[0], art["title"].strip())
        if identifier not in seen:
            unique_articles.append(art)
            seen.add(identifier)
    return unique_articles


def fetch_all_articles(enrich_content: bool = True) -> list[dict]:
    """
    Fetch articles from all active sources.
    If enrich_content=True, attempt to fetch full article text.
    """
    all_articles = []
    for source in ACTIVE_SOURCES:
        try:
            articles = source.fetch()
            logger.info(f"Fetched {len(articles)} articles from {source.NAME}")

            if enrich_content:
                for art in articles:
                    if len(art["content"]) < 300 and art["link"]:
                        full = fetch_full_content(art["link"])
                        if full:
                            art["content"] = full
                        time.sleep(0.5)

            all_articles.extend(articles)
        except Exception as e:
            logger.error(f"Error in source {source.NAME}: {e}")
    
    all_articles = deduplicate_articles(all_articles)
    return all_articles
