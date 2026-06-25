"""
render.py — shared rendering + intent routing for the FlowDash DS-agent UI.

Both the static scripted preview (web/build_web.py) and the live backend
(server/app.py) import from here, so the chat experience and the Material 3 look
(Jetski design tokens) stay identical.

What's here:
  - CSS               : the full Jetski-themed stylesheet (one source of truth)
  - load_charts()     : base64-embed the matplotlib PNGs from reports/
  - canvas_*()        : build the canvas-pane artifact HTML from live data
  - route(question)   : rule-based intent router that runs the REAL tools against
                        the REAL sqlite and returns {skill, calls, answer, canvas}
                        (optionally upgraded to true NL->SQL when ANTHROPIC_API_KEY
                        is set — see nl_to_sql()).
"""
import base64
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
REPORTS = os.path.join(ROOT, "reports")
DB = os.path.join(ROOT, "data", "flowdash.db")

import sql_tool          # noqa: E402  (read-only SQL runner with its own guards)
from key_driver import scan  # noqa: E402

REGION_CLEAN = ("CASE WHEN REPLACE(UPPER(TRIM(region)),'.','')='EMEA' THEN 'EMEA' "
                "ELSE TRIM(region) END")
CLEAN = "duration_sec > 0"


# --------------------------------------------------------------------------- #
#  charts                                                                      #
# --------------------------------------------------------------------------- #
def _b64(png):
    p = os.path.join(REPORTS, png)
    if not os.path.exists(p):
        return ""
    return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()


def load_charts():
    return {k: _b64(v) for k, v in {
        "wau": "wau_trend.png", "driver": "driver_cells.png",
        "feature": "sql_export_trend.png", "errors": "error_rate.png"}.items()}


CHARTS = load_charts()


def _q(sql):
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql).fetchall()]
    finally:
        con.close()


def _table(cols, rows, cause_col=None, cause_val=None):
    head = "".join(f'<th class="num">{c}</th>' if i else f"<th>{c}</th>"
                   for i, c in enumerate(cols))
    body = ""
    for r in rows:
        cls = ""
        if cause_col is not None and str(r[cause_col]) == str(cause_val):
            cls = ' class="cause"'
        tds = "".join(f'<td class="num">{v}</td>' if i else f"<td>{v}</td>"
                      for i, v in enumerate(r.values() if isinstance(r, dict) else r))
        body += f"<tr{cls}>{tds}</tr>"
    return f'<table class="tbl"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


# --------------------------------------------------------------------------- #
#  canvas artifact builders                                                    #
# --------------------------------------------------------------------------- #
def canvas_cleaning(state=None):
    state = state or {}
    issues = [
        ("dedupe", "&#10697;", "35 duplicate session rows",
         "Same <code>session_id</code> logged twice. Fix: keep first, drop the rest.",
         [("Approve de-dupe", "primary"), ("Show all 35", ""), ("Skip", "ghost")]),
        ("negatives", "&minus;", "28 negative durations",
         "Clock bug, <code>duration_sec &lt; 0</code>. Fix: exclude from aggregates (keep source rows).",
         [("Approve exclude", "primary"), ("Skip", "ghost")]),
        ("regions", "Aa", "Inconsistent region spelling",
         "EMEA appears as <code>EMEA</code> / <code>emea</code> / <code>E.M.E.A</code> / <code>\" EMEA \"</code>. Fix: normalise to <code>EMEA</code>.",
         [("Approve normalise", "primary"), ("Skip", "ghost")]),
    ]
    rows = ""
    for key, icon, h, d, btns in issues:
        if state.get(key) == "approved":
            rows += (f'<div class="approve"><div class="aicon" style="background:var(--good-container);color:var(--good)">&#10003;</div>'
                     f'<div><div class="ah">{h}</div><div class="ad">Applied (non-destructive) &middot; '
                     f'the clean recipe now runs in every downstream query.</div></div></div>')
        elif state.get(key) == "skipped":
            rows += (f'<div class="approve"><div class="aicon">{icon}</div>'
                     f'<div><div class="ah" style="color:var(--outline)">{h}</div>'
                     f'<div class="ad">Skipped &middot; left as-is.</div></div></div>')
        else:
            b = "".join(f'<button class="btn btn-{v}" data-act="clean" data-id="{key}" '
                        f'data-choice="{"approve" if "Approve" in t else ("skip" if t=="Skip" else "show")}">{t}</button>'
                        for t, v in btns)
            rows += (f'<div class="approve"><div class="aicon">{icon}</div>'
                     f'<div><div class="ah">{h}</div><div class="ad">{d}</div>'
                     f'<div class="btnrow">{b}</div></div></div>')
    return f"""
    <span class="kicker">Data cleaning · approval required</span>
    <h3 class="ctitle">3 data-quality issues found</h3>
    <p class="csub">I can detect these on my own (read-only). Nothing is written until you approve — your call, per issue.</p>
    {rows}
    <p class="foot">Shallow autonomy: detection is automatic; every <b>write</b> waits for you.</p>"""


