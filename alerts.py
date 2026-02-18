"""
alerts.py - Extensible alert system.

Current: logging only.
Ready for: Telegram Bot API, SMTP, Slack webhooks.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class AlertConfig:
    """
    Read alert targets from environment variables.
    Set these in GitHub Actions secrets.
    """
    TELEGRAM_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")
    SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: Optional[str] = os.getenv("SMTP_USER")
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")
    ALERT_EMAIL: Optional[str] = os.getenv("ALERT_EMAIL")
    WEBHOOK_URL: Optional[str] = os.getenv("WEBHOOK_URL")


def format_alert_message(article: dict) -> str:
    return (
        f"🚨 MACRO LAB ALERT\n"
        f"Source: {article.get('source', 'N/A')}\n"
        f"Score: {article.get('score_normalized', 0):.1f}/100\n"
        f"Themes: {', '.join(article.get('themes', [])) or 'N/A'}\n"
        f"Title: {article.get('title', '')}\n"
        f"Link: {article.get('link', '')}"
    )


def send_telegram(message: str) -> bool:
    """Send alert via Telegram Bot API."""
    if not AlertConfig.TELEGRAM_TOKEN or not AlertConfig.TELEGRAM_CHAT_ID:
        return False
    try:
        import requests
        url = f"https://api.telegram.org/bot{AlertConfig.TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": AlertConfig.TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"Telegram alert failed: {e}")
        return False


def send_email(message: str, subject: str = "Macro Lab Alert") -> bool:
    """Send alert via SMTP."""
    if not all([AlertConfig.SMTP_HOST, AlertConfig.SMTP_USER,
                AlertConfig.SMTP_PASSWORD, AlertConfig.ALERT_EMAIL]):
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = AlertConfig.SMTP_USER
        msg["To"] = AlertConfig.ALERT_EMAIL

        with smtplib.SMTP(AlertConfig.SMTP_HOST, AlertConfig.SMTP_PORT) as server:
            server.starttls()
            server.login(AlertConfig.SMTP_USER, AlertConfig.SMTP_PASSWORD)
            server.sendmail(AlertConfig.SMTP_USER, AlertConfig.ALERT_EMAIL, msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Email alert failed: {e}")
        return False


def send_webhook(message: str, article: dict) -> bool:
    """Send alert to generic webhook (Slack, Discord, etc.)."""
    if not AlertConfig.WEBHOOK_URL:
        return False
    try:
        import requests
        payload = {
            "text": message,
            "article": {
                "title": article.get("title"),
                "link": article.get("link"),
                "score": article.get("score_normalized"),
                "themes": article.get("themes"),
                "source": article.get("source"),
            }
        }
        resp = requests.post(AlertConfig.WEBHOOK_URL, json=payload, timeout=10)
        return resp.status_code in (200, 204)
    except Exception as e:
        logger.error(f"Webhook alert failed: {e}")
        return False


def trigger_alert(article: dict, reason: str = "score") -> None:
    """
    Main entry point for alerts.
    Called when score > threshold OR critical theme detected.
    
    Args:
        article: The triggering article dict
        reason: "score" | "theme" | "both"
    """
    message = format_alert_message(article)

    logger.warning(f"ALERT [{reason.upper()}]: {article.get('title', '')[:80]}")

    # Try each channel; log failures but don't crash
    channels_tried = []

    if AlertConfig.TELEGRAM_TOKEN:
        success = send_telegram(message)
        channels_tried.append(f"telegram={'ok' if success else 'fail'}")

    if AlertConfig.SMTP_HOST:
        subject = f"[Macro Alert] {article.get('title', '')[:60]}"
        success = send_email(message, subject)
        channels_tried.append(f"email={'ok' if success else 'fail'}")

    if AlertConfig.WEBHOOK_URL:
        success = send_webhook(message, article)
        channels_tried.append(f"webhook={'ok' if success else 'fail'}")

    if not channels_tried:
        logger.info("No alert channels configured. Set env vars to enable: "
                    "TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SMTP_HOST, WEBHOOK_URL")
    else:
        logger.info(f"Alert dispatched: {', '.join(channels_tried)}")


def check_and_alert(articles: list[dict]) -> int:
    """
    Scan all articles, trigger alerts for qualifying ones.
    Returns number of alerts triggered.
    """
    alerts_sent = 0
    for article in articles:
        score = article.get("score_normalized", 0)
        threshold = article.get("alert_threshold", 75.0)
        themes = article.get("themes", [])
        has_critical = len(themes) > 0
        above_threshold = score >= threshold

        if above_threshold and has_critical:
            trigger_alert(article, reason="both")
            alerts_sent += 1
        elif above_threshold:
            trigger_alert(article, reason="score")
            alerts_sent += 1
        elif has_critical:
            trigger_alert(article, reason="theme")
            alerts_sent += 1

    return alerts_sent
