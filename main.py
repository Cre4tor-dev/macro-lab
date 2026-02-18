"""
main.py - Orchestrator.
Run this hourly via GitHub Actions.
"""

import logging
import sys
import os

# Ensure scraper/ is importable when run from repo root
sys.path.insert(0, os.path.dirname(__file__))

from sources import fetch_all_articles
from scoring import score_articles, get_top_articles
from storage import update_storage, load_data
from alerts import check_and_alert
from renderer import generate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

TOP_N = 20
ENRICH_CONTENT = True  # Set False to skip full-page fetching (faster, less info)


def run():
    logger.info("=== Macro Lab scrape cycle starting ===")

    # 1. Fetch fresh articles from all sources
    new_articles = fetch_all_articles(enrich_content=ENRICH_CONTENT)
    logger.info(f"Fetched {len(new_articles)} articles total")

    if not new_articles:
        logger.warning("No articles fetched. Exiting.")
        return

    # 2. Storage: purge old, deduplicate, persist
    all_articles, truly_new = update_storage(new_articles)
    logger.info(f"Storage: {len(all_articles)} total articles, {len(truly_new)} new")

    if not all_articles:
        logger.warning("Empty corpus after storage update.")
        return

    # 3. Score ALL articles (full corpus, dynamic normalization)
    all_articles = score_articles(truly_new, all_articles)

    # 4. Get top N for display
    top_articles = get_top_articles(all_articles, top_n=TOP_N)
    logger.info(f"Top {TOP_N}: {[a['title'][:50] for a in top_articles[:5]]}")

    # 5. Check alerts on new articles only
    if truly_new:
        alerts_sent = check_and_alert(truly_new)
        logger.info(f"Alerts triggered: {alerts_sent}")

    # 6. Render HTML
    generate(all_articles, top_articles)

    # 7. Update data.json with final scored articles
    from storage import save_data
    save_data({
        "articles": all_articles,
        "last_updated": "",
        "metadata": {
            "total_runs": 0,
            "sources": list({a["source"] for a in all_articles}),
            "retention_days": 7,
            "top_n": TOP_N,
            "alert_threshold": top_articles[0].get("alert_threshold") if top_articles else None,
        }
    })

    logger.info("=== Cycle complete ===")


if __name__ == "__main__":
    run()
