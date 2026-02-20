"""
storage.py - Sliding window persistence.

- Loads/saves data.json
- Deduplicates by URL (within new batch AND against existing)
- Purges articles older than 7 days
- Keeps repo size stable
"""

import json
import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).parent.parent / "data.json"
RETENTION_DAYS = 7


def _parse_date(date_str: str) -> Optional[datetime]:
    """Try multiple date formats."""
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def load_data() -> dict:
    """Load existing data.json or return empty structure."""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Loaded {len(data.get('articles', []))} articles from storage")
            return data
        except Exception as e:
            logger.error(f"Failed to load data.json: {e}")

    return {
        "articles": [],
        "last_updated": "",
        "metadata": {
            "total_runs": 0,
            "sources": [],
            "retention_days": RETENTION_DAYS,
        }
    }


def save_data(data: dict) -> None:
    """Save data to data.json with atomic write."""
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    tmp_path = DATA_FILE.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(DATA_FILE)
        logger.info(f"Saved {len(data.get('articles', []))} articles to {DATA_FILE}")
    except Exception as e:
        logger.error(f"Failed to save data.json: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def purge_old_articles(articles: list[dict]) -> list[dict]:
    """Remove articles older than RETENTION_DAYS."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    fresh = []
    removed = 0

    for article in articles:
        date_str = article.get("published_date") or article.get("scrape_timestamp", "")
        dt = _parse_date(date_str)

        if dt is None:
            fresh.append(article)
            continue

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        if dt >= cutoff:
            fresh.append(article)
        else:
            removed += 1

    if removed:
        logger.info(f"Purged {removed} articles older than {RETENTION_DAYS} days")

    return fresh


def deduplicate(existing: list[dict], new_articles: list[dict]) -> list[dict]:
    """
    Merge new articles, deduplicating by normalized URL.
    Handles duplicates within new_articles themselves (same article in multiple feeds)
    AND against existing articles.
    """
    # Build seen set from existing articles
    seen_links = {a["link"].rstrip("/").lower() for a in existing}
    added = 0

    for article in new_articles:
        link = article.get("link", "").rstrip("/").lower()
        # Skip empty links or already seen links (catches intra-batch duplicates too)
        if not link or link in seen_links:
            continue
        existing.append(article)
        seen_links.add(link)  # Add immediately so next duplicate in same batch is caught
        added += 1

    skipped = len(new_articles) - added
    logger.info(f"Added {added} new unique articles (skipped {skipped} duplicates)")
    return existing


def update_storage(new_articles: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Full storage update cycle.
    Returns (all_articles_after_purge, truly_new_articles).
    """
    data = load_data()
    existing = data.get("articles", [])

    # Purge old first
    existing = purge_old_articles(existing)

    # Snapshot existing links BEFORE merge (to identify truly new ones)
    existing_links = {a["link"].rstrip("/").lower() for a in existing}

    # Deduplicate and merge
    merged = deduplicate(existing, new_articles)

    # Truly new = articles that weren't in existing before this run
    truly_new = [
        a for a in new_articles
        if a.get("link", "").rstrip("/").lower() not in existing_links
    ]
    # Also deduplicate truly_new itself (same fix)
    seen = set()
    truly_new_deduped = []
    for a in truly_new:
        link = a.get("link", "").rstrip("/").lower()
        if link and link not in seen:
            truly_new_deduped.append(a)
            seen.add(link)
    truly_new = truly_new_deduped

    # Update metadata
    data["articles"] = merged
    data["metadata"]["total_runs"] = data["metadata"].get("total_runs", 0) + 1
    data["metadata"]["sources"] = list({a["source"] for a in merged})

    save_data(data)
    return merged, truly_new