"""
renderer.py - Generates index.html from scored articles.
Pure Python + embedded vanilla JS. No external frameworks.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_FILE = Path(__file__).parent.parent / "index.html"
DATA_FILE = Path(__file__).parent.parent / "data.json"
TOP_N = 20


def _format_themes(themes: list) -> str:
    if not themes:
        return ""
    labels = {
        "war_conflict": "⚔️ War/Conflict",
        "market_crash": "💥 Market Crash",
        "monetary_emergency": "🚨 Fed Emergency",
        "sovereign_default": "💀 Default",
        "banking_crisis": "🏦 Banking Crisis",
        "sanctions_major": "🚫 Sanctions",
        "geopolitical_shock": "🌐 Geo Shock",
    }
    tags = [labels.get(t, t) for t in themes]
    return "".join(f'<span class="theme-tag">{tag}</span>' for tag in tags)


def _format_score(score: float) -> str:
    cls = "score-high" if score >= 70 else ("score-mid" if score >= 40 else "score-low")
    return f'<span class="score {cls}">{score:.1f}</span>'


def _build_article_card(article: dict, idx: int) -> str:
    title = article.get("title", "No title")
    link = article.get("link", "#")
    source = article.get("source", "Unknown")
    pub_date = article.get("published_date", "")
    score = article.get("score_normalized", 0)
    themes = article.get("themes", [])

    # Truncate content for preview
    content = article.get("content", "")
    preview = content[:280].replace("<", "&lt;").replace(">", "&gt;")
    if len(content) > 280:
        preview += "…"

    return f"""
<article class="card" data-score="{score}" data-themes="{','.join(themes)}">
  <div class="card-header">
    <span class="source-badge">{source}</span>
    {_format_score(score)}
    {_format_themes(themes)}
  </div>
  <h3><a href="{link}" target="_blank" rel="noopener">{title}</a></h3>
  <p class="preview">{preview}</p>
  <div class="card-footer">
    <time>{pub_date[:25] if pub_date else 'Unknown date'}</time>
  </div>