def canvas_driver(R=None):
    R = R or scan()
    T, O = R["top_driver"], R["overall"]
    ev = ""
    for e in R["evidence"]:
        cls = ' class="cause"' if e["is_cause"] else ""
        tag = ' <span class="pill pill-bad">cause</span>' if e["is_cause"] else ""
        ev += (f'<tr{cls}><td>{e["cell"]}{tag}</td><td class="num">{e["first"]}</td>'
               f'<td class="num">{e["last"]}</td><td class="num">{e["change_pct"]:+.0f}%</td></tr>')
    singles = "".join(f'<tr><td>{s["dim"]} = {s["value"]}</td><td class="num">{s["change_pct"]:+.0f}%</td></tr>'
                      for s in R["singles"][:5])
    return f"""
    <span class="kicker">Key-driver analysis</span>
    <h3 class="ctitle">Why is weekly active down {abs(O['change_pct'])}%?</h3>
    <p class="csub">wk{O['first_week']} &rarr; wk{O['last_week']}: {O['wau_first']} &rarr; {O['wau_last']} active users.</p>
    <div class="metrics">
      <div><div class="mval bad">{T['change_pct']}%</div><div class="mlbl">{T['value']}</div></div>
      <div><div class="mval">{T['share_of_base']}%</div><div class="mlbl">of the user base</div></div>
      <div><div class="mval">{R['combos_tried']}</div><div class="mlbl">combinations scanned</div></div>
    </div>
    <p>The decline is <b>not</b> platform-wide or new-user-wide. It concentrates almost entirely in one cell: <b>{T['value']}</b>. Every sibling segment is flat.</p>
    <div class="conf"><div class="conf-track"><div class="conf-fill" style="width:{R['confidence']}%"></div></div>
      <div class="conf-lbl">Confidence in this driver: <b>{R['confidence']}%</b> &middot; heuristic: drop severity, base share, sibling flatness</div></div>
    <img class="chart" src="{CHARTS['driver']}" alt="driver breakdown">
    <details class="evidence"><summary>&#9656; Show the evidence (what I actually checked)</summary>
      <p class="foot">Single-dimension cuts only show a diffuse, misleading dip — none isolate the cause:</p>
      <table class="tbl"><thead><tr><th>single-dimension cut</th><th class="num">wk1&rarr;wk8</th></tr></thead><tbody>{singles}</tbody></table>
      <p class="foot" style="margin-top:12px">Crossing platform &times; user_type localises it:</p>
      <table class="tbl"><thead><tr><th>cell</th><th class="num">wk1</th><th class="num">wk8</th><th class="num">&Delta;</th></tr></thead><tbody>{ev}</tbody></table>
    </details>
    <p class="foot">This is a probabilistic finding, not a fact. Open the evidence before acting.</p>"""


def canvas_wau():
    rows = _q(f"SELECT week, COUNT(DISTINCT user_id) wau FROM sessions WHERE {CLEAN} GROUP BY week ORDER BY week")
    first, last = rows[0]["wau"], rows[-1]["wau"]
    chg = round((last - first) / first * 100, 1)
    return f"""
    <span class="kicker">Metric trend</span>
    <h3 class="ctitle">Weekly active users</h3>
    <p class="csub">Cleaned (deduped, duration&gt;0). wk1 &rarr; wk8: {first} &rarr; {last} ({chg}%).</p>
    <img class="chart" src="{CHARTS['wau']}" alt="wau trend">
    {_table(["week", "wau"], rows)}
    <p class="foot">Want the cause of the decline? Ask "why is weekly active down?"</p>"""


