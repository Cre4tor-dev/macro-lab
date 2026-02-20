"""
renderer.py - Generates index.html from scored articles.

Features:
  - Toggle Top20 / Full 7-day history
  - Date filter (dropdown per day)
  - Multi-theme filter (combinable, OR logic)
  - Keyword search bar
  - Score gradient + tooltip with matched keywords
  - Visual alert pulse for critical articles
  - Mini dashboard: articles/day bar chart + theme donut (Chart.js CDN)
  - Compact / detailed mode toggle
"""

import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUTPUT_FILE = Path(__file__).parent.parent / "index.html"
TOP_N = 20

THEME_LABELS = {
    "war_conflict":        "⚔️ War/Conflict",
    "market_crash":        "💥 Market Crash",
    "monetary_emergency":  "🚨 Fed Emergency",
    "sovereign_default":   "💀 Default",
    "banking_crisis":      "🏦 Banking Crisis",
    "sanctions_major":     "🚫 Sanctions",
    "geopolitical_shock":  "🌐 Geo Shock",
    "recession":           "📉 Recession",
    "inflation":           "🔥 Inflation",
    "oil_energy":          "🛢️ Oil/Energy",
    "market_volatility":   "📊 Volatility",
    "central_bank":        "🏛️ Central Bank",
}


def _score_color(score: float) -> str:
    s = max(0.0, min(100.0, score))
    if s >= 70:
        return "#3fb950"
    elif s >= 50:
        return "#d29922"
    elif s >= 30:
        return "#f0883e"
    else:
        return "#8b949e"


def _parse_pub_day(date_str: str) -> str:
    """Return YYYY-MM-DD or empty string."""
    if not date_str:
        return ""
    # Try email/RFC date (Mon, 01 Jan 2024 12:00:00 +0000)
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    # ISO formats
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str[:len(fmt)], fmt)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            continue
    return date_str[:10] if len(date_str) >= 10 else ""


def _build_chart_data(all_articles: list) -> tuple:
    today = datetime.now(timezone.utc).date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    per_day = {d: 0 for d in days}
    per_theme = defaultdict(int)

    for a in all_articles:
        d = _parse_pub_day(a.get("published_date", ""))
        if d in per_day:
            per_day[d] += 1
        for t in a.get("themes", []):
            per_theme[t] += 1

    return per_day, dict(per_theme)


def _build_card(article: dict) -> str:
    raw_title = article.get("title", "No title")
    title = raw_title.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    link = article.get("link", "#")
    source = article.get("source", "Unknown")
    pub_raw = article.get("published_date", "")
    pub_day = _parse_pub_day(pub_raw)
    score = article.get("score_normalized", 0.0)
    themes = article.get("themes", [])
    keywords = article.get("matched_keywords", [])
    threshold = article.get("alert_threshold", 75.0)
    is_alert = (score >= threshold) or len(themes) > 0

    color = _score_color(score)

    theme_html = "".join(
        f'<span class="theme-tag">{THEME_LABELS.get(t, t)}</span>'
        for t in themes
    )

    content = article.get("content", "")
    preview = content[:300].replace("<", "&lt;").replace(">", "&gt;")
    if len(content) > 300:
        preview += "&#8230;"

    kw_display = ", ".join(keywords[:8]) if keywords else "—"
    tooltip = f"Score: {score:.2f} | Seuil: {threshold:.1f} | Sentiment: {article.get('sentiment_label','?')}| Mots-cles: {kw_display}"

    # data-text: searchable text blob (title + content snippet, lowercased)
    searchable = (raw_title + " " + content[:600]).lower().replace('"', "").replace("\n", " ")

    alert_cls = " card-alert" if is_alert else ""
    alert_badge = '<span class="alert-badge">🚨 ALERT</span>' if is_alert else ""
    kw_hint = f'<span class="kw-hint">🔑 {", ".join(keywords[:5])}</span>' if keywords else ""

    return (
        f'<article class="card{alert_cls}" '
        f'data-score="{score:.2f}" data-date="{pub_day}" '
        f'data-themes="{",".join(themes)}" data-text="{searchable[:800]}">\n'
        f'  <div class="card-header">\n'
        f'    <span class="source-badge">{source}</span>\n'
        f'    <span class="score-pill" '
        f'style="background:color-mix(in srgb,{color} 18%,transparent);'
        f'color:{color};border-color:color-mix(in srgb,{color} 35%,transparent)" '
        f'title="{tooltip}">{score:.1f} <sup>ℹ</sup></span>\n'
        f'    {theme_html}\n'
        f'    {alert_badge}\n'
        f'  </div>\n'
        f'  <h3 class="card-title"><a href="{link}" target="_blank" rel="noopener">{title}</a></h3>\n'
        f'  <p class="preview card-detail">{preview}</p>\n'
        f'  <div class="card-footer card-detail">\n'
        f'    <time datetime="{pub_day}">{pub_raw[:25] if pub_raw else "Unknown date"}</time>\n'
        f'    {kw_hint}\n'
        f'  </div>\n'
        f'</article>'
    )


