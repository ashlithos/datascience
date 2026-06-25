"""
components.py — render the demo's MOCK UI components as self-contained HTML.

These are the "summoned components" the agent drops into the conversation: a
key-driver finding card, an autonomous alert banner, a cleaning approval panel.
Each is a single .html file (CSS inlined from assets/theme.css, charts embedded
as base64) so it opens anywhere. Every analytical card includes a collapsible
"▸ Show the evidence" block — the human takeover point.

Usage:
    python tools/components.py key-driver     # -> reports/card_key_driver.html
    python tools/components.py alert          # -> reports/card_alert.html
    python tools/components.py cleaning       # -> reports/panel_cleaning.html
    python tools/components.py all
"""
import base64
import os
import sqlite3
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
ROOT = os.path.join(HERE, "..")
DB = os.path.join(ROOT, "data", "flowdash.db")
OUT = os.path.join(ROOT, "reports")
THEME = os.path.join(ROOT, "assets", "theme.css")
REGION_CLEAN = ("CASE WHEN REPLACE(UPPER(TRIM(region)),'.','')='EMEA' THEN 'EMEA' "
                "ELSE TRIM(region) END")
os.makedirs(OUT, exist_ok=True)


def _css():
    return open(THEME).read()


def _img(png_name):
    """base64-embed a chart PNG (build it via viz_tool first)."""
    p = os.path.join(OUT, png_name)
    if not os.path.exists(p):
        return ""
    b = base64.b64encode(open(p, "rb").read()).decode()
    return f'<img class="ds-chart" alt="{png_name}" src="data:image/png;base64,{b}">'


def _page(title, body):
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"
            f"<style>{_css()}</style></head><body class='ds-root'>{body}</body></html>")


def _write(name, html):
    p = os.path.join(OUT, name)
    open(p, "w").write(html)
    print(p)
    return p


# ---------------------------------------------------------------------------
def card_key_driver():
    from key_driver import scan
    r = scan()
    t, o = r["top_driver"], r["overall"]
    rows = ""
    for e in r["evidence"]:
        cls = " class='is-cause'" if e["is_cause"] else ""
        tag = " <span class='ds-pill ds-pill--bad'>cause</span>" if e["is_cause"] else ""
        rows += (f"<tr{cls}><td>{e['cell']}{tag}</td>"
                 f"<td class='num'>{e['first']}</td><td class='num'>{e['last']}</td>"
                 f"<td class='num'>{e['change_pct']:+.0f}%</td></tr>")
    singles = "".join(
        f"<tr><td>{s['dim']} = {s['value']}</td><td class='num'>{s['change_pct']:+.0f}%</td></tr>"
        for s in r["singles"][:5])
    conf = r["confidence"]
    body = f"""
    <div class="ds-card">
      <div class="ds-card__kicker">Key-driver analysis</div>
      <h2 class="ds-card__title">Why is weekly active down {abs(o['change_pct'])}%?</h2>
      <p class="ds-card__sub">wk{o['first_week']} → wk{o['last_week']}: {o['wau_first']} → {o['wau_last']} active users.</p>
      <div class="ds-metrics">
        <div class="ds-metric ds-metric--bad"><div class="ds-metric__val">{t['change_pct']}%</div>
          <div class="ds-metric__lbl">{t['value']}</div></div>
        <div class="ds-metric"><div class="ds-metric__val">{t['share_of_base']}%</div>
          <div class="ds-metric__lbl">of the user base</div></div>
        <div class="ds-metric"><div class="ds-metric__val">{r['combos_tried']}</div>
          <div class="ds-metric__lbl">combinations scanned</div></div>
      </div>
      <p>The decline is <b>not</b> platform-wide or new-user-wide. It concentrates almost
      entirely in one cell: <b>{t['value']}</b>. Every sibling segment is flat.</p>
      <div class="ds-conf">
        <div class="ds-conf__track"><div class="ds-conf__fill" style="width:{conf}%"></div></div>
        <div class="ds-conf__label">Confidence in this driver: <b>{conf}%</b>
          &nbsp;·&nbsp; heuristic: drop severity, base share, sibling flatness</div>
      </div>
      {_img('driver_cells.png')}
      <details class="ds-evidence">
        <summary>▸ Show the evidence (what I actually checked)</summary>
        <p class="ds-foot">Single-dimension cuts only show a diffuse, misleading dip —
        no single cut isolates the cause:</p>
        <table class="ds-table"><thead><tr><th>single-dimension cut</th><th class='num'>wk1→wk8</th></tr></thead>
        <tbody>{singles}</tbody></table>
        <p class="ds-foot" style="margin-top:12px">Crossing platform × user_type localises it
        (🔴 = the cause cell):</p>
        <table class="ds-table"><thead><tr><th>cell</th><th class='num'>wk1</th><th class='num'>wk8</th><th class='num'>Δ</th></tr></thead>
        <tbody>{rows}</tbody></table>
        <p class="ds-foot" style="margin-top:12px">Reproduce:</p>
        <div class="ds-code">python tools/key_driver.py
python tools/sql_tool.py "SELECT week, COUNT(DISTINCT user_id) wau FROM sessions
  WHERE duration_sec>0 AND platform='android' AND user_type='new' GROUP BY week"</div>
      </details>
      <p class="ds-foot">⚠️ This is a probabilistic finding, not a fact. Open the evidence before acting.</p>
    </div>"""
    return _write("card_key_driver.html", _page("Key driver — WAU", body))