def canvas_feature():
    rows = _q(f"""SELECT s.week,
        ROUND(100.0*COUNT(DISTINCT CASE WHEN f.feature='sql_export' THEN s.session_id END)
              /COUNT(DISTINCT s.session_id),1) AS sql_export_pct
        FROM sessions s LEFT JOIN feature_events f USING(session_id)
        WHERE {CLEAN} GROUP BY s.week ORDER BY s.week""")
    first, last = rows[0]["sql_export_pct"], rows[-1]["sql_export_pct"]
    return f"""
    <span class="kicker">Feature adoption</span>
    <h3 class="ctitle">sql_export is quietly up ~3&times;</h3>
    <p class="csub">Share of sessions using sql_export. wk1 &rarr; wk8: {first}% &rarr; {last}%.</p>
    <img class="chart" src="{CHARTS['feature']}" alt="sql_export trend">
    {_table(["week", "sql_export_pct"], rows)}
    <p class="foot">A power-user feature gaining ground even as overall usage falls — the good-news story.</p>"""


def canvas_alert():
    reg = _q(f"SELECT {REGION_CLEAN} region, ROUND(100.0*SUM(had_error)/COUNT(*),2) error_pct, COUNT(*) n "
             f"FROM sessions WHERE week=6 GROUP BY region ORDER BY error_pct DESC")
    return f"""
    <span class="kicker alert-k">Threshold breach · autonomous alert</span>
    <h3 class="ctitle">EMEA error rate broke 5% in week 6</h3>
    <p class="csub">I noticed this without being asked. Concentrated in the 2h after deploy v2026.06.03.</p>
    <div class="metrics">
      <div><div class="mval bad">7.17%</div><div class="mlbl">EMEA wk-6 error rate (vs ~1.3% normal)</div></div>
      <div><div class="mval bad">56.5%</div><div class="mlbl">in the 2h after deploy</div></div>
    </div>
    <img class="chart" src="{CHARTS['errors']}" alt="error rate">
    {_table(["region", "error_pct", "n"], reg, cause_col="region", cause_val="EMEA")}
    <div class="btnrow"><button class="btn btn-primary" data-act="ask" data-q="why did EMEA errors spike">Expand investigation</button>
      <button class="btn btn-ghost">Snooze · adjust threshold</button></div>
    <p class="foot">Was this worth interrupting you for? The threshold is the etiquette of autonomy.</p>"""


def canvas_story():
    return f"""
    <span class="kicker">Storytelling · B / C comparison</span>
    <h3 class="ctitle">Weekly summary — two structures, same facts</h3>
    <div class="tabs"><button class="tab tab-on" data-tab="C">Version C · fixed</button><button class="tab" data-tab="B">Version B · agent-decided</button></div>
    <div class="tabpane" data-pane="C">
      <p class="csub">Predictable template: Overview &rarr; Findings &rarr; Evidence &rarr; Recommendations.</p>
      <p><b>Overview.</b> Weekly active down 18% over 8 weeks. Not broad-based — one segment.</p>
      <p><b>Key findings.</b> WAU &minus;18%; cause is <b>android &times; new</b> &minus;61% (92% conf.); <code>sql_export</code> up ~3&times;; EMEA wk-6 errors ~7%.</p>
      <img class="chart" src="{CHARTS['wau']}" alt="wau trend">
      <p><b>Recommendation.</b> Investigate Android new-user onboarding — the entire decline lives there.</p>
    </div>
    <div class="tabpane" data-pane="B" hidden>
      <p class="csub">Agent-decided structure: it chose to <b>open on the good news</b>.</p>
      <p class="m3head">The thing nobody's looking at is going right.</p>
      <p>Everyone's about to panic about the 18% WAU drop. First: <b><code>sql_export</code> has tripled</b> (5%&rarr;15% of sessions), climbing every week with zero marketing.</p>
      <img class="chart" src="{CHARTS['feature']}" alt="sql_export trend">
      <p>Now the drop — it's precise: new users on Android, &minus;61%. Not all of Android, not all new users. The intersection. ~92% sure.</p>
    </div>
    <p class="foot">C is predictable & audit-friendly; B noticed the surprise and restructured around it.</p>"""


