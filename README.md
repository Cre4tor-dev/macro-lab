# Macro Lab — Personal Macro Intelligence System

> Automated market & geopolitical intelligence. Scrapes hourly, scores intelligently, deploys to static HTML.

## Architecture

```
GitHub Repository
  └── .github/workflows/scrape.yml   ← Cron: every hour
        │
        ▼
  GitHub Actions Runner (ubuntu, ~100MB RAM peak)
        │
        ▼
  scraper/main.py
    ├── sources.py       → Fetch RSS + full article content
    ├── scoring.py       → BM25 keyword scoring + dynamic normalization
    ├── storage.py       → 7-day sliding window, dedup, persist
    ├── alerts.py        → Telegram / Email / Webhook
    └── renderer.py      → Generate index.html
        │
        ▼
  data.json  +  index.html
        │
        ▼ git commit + push (only if changed)
        │
        ▼
  Vercel (auto-deploy on push) → https://your-domain.vercel.app
```

## Scoring Pipeline

```
Raw text (title × 3 + content)
  → BM25-normalized keyword matching (weighted taxonomy: markets, geopolitics, crisis)
  → Critical theme detection (war, default, bank run, etc.)
  → Percentile normalization against 7-day corpus → score [0–100]
  → Adaptive threshold = mean + 1.5σ
  → is_relevant = score ≥ threshold OR critical theme detected
```

**Why BM25 over pure TF?** Prevents high-frequency but low-signal documents (e.g., opinion pieces
mentioning "markets" 20x) from dominating. Term saturation with K1=1.5.

**Why percentile normalization?** Robust to outliers. Score is always relative to recent corpus
distribution, so threshold adapts automatically to news cycles.

## Setup

### 1. Create GitHub repository and push code

```bash
git init
git remote add origin https://github.com/yourusername/macro-lab
git add .
git commit -m "init: macro lab"
git push -u origin main
```

### 2. Connect Vercel

- Go to https://vercel.com → New Project → Import from GitHub
- Framework: Other (static)
- Root directory: `/`
- No build command needed
- Vercel auto-deploys on every push

### 3. Enable GitHub Actions

The workflow is in `.github/workflows/scrape.yml`. It runs automatically at `0 * * * *`.

Manual trigger: GitHub → Actions → "Macro Lab Hourly Scrape" → Run workflow

### 4. Configure Alerts (optional)

Set these in **GitHub → Settings → Secrets → Actions**:

| Secret | Description |
|--------|-------------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Your chat or channel ID |
| `SMTP_HOST` | e.g. `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Your email |
| `SMTP_PASSWORD` | App password |
| `ALERT_EMAIL` | Destination email |
| `WEBHOOK_URL` | Slack/Discord webhook |

### 5. Local testing

```bash
pip install -r requirements.txt
python scraper/main.py
```

## Adding New Sources

In `scraper/sources.py`, implement the source class pattern:

```python
class BloombergSource:
    NAME = "Bloomberg"
    FEEDS = ["https://feeds.bloomberg.com/markets/news.rss"]

    def fetch(self) -> list[dict]:
        articles = []
        feed = feedparser.parse(self.FEEDS[0])
        for entry in feed.entries[:15]:
            articles.append(make_article(
                source=self.NAME,
                title=entry.get("title", ""),
                link=entry.get("link", ""),
                published_date=entry.get("published", ""),
                content=entry.get("summary", ""),
            ))
        return articles

# Register:
ACTIVE_SOURCES = [NYTimesSource(), ReutersSource(), BloombergSource()]
```

## Project Structure

```
macro-lab/
├── .github/
│   └── workflows/
│       └── scrape.yml          ← Hourly cron job
├── scraper/
│   ├── main.py                 ← Orchestrator
│   ├── sources.py              ← Multi-source scraper
│   ├── scoring.py              ← BM25 + dynamic normalization
│   ├── storage.py              ← Sliding window persistence
│   ├── alerts.py               ← Telegram / Email / Webhooks
│   └── renderer.py             ← Static HTML generator
├── data.json                   ← 7-day rolling corpus
├── index.html                  ← Auto-generated dashboard
├── vercel.json                 ← Vercel deployment config
├── requirements.txt
└── .gitignore
```

## Resource Footprint

| Metric | Estimate |
|--------|----------|
| RAM peak (GitHub Actions) | ~80–120 MB |
| CPU time per run | 2–5 min |
| GitHub Actions minutes/month | ~50–70 (within free tier) |
| Repo size growth | Stable: 7-day purge keeps data.json ~1–3 MB |
| Vercel bandwidth | Negligible (static HTML) |

## Evolution Roadmap

### 3-Month Plan
- [ ] Add Reuters, Bloomberg (via RSS), FT sources
- [ ] Telegram alert integration (env vars are ready)
- [ ] Per-source score weighting configuration (YAML config file)
- [ ] Add Chart.js sparkline of hourly score evolution to dashboard
- [ ] Score history JSON (`score_history.json`) for trend visualization

### 6-Month Plan
- [ ] Lightweight semantic embeddings via `sentence-transformers` (distilbert, ~80MB, runs fine on Actions)
- [ ] Macro regime detection: classify each run as Risk-On / Risk-Off / Crisis
- [ ] Synthetic macro index: weighted composite of top-10 article scores
- [ ] Multi-language sources (Le Monde, Nikkei English, Handelsblatt)
- [ ] Weekly digest email with top articles + score chart
- [ ] Optional: Supabase free tier for historical score series (replacing JSON once needed)

### Longer Term (Quant Lab)
- [ ] Factor signals extracted from article themes (geopolitical risk index, policy uncertainty index)
- [ ] Correlation analysis: article score spikes vs VIX, SPX, DXY next-day moves
- [ ] Backtest framework: did high scores predict next-day vol expansion?
- [ ] Python Jupyter notebook connected to data.json for ad-hoc analysis