# ---------------------------------------------------------------------------
def card_alert():
    c = sqlite3.connect(DB)
    rate = c.execute(
        f"SELECT ROUND(100.0*SUM(had_error)/COUNT(*),2) FROM sessions "
        f"WHERE week=6 AND {REGION_CLEAN}='EMEA'").fetchone()[0]
    dep = c.execute("SELECT deploy_id, deployed_at, notes FROM deployments "
                    "WHERE deploy_id='v2026.06.03'").fetchone()
    win = c.execute(
        "SELECT COUNT(*), SUM(had_error) FROM sessions WHERE week=6 "
        f"AND {REGION_CLEAN}='EMEA' AND started_at BETWEEN '2026-06-03T14:00:00' "
        "AND '2026-06-03T16:00:00'").fetchone()
    c.close()
    win_rate = round(100 * win[1] / win[0], 1) if win[0] else 0
    body = f"""
    <div class="ds-card ds-alert">
      <div class="ds-card__kicker">Threshold breach · autonomous alert</div>
      <h2 class="ds-card__title">EMEA error rate broke 5% in week 6</h2>
      <p class="ds-card__sub">I noticed this without being asked. Want me to dig in?</p>
      <div class="ds-metrics">
        <div class="ds-metric ds-metric--bad"><div class="ds-metric__val">{rate}%</div>
          <div class="ds-metric__lbl">EMEA week-6 error rate (vs ~1.3% normal)</div></div>
        <div class="ds-metric ds-metric--bad"><div class="ds-metric__val">{win_rate}%</div>
          <div class="ds-metric__lbl">in the 2h after deploy</div></div>
      </div>
      <p>Spike concentrates in the <b>~2 hours after deploy {dep[0]}</b>
      ({dep[1].replace('T',' ')}) and is confined to <b>EMEA</b>. Other regions stayed ~1–2%.</p>
      <p class="ds-foot">Release note: “{dep[2]}”</p>
      {_img('error_rate.png')}
      <details class="ds-evidence">
        <summary>▸ Show the evidence</summary>
        <div class="ds-code">python tools/sql_tool.py "SELECT
  CASE WHEN REPLACE(UPPER(TRIM(region)),'.','')='EMEA' THEN 'EMEA' ELSE TRIM(region) END region_clean,
  ROUND(100.0*SUM(had_error)/COUNT(*),2) err_pct
FROM sessions WHERE week=6 GROUP BY region_clean ORDER BY err_pct DESC"</div>
      </details>
      <div class="ds-btnrow">
        <button class="ds-btn ds-btn--primary">Expand investigation</button>
        <button class="ds-btn ds-btn--ghost">Snooze · adjust threshold</button>
      </div>
    </div>"""
    return _write("card_alert.html", _page("Alert — EMEA errors", body))