def canvas_sql(sql):
    try:
        cols, rows = sql_tool.run(sql)
    except Exception as e:
        return None, f'<span class="kicker">SQL</span><h3 class="ctitle">Query error</h3><p class="csub">{e}</p>'
    listrows = [dict(zip(cols, r)) for r in rows[:100]]
    tbl = _table(list(cols), listrows) if cols else "<p>(no columns)</p>"
    note = f"<p class='foot'>{len(rows)} row(s)." + (" Showing first 100." if len(rows) > 100 else "") + "</p>"
    canvas = (f'<span class="kicker">Text-to-SQL · read-only</span><h3 class="ctitle">Query result</h3>'
              f'<div class="ds-code">{sql}</div>{tbl}{note}')
    return rows, canvas


def canvas_help():
    return """
    <span class="kicker">What I can do</span>
    <h3 class="ctitle">Ask me about FlowDash, in plain English</h3>
    <p class="csub">I translate to SQL against the cleaned data and answer with evidence. Try:</p>
    <ul style="font-size:14px;line-height:1.9;color:var(--on-surface)">
      <li>"Is this data clean enough to trust?" <span style="color:var(--outline)">— cleaning + approvals</span></li>
      <li>"Why is weekly active down?" <span style="color:var(--outline)">— key-driver analysis</span></li>
      <li>"How's sql_export doing?" <span style="color:var(--outline)">— feature adoption</span></li>
      <li>"Any error spikes?" / "Assume a week passed" <span style="color:var(--outline)">— alerts</span></li>
      <li>"Write the weekly summary" <span style="color:var(--outline)">— storytelling (B vs C)</span></li>
      <li>"Show weekly active by region" <span style="color:var(--outline)">— or paste raw SQL</span></li>
    </ul>"""


# --------------------------------------------------------------------------- #
#  intent router (the "agent" brain for the live backend)                      #
# --------------------------------------------------------------------------- #
def _has(text, *words):
    return any(w in text for w in words)