</article>"""


def render_html(all_articles: list[dict], top_articles: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    top_cards = "\n".join(_build_article_card(a, i) for i, a in enumerate(top_articles))
    all_cards = "\n".join(_build_article_card(a, i) for i, a in enumerate(
        sorted(all_articles, key=lambda x: x.get("score_normalized", 0), reverse=True)
    ))

    threshold = top_articles[0].get("alert_threshold", "N/A") if top_articles else "N/A"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Macro Lab — {now}</title>
  <style>
    :root {{
      --bg: #0d1117;
      --surface: #161b22;
      --border: #30363d;
      --text: #c9d1d9;
      --text-muted: #8b949e;
      --accent: #58a6ff;
      --green: #3fb950;
      --yellow: #d29922;
      --red: #f85149;
      --tag-bg: #1f2937;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.6;
    }}
    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 16px 24px;
      display: flex;
      align-items: center;
      gap: 16px;
      position: sticky;
      top: 0;
      z-index: 100;
    }}
    header h1 {{ font-size: 18px; font-weight: 700; color: var(--accent); }}
    header .meta {{ color: var(--text-muted); font-size: 12px; margin-left: auto; }}
    .toggle-btn {{
      background: var(--tag-bg);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      transition: background 0.2s;
    }}
    .toggle-btn:hover {{ background: var(--border); }}
    .toggle-btn.active {{ background: var(--accent); color: #000; border-color: var(--accent); }}
    main {{ max-width: 960px; margin: 0 auto; padding: 24px 16px; }}
    .stats-bar {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 16px;
      margin-bottom: 20px;
      display: flex;
      gap: 24px;
      flex-wrap: wrap;
    }}
    .stat {{ display: flex; flex-direction: column; }}
    .stat-label {{ font-size: 11px; text-transform: uppercase; color: var(--text-muted); }}
    .stat-value {{ font-size: 20px; font-weight: 700; color: var(--accent); }}
    .view {{ display: none; }}
    .view.active {{ display: block; }}
    .section-title {{
      font-size: 13px;
      text-transform: uppercase;
      color: var(--text-muted);
      letter-spacing: 0.08em;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 12px;
      transition: border-color 0.15s;
    }}
    .card:hover {{ border-color: var(--accent); }}
    .card-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
      flex-wrap: wrap;
    }}
    .source-badge {{
      background: var(--tag-bg);
      color: var(--text-muted);
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 4px;
      border: 1px solid var(--border);
    }}
    .score {{
      font-size: 12px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
    }}
    .score-high {{ background: rgba(63,185,80,0.15); color: var(--green); }}
    .score-mid {{ background: rgba(210,153,34,0.15); color: var(--yellow); }}
    .score-low {{ background: rgba(139,148,158,0.1); color: var(--text-muted); }}
    .theme-tag {{
      font-size: 11px;
      background: rgba(248,81,73,0.15);
      color: var(--red);
      padding: 2px 8px;
      border-radius: 4px;
      border: 1px solid rgba(248,81,73,0.3);
    }}
    .card h3 {{ font-size: 15px; margin-bottom: 6px; }}
    .card h3 a {{ color: var(--text); text-decoration: none; }}
    .card h3 a:hover {{ color: var(--accent); }}
    .preview {{ color: var(--text-muted); font-size: 13px; margin-bottom: 8px; }}
    .card-footer {{ font-size: 11px; color: var(--text-muted); }}
    .filter-bar {{
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }}
    .filter-btn {{
      background: var(--tag-bg);
      color: var(--text-muted);
      border: 1px solid var(--border);
      padding: 4px 12px;
      border-radius: 20px;
      cursor: pointer;
      font-size: 12px;
    }}
    .filter-btn:hover, .filter-btn.active {{
      background: var(--accent);
      color: #000;
      border-color: var(--accent);
    }}
    @media (max-width: 600px) {{
      header {{ flex-wrap: wrap; }}
      .stats-bar {{ gap: 12px; }}
    }}
  </style>
</head>
<body>
<header>
  <h1>📊 Macro Lab</h1>
  <button class="toggle-btn active" id="toggleBtn" onclick="toggleView()">
    Top {TOP_N} View
  </button>
  <div class="meta">Updated: {now} · {len(all_articles)} articles (7d) · Alert threshold: {threshold}</div>
</header>

<main>
  <div class="stats-bar">
    <div class="stat">
      <span class="stat-label">Articles (7d)</span>
      <span class="stat-value">{len(all_articles)}</span>
    </div>
    <div class="stat">
      <span class="stat-label">Top Articles</span>
      <span class="stat-value">{len(top_articles)}</span>
    </div>
    <div class="stat">
      <span class="stat-label">Critical Alerts</span>
      <span class="stat-value">{sum(1 for a in all_articles if a.get('themes'))}</span>
    </div>
    <div class="stat">
      <span class="stat-label">Alert Threshold</span>
      <span class="stat-value">{threshold}</span>
    </div>
  </div>

  <!-- TOP VIEW -->
  <div class="view active" id="view-top">
    <div class="section-title">Top {TOP_N} Articles This Hour</div>
    <div class="filter-bar">
      <button class="filter-btn active" onclick="filterCards('all', this)">All</button>
      <button class="filter-btn" onclick="filterCards('war_conflict', this)">War/Conflict</button>
      <button class="filter-btn" onclick="filterCards('monetary_emergency', this)">Fed</button>
      <button class="filter-btn" onclick="filterCards('market_crash', this)">Market Crash</button>
      <button class="filter-btn" onclick="filterCards('sanctions_major', this)">Sanctions</button>
    </div>
    <div id="cards-top">
{top_cards}
    </div>
  </div>

  <!-- FULL HISTORY VIEW -->
  <div class="view" id="view-all">
    <div class="section-title">Complete History — Last 7 Days ({len(all_articles)} articles)</div>
    <div class="filter-bar">
      <button class="filter-btn active" onclick="filterCards('all', this, 'all')">All</button>
      <button class="filter-btn" onclick="filterCards('war_conflict', this, 'all')">War/Conflict</button>
      <button class="filter-btn" onclick="filterCards('monetary_emergency', this, 'all')">Fed</button>
      <button class="filter-btn" onclick="filterCards('market_crash', this, 'all')">Market Crash</button>
      <button class="filter-btn" onclick="filterCards('sanctions_major', this, 'all')">Sanctions</button>
    </div>
    <div id="cards-all">
{all_cards}
    </div>
  </div>
</main>

<script>
  let currentView = 'top';

  function toggleView() {{
    const btn = document.getElementById('toggleBtn');
    const topView = document.getElementById('view-top');
    const allView = document.getElementById('view-all');
    if (currentView === 'top') {{
      topView.classList.remove('active');
      allView.classList.add('active');
      btn.textContent = 'Full History View';
      btn.classList.add('active');
      currentView = 'all';
    }} else {{
      allView.classList.remove('active');
      topView.classList.add('active');
      btn.textContent = 'Top {TOP_N} View';
      currentView = 'top';
    }}
  }}

  function filterCards(theme, btn, viewId) {{
    const containerId = viewId === 'all' ? 'cards-all' : 'cards-top';
    const container = document.getElementById(containerId);
    const cards = container.querySelectorAll('.card');

    // Update active filter button
    const parent = btn.parentElement;
    parent.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    cards.forEach(card => {{
      if (theme === 'all') {{
        card.style.display = '';
      }} else {{
        const themes = card.dataset.themes || '';
        card.style.display = themes.includes(theme) ? '' : 'none';
      }}
    }});
  }}
</script>
</body>
</html>"""


def generate(all_articles: list[dict], top_articles: list[dict]) -> None:
    html = render_html(all_articles, top_articles)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated {OUTPUT_FILE} ({len(html):,} bytes)")