# ---------------------------------------------------------------------------
def panel_cleaning():
    c = sqlite3.connect(DB)
    dups = c.execute("SELECT COUNT(*) FROM (SELECT session_id FROM sessions "
                     "GROUP BY session_id HAVING COUNT(*)>1)").fetchone()[0]
    negs = c.execute("SELECT COUNT(*) FROM sessions WHERE duration_sec<0").fetchone()[0]
    spell = [r[0] for r in c.execute("SELECT DISTINCT region FROM sessions "
             "WHERE REPLACE(UPPER(TRIM(region)),'.','')='EMEA' ORDER BY 1")]
    sample = c.execute("SELECT session_id, region, duration_sec FROM sessions "
                       "WHERE duration_sec<0 LIMIT 3").fetchall()
    c.close()
    samp = "".join(f"<tr><td>{s[0]}</td><td>{s[1]}</td><td class='num'>{s[2]}</td></tr>" for s in sample)
    body = f"""
    <div class="ds-card">
      <div class="ds-card__kicker">Data cleaning · approval required</div>
      <h2 class="ds-card__title">I found 3 data-quality issues. Approve fixes?</h2>
      <p class="ds-card__sub">I can detect these on my own (read-only). I will not write
      anything until you approve — your call, per issue.</p>

      <div class="ds-approve">
        <div class="ds-approve__icon">⧉</div>
        <div class="ds-approve__body">
          <div class="ds-approve__h">{dups} duplicate session rows</div>
          <div class="ds-approve__d">Same <code>session_id</code> logged twice. Proposed fix:
          keep the first occurrence, drop the rest.</div>
          <div class="ds-btnrow"><button class="ds-btn ds-btn--primary">Approve de-dupe</button>
            <button class="ds-btn">Show all {dups}</button><button class="ds-btn ds-btn--ghost">Skip</button></div>
        </div>
      </div>

      <div class="ds-approve">
        <div class="ds-approve__icon">−</div>
        <div class="ds-approve__body">
          <div class="ds-approve__h">{negs} negative durations</div>
          <div class="ds-approve__d">Clock bug — <code>duration_sec &lt; 0</code>. Proposed fix:
          exclude from aggregates (don't delete source rows). Sample:</div>
          <table class="ds-table" style="margin-top:8px"><thead><tr><th>session_id</th><th>region</th><th class='num'>duration_sec</th></tr></thead>
          <tbody>{samp}</tbody></table>
          <div class="ds-btnrow"><button class="ds-btn ds-btn--primary">Approve exclude</button>
            <button class="ds-btn ds-btn--ghost">Skip</button></div>
        </div>
      </div>

      <div class="ds-approve">
        <div class="ds-approve__icon">Aa</div>
        <div class="ds-approve__body">
          <div class="ds-approve__h">Inconsistent region spelling</div>
          <div class="ds-approve__d">EMEA appears as: {", ".join(f"<code>{repr(s)}</code>" for s in spell)}.
          Proposed fix: normalise all to <code>EMEA</code>.</div>
          <div class="ds-btnrow"><button class="ds-btn ds-btn--primary">Approve normalise</button>
            <button class="ds-btn ds-btn--ghost">Skip</button></div>
        </div>
      </div>
      <p class="ds-foot">Shallow autonomy: detection is automatic; every <b>write</b> waits for you.</p>
    </div>"""
    return _write("panel_cleaning.html", _page("Cleaning — approvals", body))


BUILDERS = {"key-driver": card_key_driver, "alert": card_alert, "cleaning": panel_cleaning}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "all":
        for b in BUILDERS.values():
            b()
    elif cmd in BUILDERS:
        BUILDERS[cmd]()
    else:
        print("usage: components.py [key-driver|alert|cleaning|all]")
        sys.exit(1)