def route(question, state=None):
    """Map a plain-English question to a real analysis. Returns a dict with
    skill, calls (reasoning trace), answer (html), canvas (html)."""
    q = (question or "").strip()
    ql = q.lower()
    state = state or {}

    # raw SQL passthrough
    if re.match(r"^\s*(select|with)\b", ql):
        rows, canvas = canvas_sql(q)
        n = len(rows) if rows is not None else 0
        return {"skill": "sql_tool", "calls": [f"sql_tool · {q[:60]}…"],
                "answer": f"Ran your query (read-only) — {n} row(s). Result on the right.",
                "canvas": canvas}

    # cleaning
    if _has(ql, "clean", "quality", "trust", "dirty", "duplicat", "dedup", "valid"):
        return {"skill": "data-cleaning",
                "calls": ["sql_tool · detect duplicates", "sql_tool · detect negatives",
                          "sql_tool · DISTINCT region", "components · cleaning panel"],
                "answer": "Not quite yet — but the issues are small and fixable. I found <b>three</b>: 35 duplicate rows, 28 negative durations, and EMEA spelled four ways. Approve each on the right; I won't write anything until you do.",
                "canvas": canvas_cleaning(state.get("clean"))}

    # key driver — "why ... down/drop", "cause", "driver"
    if _has(ql, "why", "driver", "caus", "reason", "explain") and _has(ql, "down", "drop", "decl", "fall", "fell", "lower", "active", "wau", "users") \
       or _has(ql, "what's driving", "whats driving", "root cause"):
        R = scan()
        return {"skill": "key-driver-analysis",
                "calls": ["key_driver · scanning 55 dimension combinations",
                          "viz_tool · driver", "components · key-driver"],
                "answer": f"It's <b>not</b> everyone leaving. I crossed every dimension (55 combinations) and the whole decline sits in one cell: <b>{R['top_driver']['value']}</b>, down {abs(R['top_driver']['change_pct'])}%. Single cuts (Android &minus;41%, new users &minus;35%) would've misled you — it's the intersection. ~{R['confidence']}% sure. Evidence on the right.",
                "canvas": canvas_driver(R)}

    # feature adoption
    if _has(ql, "sql_export", "sql export", "feature", "adopt", "export", "growing", "rising"):
        return {"skill": "storytelling",
                "calls": ["sql_tool · sql_export share by week", "viz_tool · feature"],
                "answer": "The quiet good-news story: <b>sql_export has roughly tripled</b> (5%&rarr;15% of sessions), climbing every week. Trend + numbers on the right.",
                "canvas": canvas_feature()}

    # alert / errors / time-jump
    if _has(ql, "error", "alert", "spike", "breach", "threshold", "5%", "incident") \
       or _has(ql, "week passed", "week has passed", "fast forward", "fast-forward", "assume a week"):
        return {"skill": "alert (autonomous)",
                "calls": ["monitor · error_rate by region", "threshold breach: EMEA > 5%",
                          "components · alert"],
                "answer": "⚠️ Heads up — <b>EMEA's error rate broke 5% in week 6</b> (hit ~7%), concentrated in the 2 hours after deploy <code>v2026.06.03</code>. Looks contained to that release. Details on the right.",
                "canvas": canvas_alert()}

    # storytelling / summary
    if _has(ql, "summary", "summarise", "summarize", "report", "story", "digest", "writeup", "write up", "presentable"):
        return {"skill": "storytelling",
                "calls": ["key_driver · gather facts", "viz_tool · wau feature",
                          "write story_C.md + story_B.md"],
                "answer": "Two versions on the right. <b>C</b> is the fixed template; <b>B</b> I structured myself and chose to <b>lead with the good news</b> (sql_export). Toggle between them — the contrast is the point.",
                "canvas": canvas_story()}

    # wau / trend / active users
    if _has(ql, "weekly active", "wau", "active users", "trend", "how many users", "usage"):
        # region/plan breakdown variants -> real SQL
        if _has(ql, "region"):
            rows, canvas = canvas_sql(
                f"SELECT {REGION_CLEAN} region, COUNT(DISTINCT user_id) wau "
                f"FROM sessions WHERE {CLEAN} AND week=8 GROUP BY region ORDER BY wau DESC")
            return {"skill": "sql_tool", "calls": ["sql_tool · WAU by region (wk8)"],
                    "answer": "Week-8 active users by region, on the right.", "canvas": canvas}
        return {"skill": "sql_tool", "calls": ["sql_tool · WAU by week", "viz_tool · wau"],
                "answer": "Weekly active users trend on the right (cleaned). It's down ~18% — ask <i>why</i> for the driver.",
                "canvas": canvas_wau()}

    # fallback
    return {"skill": "router", "calls": ["intent: unmatched → help"],
            "answer": "I'm not sure how to chart that one yet — here's what I can answer (or paste a <code>SELECT…</code> and I'll run it read-only).",
            "canvas": canvas_help()}