def render_html(all_articles: list, top_articles: list) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    threshold_val = top_articles[0].get("alert_threshold", 75.0) if top_articles else 75.0
    threshold_display = f"{threshold_val:.1f}" if isinstance(threshold_val, float) else str(threshold_val)

    alert_count = sum(
        1 for a in all_articles
        if a.get("themes") or a.get("score_normalized", 0) >= threshold_val
    )
    avg_score = round(
        sum(a.get("score_normalized", 0) for a in all_articles) / max(len(all_articles), 1), 1
    )

    per_day, per_theme = _build_chart_data(all_articles)
    chart_days_labels = json.dumps([d[5:] for d in per_day.keys()])   # "MM-DD" shorter labels
    chart_days_values = json.dumps(list(per_day.values()))
    chart_theme_labels = json.dumps([THEME_LABELS.get(k, k) for k in per_theme.keys()])
    chart_theme_values = json.dumps(list(per_theme.values()))

    today = datetime.now(timezone.utc).date()
    date_options = "\n".join(
        f'<option value="{(today - timedelta(days=i)).isoformat()}">'
        f'{(today - timedelta(days=i)).strftime("%a %d %b")}</option>'
        for i in range(7)
    )

    top_cards = "\n".join(_build_card(a) for a in top_articles)
    all_cards = "\n".join(_build_card(a) for a in sorted(
        all_articles, key=lambda x: x.get("score_normalized", 0), reverse=True
    ))

    theme_filter_btns = "\n".join(
        f'<button class="filter-btn" data-theme="{k}" onclick="toggleTheme(this)">'
        f'{THEME_LABELS[k]}</button>'
        for k in THEME_LABELS.keys()
    )

    # We split the template into a plain string (no f-string) for the JS block
    # to avoid having to escape every single brace.
    js_block = """
let currentView = 'top';
let activeThemes = new Set();
let isCompact = false;

function setView(v) {
  currentView = v;
  document.getElementById('view-top').classList.toggle('active', v === 'top');
  document.getElementById('view-all').classList.toggle('active', v === 'all');
  document.getElementById('viewBtn').classList.toggle('on', v === 'top');
  document.getElementById('viewAllBtn').classList.toggle('on', v === 'all');
  applyFilters();
}

function toggleCompact() {
  isCompact = !isCompact;
  document.body.classList.toggle('compact-mode', isCompact);
  const btn = document.getElementById('compactBtn');
  btn.classList.toggle('on', isCompact);
  btn.textContent = isCompact ? '⊟ Détails' : '⊞ Compact';
}

function toggleTheme(btn) {
  const theme = btn.dataset.theme;
  if (activeThemes.has(theme)) {
    activeThemes.delete(theme);
    btn.classList.remove('on');
  } else {
    activeThemes.add(theme);
    btn.classList.add('on');
  }
  document.getElementById('themeAll').classList.toggle('on', activeThemes.size === 0);
  applyFilters();
}

function clearThemes() {
  activeThemes.clear();
  document.querySelectorAll('.filter-btn[data-theme]').forEach(b => b.classList.remove('on'));
  document.getElementById('themeAll').classList.add('on');
  applyFilters();
}

function applyFilters() {
  const query   = document.getElementById('searchInput').value.toLowerCase().trim();
  const dateVal = document.getElementById('dateSelect').value;
  const cid     = currentView === 'top' ? 'cards-top' : 'cards-all';
  const cards   = document.getElementById(cid).querySelectorAll('.card');

  let visible = 0;
  cards.forEach(card => {
    const text   = (card.dataset.text || '') + ' ' + (card.querySelector('.card-title')?.textContent || '').toLowerCase();
    const date   = card.dataset.date  || '';
    const themes = card.dataset.themes || '';

    const matchSearch = !query    || text.includes(query);
    const matchDate   = !dateVal  || date === dateVal;
    const matchTheme  = activeThemes.size === 0 || [...activeThemes].some(t => themes.includes(t));

    const show = matchSearch && matchDate && matchTheme;
    card.classList.toggle('hidden', !show);
    if (show) visible++;
  });

  const rc = document.getElementById('resultCount');
  if (rc) rc.textContent = visible + ' article' + (visible !== 1 ? 's' : '') + ' affiché' + (visible !== 1 ? 's' : '');
}

// ── CHARTS ──
const gridColor = '#30363d';
const tickColor = '#8b949e';
const axisOpts  = { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10 } } };

""" + f"""
new Chart(document.getElementById('chartDays'), {{
  type: 'bar',
  data: {{
    labels: {chart_days_labels},
    datasets: [{{
      data: {chart_days_values},
      backgroundColor: 'rgba(88,166,255,0.45)',
      borderColor: '#58a6ff',
      borderWidth: 1,
      borderRadius: 4
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ x: axisOpts, y: {{ ...axisOpts, ticks: {{ ...axisOpts.ticks, stepSize: 1 }} }} }}
  }}
}});

const themeValues = {chart_theme_values};
if (themeValues.length > 0 && themeValues.some(v => v > 0)) {{
  new Chart(document.getElementById('chartThemes'), {{
    type: 'doughnut',
    data: {{
      labels: {chart_theme_labels},
      datasets: [{{
        data: themeValues,
        backgroundColor: ['#f85149','#d29922','#3fb950','#58a6ff','#ff7b72','#79c0ff','#56d364','#e3b341','#ffa657','#d2a8ff','#7ee787','#a5d6ff'],
        borderWidth: 0
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: true,
      plugins: {{ legend: {{ display: true, position: 'right',
        labels: {{ color: '#8b949e', font: {{ size: 10 }}, boxWidth: 12, padding: 6 }}
      }} }}
    }}
  }});
}} else {{
  document.getElementById('chartThemes').parentElement.innerHTML +=
    '<p style="color:#8b949e;font-size:12px;text-align:center;margin-top:30px">Aucun thème critique détecté</p>';
}}

applyFilters();
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Macro Lab — {now}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg:#0d1117; --surface:#161b22; --surface2:#1c2128;
      --border:#30363d; --text:#c9d1d9; --muted:#8b949e;
      --accent:#58a6ff; --green:#3fb950; --yellow:#d29922;
      --red:#f85149; --tag-bg:#1f2937; --alert:#ff7b72;
    }}
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;line-height:1.6}}
    header{{background:var(--surface);border-bottom:1px solid var(--border);padding:12px 20px;display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:200;flex-wrap:wrap}}
    header h1{{font-size:17px;font-weight:700;color:var(--accent);white-space:nowrap}}
    .header-meta{{color:var(--muted);font-size:11px;margin-left:auto;text-align:right;line-height:1.5}}
    .btn{{background:var(--tag-bg);color:var(--text);border:1px solid var(--border);padding:5px 12px;border-radius:6px;cursor:pointer;font-size:12px;transition:all .15s;white-space:nowrap}}
    .btn:hover{{background:var(--border)}}
    .btn.on{{background:var(--accent);color:#000;border-color:var(--accent)}}
    main{{max-width:980px;margin:0 auto;padding:20px 16px}}
    .dashboard{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:14px}}
    .stat-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:11px 14px}}
    .stat-label{{font-size:10px;text-transform:uppercase;color:var(--muted);letter-spacing:.05em}}
    .stat-value{{font-size:22px;font-weight:700;color:var(--accent);margin-top:2px}}
    .charts-row{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}}
    @media(max-width:600px){{.charts-row{{grid-template-columns:1fr}}}}
    .chart-box{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px}}
    .chart-title{{font-size:10px;text-transform:uppercase;color:var(--muted);margin-bottom:10px;letter-spacing:.06em}}
    .chart-box canvas{{max-height:155px}}
    .toolbar{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px 14px;margin-bottom:14px;display:flex;flex-direction:column;gap:9px}}
    .toolbar-row{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
    .toolbar-label{{font-size:11px;color:var(--muted);white-space:nowrap;min-width:64px}}
    .search-input{{background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 10px;font-size:13px;flex:1;min-width:160px;outline:none}}
    .search-input:focus{{border-color:var(--accent)}}
    .date-select{{background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:12px;cursor:pointer;outline:none}}
    .result-count{{font-size:11px;color:var(--muted);margin-left:auto}}
    .filter-btn{{background:var(--tag-bg);color:var(--muted);border:1px solid var(--border);padding:3px 10px;border-radius:20px;cursor:pointer;font-size:11px;transition:all .15s}}
    .filter-btn:hover{{border-color:var(--accent);color:var(--text)}}
    .filter-btn.on{{background:rgba(248,81,73,.18);color:var(--red);border-color:rgba(248,81,73,.5)}}
    .section-title{{font-size:11px;text-transform:uppercase;color:var(--muted);letter-spacing:.08em;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border)}}
    .card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:10px;transition:border-color .15s;position:relative}}
    .card:hover{{border-color:var(--accent)}}
    .card-alert{{border-color:rgba(255,123,114,.45)!important;animation:pulse 2.5s ease-in-out infinite}}
    @keyframes pulse{{0%,100%{{box-shadow:0 0 0 1px rgba(255,123,114,.15)}}50%{{box-shadow:0 0 0 3px rgba(255,123,114,.35)}}}}
    .card-header{{display:flex;align-items:center;gap:7px;margin-bottom:7px;flex-wrap:wrap}}
    .source-badge{{background:var(--tag-bg);color:var(--muted);font-size:10px;padding:2px 7px;border-radius:4px;border:1px solid var(--border)}}
    .score-pill{{font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;border:1px solid;cursor:help;position:relative}}
    .score-pill:hover::after{{content:attr(title);position:absolute;bottom:calc(100% + 6px);left:0;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:7px 10px;border-radius:6px;font-size:11px;white-space:pre-wrap;max-width:300px;z-index:999;pointer-events:none;line-height:1.5;font-weight:400}}
    .theme-tag{{font-size:10px;background:rgba(248,81,73,.12);color:var(--red);padding:2px 7px;border-radius:4px;border:1px solid rgba(248,81,73,.25)}}
    .alert-badge{{font-size:10px;background:rgba(255,123,114,.2);color:var(--alert);padding:2px 7px;border-radius:4px;border:1px solid rgba(255,123,114,.4);font-weight:700}}
    .card-title{{font-size:14px;margin-bottom:5px;line-height:1.4}}
    .card-title a{{color:var(--text);text-decoration:none}}
    .card-title a:hover{{color:var(--accent)}}
    .preview{{color:var(--muted);font-size:12px;margin-bottom:7px;line-height:1.5}}
    .card-footer{{font-size:11px;color:var(--muted);display:flex;gap:12px;flex-wrap:wrap}}
    .kw-hint{{color:#58a6ff77;font-size:10px}}
    .compact-mode .card-detail{{display:none!important}}
    .compact-mode .card{{padding:9px 14px;margin-bottom:6px}}
    .hidden{{display:none!important}}
    .view{{display:none}}.view.active{{display:block}}
  </style>
</head>
<body>

<header>
  <h1>📊 Macro Lab</h1>
  <button class="btn on" id="viewBtn" onclick="setView('top')">Top {TOP_N}</button>
  <button class="btn" id="viewAllBtn" onclick="setView('all')">Historique 7j</button>
  <button class="btn" id="compactBtn" onclick="toggleCompact()">⊞ Compact</button>
  <div class="header-meta">Mis à jour: {now}<br>Seuil alerte: {threshold_display} · {alert_count} alertes</div>
</header>

<main>
  <div class="dashboard">
    <div class="stat-card"><div class="stat-label">Articles 7j</div><div class="stat-value">{len(all_articles)}</div></div>
    <div class="stat-card"><div class="stat-label">Top sélectionnés</div><div class="stat-value">{len(top_articles)}</div></div>
    <div class="stat-card"><div class="stat-label">Alertes critiques</div><div class="stat-value" style="color:var(--alert)">{alert_count}</div></div>
    <div class="stat-card"><div class="stat-label">Score moyen</div><div class="stat-value">{avg_score}</div></div>
    <div class="stat-card"><div class="stat-label">Seuil alerte</div><div class="stat-value">{threshold_display}</div></div>
  </div>

  <div class="charts-row">
    <div class="chart-box">
      <div class="chart-title">Articles par jour (7 jours)</div>
      <canvas id="chartDays"></canvas>
    </div>
    <div class="chart-box">
      <div class="chart-title">Thèmes critiques détectés</div>
      <canvas id="chartThemes"></canvas>
    </div>
  </div>

  <div class="toolbar">
    <div class="toolbar-row">
      <span class="toolbar-label">🔍 Recherche</span>
      <input class="search-input" id="searchInput" type="text" placeholder="Ukraine, Fed, S&amp;P 500, inflation…" oninput="applyFilters()">
      <span class="toolbar-label" style="min-width:36px">📅 Jour</span>
      <select class="date-select" id="dateSelect" onchange="applyFilters()">
        <option value="">Tous</option>
        {date_options}
      </select>
      <span class="result-count" id="resultCount"></span>
    </div>
    <div class="toolbar-row">
      <span class="toolbar-label">🏷 Thèmes</span>
      <button class="filter-btn on" id="themeAll" onclick="clearThemes()">Tous</button>
      {theme_filter_btns}
    </div>
  </div>

  <div class="view active" id="view-top">
    <div class="section-title">Top {TOP_N} articles — cette heure</div>
    <div id="cards-top">{top_cards}</div>
  </div>

  <div class="view" id="view-all">
    <div class="section-title">Historique complet — 7 derniers jours ({len(all_articles)} articles)</div>
    <div id="cards-all">{all_cards}</div>
  </div>
</main>

<script>
{js_block}
</script>
</body>
</html>"""


def generate(all_articles: list, top_articles: list) -> None:
    html = render_html(all_articles, top_articles)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated {OUTPUT_FILE} ({len(html):,} bytes, {len(all_articles)} articles)")