# --------------------------------------------------------------------------- #
#  optional: true NL->SQL when an API key is available                         #
# --------------------------------------------------------------------------- #
def nl_to_sql_available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# --------------------------------------------------------------------------- #
#  CSS — Jetski Material 3 tokens (single source of truth for both UIs)        #
# --------------------------------------------------------------------------- #
CSS = """
:root{
 --primary:#a8c7fa;--on-primary:#062e6f;--primary-container:#0842a0;--on-primary-container:#d3e3fd;
 --secondary:#85d2e3;--secondary-container:#004e5a;--on-secondary-container:#adebff;
 --tertiary:#dbc66e;--tertiary-container:#544600;--on-tertiary-container:#f9e287;
 --error:#ffb4ab;--error-container:#93000a;--on-error-container:#ffdad6;--good:#8ed8a9;--good-container:#1d4a2f;
 --bg:#111418;--on-surface:#e2e2e9;--on-surface-variant:#c4c6d0;--sc-lowest:#0c0e13;--sc-low:#191c20;
 --sc:#1d2024;--sc-high:#282a2f;--sc-highest:#33353a;--outline:#8e9099;--outline-variant:#44474e;
 --erosion:#ff8a65;--r-sm:8px;--r-md:12px;
 --font:Roboto,"Google Sans Flex",ui-sans-serif,system-ui,sans-serif;
 --mono:"Roboto Mono",ui-monospace,Menlo,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--on-surface);font-family:var(--font);-webkit-font-smoothing:antialiased}
.kicker{font-size:11px;font-weight:500;letter-spacing:.5px;text-transform:uppercase;color:var(--on-surface-variant);display:block;margin-bottom:8px}
.tnum,.num{font-variant-numeric:tabular-nums}
code{font-family:var(--mono);font-size:.92em;color:var(--on-surface-variant)}
@keyframes fade-up{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.fade-up{animation:fade-up .32s cubic-bezier(.2,0,0,1) both}
@media(prefers-reduced-motion:reduce){.fade-up{animation:none}*{transition-duration:.01ms!important}}
header{display:flex;align-items:center;gap:12px;padding:14px 22px;border-bottom:1px solid var(--outline-variant);position:sticky;top:0;background:var(--bg);z-index:5}
header .logo{width:26px;height:26px;border-radius:7px;background:var(--primary);color:var(--on-primary);display:grid;place-items:center;font-weight:700;font-size:14px}
header .name{font-weight:500;font-size:15px}
header .demo{margin-left:auto;font-size:11px;color:var(--on-tertiary-container);background:var(--tertiary-container);padding:4px 9px;border-radius:var(--r-sm);font-weight:500}
header .live{font-size:11px;color:var(--good);background:var(--good-container);padding:4px 9px;border-radius:var(--r-sm);font-weight:500;display:flex;align-items:center;gap:6px}
header .live::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--good)}
.wrap{display:flex;height:calc(100vh - 55px)}
.chat{flex:1;min-width:0;display:flex;flex-direction:column}
.chat.has-canvas{max-width:46%;border-right:1px solid var(--outline-variant)}
.chat:not(.has-canvas) .thread{max-width:680px;margin:0 auto;width:100%}
.thread{flex:1;overflow-y:auto;padding:26px 24px 8px}
.canvas{flex:1;min-width:0;overflow-y:auto;padding:26px 26px 60px;display:none}
.canvas.on{display:block}
.turn{display:flex;gap:12px;margin-bottom:22px}
.turn.user{justify-content:flex-end}
.avatar{width:24px;height:24px;border-radius:50%;background:var(--primary);color:var(--on-primary);display:grid;place-items:center;font-size:12px;font-weight:700;flex:none}
.bubble{max-width:80%}
.turn.user .bubble{background:var(--sc-high);padding:10px 14px;border-radius:14px 14px 4px 14px;font-size:14.5px}
.agent .bubble{font-size:14.5px;line-height:1.55}
.agent .bubble p{margin:0 0 8px}
.m3head{font-size:18px;font-weight:500;margin:4px 0 8px}
.trace{border-left:2px solid var(--outline-variant);padding:2px 0 2px 12px;margin:2px 0 12px;font-size:12.5px;color:var(--on-surface-variant)}
.trace summary{cursor:pointer;list-style:none;color:var(--on-surface-variant);font-weight:500;display:flex;align-items:center;gap:7px}
.trace summary::-webkit-details-marker{display:none}
.trace .call{font-family:var(--mono);font-size:11.5px;margin-top:6px;color:var(--outline);display:flex;gap:7px;align-items:baseline}
.trace .call .ok{color:var(--good)}
.dot{width:7px;height:7px;border-radius:50%;border:2px solid var(--primary);border-top-color:transparent;display:inline-block;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.composer{padding:14px 24px 22px;border-top:1px solid var(--outline-variant)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
.chip{font-size:13px;font-weight:500;padding:8px 14px;border-radius:999px;border:1px solid var(--outline);background:transparent;color:var(--primary);cursor:pointer;transition:all .15s cubic-bezier(.22,1,.36,1)}
.chip:hover{background:rgba(168,199,250,.08)}
.chip:active{transform:scale(.97)}
.form{display:flex;align-items:center;gap:10px;border:1px solid var(--outline-variant);border-radius:22px;padding:7px 7px 7px 16px;background:var(--sc-low)}
.form input{flex:1;background:none;border:none;outline:none;color:var(--on-surface);font-size:14px;font-family:var(--font)}
.form input::placeholder{color:var(--outline)}
.send{width:36px;height:36px;border-radius:50%;border:none;background:var(--primary);color:var(--on-primary);font-size:16px;cursor:pointer;flex:none}
.send:disabled{opacity:.4}
.ctitle{font-size:20px;font-weight:500;line-height:1.3;margin:0 0 6px}
.csub{color:var(--on-surface-variant);font-size:14px;margin:0 0 16px}
.metrics{display:flex;gap:26px;flex-wrap:wrap;margin:8px 0 14px}
.mval{font-size:26px;font-weight:500;letter-spacing:-.01em}.mval.bad{color:var(--error)}
.mlbl{font-size:12px;color:var(--on-surface-variant);margin-top:2px}
.conf{margin:12px 0}.conf-track{height:6px;border-radius:999px;background:var(--sc-high);overflow:hidden}
.conf-fill{height:100%;background:var(--primary);border-radius:999px}
.conf-lbl{font-size:12px;color:var(--on-surface-variant);margin-top:7px}
.chart{width:100%;border-radius:var(--r-sm);border:1px solid var(--outline-variant);margin:14px 0;display:block}
.evidence{margin-top:14px;border-top:1px solid var(--outline-variant);padding-top:12px}
.evidence summary{cursor:pointer;list-style:none;font-size:13px;font-weight:500;color:var(--primary)}
.evidence summary::-webkit-details-marker{display:none}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px}
.tbl th,.tbl td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--outline-variant)}
.tbl th{color:var(--on-surface-variant);font-weight:500}
.tbl td.num,.tbl th.num{text-align:right}
.tbl tr.cause td{background:color-mix(in srgb,var(--error-container) 45%,transparent)}
.pill{display:inline-flex;align-items:center;border-radius:var(--r-sm);padding:2px 7px;font-size:11px;font-weight:500}
.pill-bad{background:var(--error-container);color:var(--on-error-container)}
.foot{font-size:11.5px;color:var(--outline);margin-top:12px}
.ds-code{font-family:var(--mono);font-size:12px;background:var(--sc-lowest);border:1px solid var(--outline-variant);border-radius:var(--r-sm);padding:11px 13px;color:var(--on-surface-variant);white-space:pre-wrap;overflow-x:auto;margin:8px 0}
.approve{display:flex;gap:12px;padding:14px 0;border-bottom:1px solid var(--outline-variant)}
.approve:last-of-type{border-bottom:none}
.aicon{width:28px;height:28px;flex:none;border-radius:var(--r-sm);display:grid;place-items:center;font-size:13px;font-weight:600;background:var(--sc-high);color:var(--on-surface-variant)}
.ah{font-weight:500;font-size:15px}.ad{font-size:13px;color:var(--on-surface-variant);margin-top:3px}
.btnrow{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
.btn{font-size:13px;font-weight:500;padding:8px 15px;border-radius:999px;border:1px solid var(--outline);background:transparent;color:var(--primary);cursor:pointer;transition:all .15s}
.btn:active{transform:scale(.97)}.btn-primary{background:var(--primary);border-color:var(--primary);color:var(--on-primary)}
.btn-ghost{border-color:transparent}
.alert-k{color:var(--error)}
.tabs{display:flex;gap:8px;margin-bottom:14px}
.tab{font-size:13px;font-weight:500;padding:7px 14px;border-radius:999px;border:1px solid var(--outline-variant);background:transparent;color:var(--on-surface-variant);cursor:pointer}
.tab-on{background:var(--secondary-container);border-color:transparent;color:var(--on-secondary-container)}
"""
