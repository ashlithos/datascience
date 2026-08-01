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
    python tools/components.py spectrum       # -> reports/spectrum_data_prep.html
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


# ---------------------------------------------------------------------------
# The data-prep autonomy spectrum. Not generated from the DB — this is the
# design artifact behind the cleaning stage: which prep decisions the agent may
# make alone, and which ones need Maya. Bands are ordered by the only thing
# that matters for the interface: how confident the agent can be that a single
# right answer exists.
BANDS = [
    dict(band="var(--c1)", posture="Just do it", conf=4, conf_lbl="settled",
         h="Decided in the skill",
         rule="One right answer, nothing lost. Surfacing it would only spend attention.",
         tasks=["parse timestamps to one type", "trim whitespace on join keys",
                'read <code>"1,024"</code> as a number', "detect encoding &amp; delimiter",
                "drop fully empty columns"],
         sees_dt="Maya sees", sees="Nothing."),
    dict(band="var(--c2)", posture="Do it, then say so", conf=3, conf_lbl="strong convention",
         h="Agent assumes, Maya is told",
         rule="One dominant convention — but values change, so it goes on the record.",
         tasks=["<code>emea</code> / <code>E.M.E.A</code> / <code>&quot; EMEA &quot;</code> → <code>EMEA</code>",
                "exact duplicate <code>session_id</code> rows",
                "timestamps → one timezone", "consistent week boundaries"],
         sees_dt="Maya sees", sees="One line in the answer: &ldquo;normalised 4 region "
                 "spellings, dropped 35 duplicate rows.&rdquo; Undoable after, not gated before."),
    dict(band="var(--tertiary)", posture="Propose, then wait", conf=2, conf_lbl="contested",
         h="Agent offers options, Maya approves",
         rule="Several defensible answers, and the choice moves the conclusion.",
         tasks=["missing <code>user_id</code> — flag-and-keep vs drop",
                "negative <code>duration_sec</code> — exclude / clamp / null",
                "outlier sessions — winsorise vs keep",
                "near-duplicates (same user, same minute)", "backfill cutoff"],
         sees_dt="Maya sees", sees="The approval panel — each option with a sample and "
                 "how many rows it moves. Approve or skip, per issue."),
    dict(band="var(--error)", posture="Ask — only Maya knows", conf=0, conf_lbl="not in the data",
         h="Maya provides, agent records",
         rule="Not a confidence problem — the answer isn't in the data, so no default is safe.",
         tasks=["&ldquo;active user&rdquo; = distinct <code>user_id</code>?",
                "<code>duration_sec</code> vs <code>active_sec</code>",
                "exclude internal / QA accounts?",
                "which error rate is worth interrupting for",
                "<code>user_type</code> vs <code>plan</code>"],
         sees_dt="Maya gives", sees="A question, asked once — then written into "
                 "<code>data_dictionary.md</code> and never asked again."),
]

_ARROW_R = ("<svg viewBox='0 0 200 9' preserveAspectRatio='none' aria-hidden='true'>"
            "<line x1='0' y1='4.5' x2='193' y2='4.5' stroke='currentColor' stroke-width='1'/>"
            "<polygon points='200,4.5 191,0.5 191,8.5' fill='currentColor'/></svg>")
_ARROW_L = ("<svg viewBox='0 0 200 9' preserveAspectRatio='none' aria-hidden='true'>"
            "<line x1='7' y1='4.5' x2='200' y2='4.5' stroke='currentColor' stroke-width='1'/>"
            "<polygon points='0,4.5 9,0.5 9,8.5' fill='currentColor'/></svg>")
_ARROW_L_DASH = ("<svg viewBox='0 0 200 9' preserveAspectRatio='none' aria-hidden='true'>"
                 "<line x1='7' y1='4.5' x2='200' y2='4.5' stroke='currentColor' stroke-width='1'"
                 " stroke-dasharray='4 4'/>"
                 "<polygon points='0,4.5 9,0.5 9,8.5' fill='currentColor'/></svg>")


def spectrum_body():
    """Body markup for the spectrum (shared by the report page and the artifact)."""
    rail = "".join(f"<span style=\"--band:{b['band']}\"></span>" for b in BANDS)
    cards = ""
    for b in BANDS:
        dots = "".join(
            f"<i class='{'on' if i < b['conf'] else ('off' if b['conf'] == 0 else '')}'></i>"
            for i in range(4))
        tasks = "".join(f"<li>{t}</li>" for t in b["tasks"])
        cards += f"""
      <article class="spec-band" style="--band:{b['band']}">
        <div class="spec-band__posture">{b['posture']}</div>
        <h2 class="spec-band__h">{b['h']}</h2>
        <p class="spec-band__rule">{b['rule']}</p>
        <div class="spec-meter">
          <div class="spec-meter__dots">{dots}</div>
          <div class="spec-meter__lbl">{b['conf_lbl']}</div>
        </div>
        <ul class="spec-tasks">{tasks}</ul>
        <dl class="spec-band__sees"><dt>{b['sees_dt']}</dt><dd>{b['sees']}</dd></dl>
      </article>"""
    return f"""
    <div class="spec-root">
      <header class="spec-head">
        <span class="m3-label">Data preparation · autonomy design</span>
        <h1 class="spec-title">How much of the cleaning should Maya ever see?</h1>
        <p class="spec-lede">Each prep task sits where it does for one reason: <b>how confident
        the agent can be that a single right answer exists</b>. As that confidence falls, control
        and transparency get handed back.</p>
      </header>

      <div class="spec-axes">
        <div class="spec-axis"><span>Agent confidence in one right answer</span>{_ARROW_L}</div>
        <div class="spec-axis">{_ARROW_R}<span>User control &amp; transparency</span></div>
      </div>

      <div class="spec-rail">{rail}</div>
      <div class="spec-grid">{cards}</div>

      <div class="spec-return">{_ARROW_L_DASH}
        <span><b>Answered once, a task moves left.</b> A ratified definition becomes a written
        rule the agent applies silently — the spectrum is a starting position, not a fixed one.</span>
      </div>

      <section class="spec-note">
        <h3>Placing a new task</h3>
        <p>Each <em>yes</em> moves it one band right. Get it wrong on the left and you ship silent
        wrong answers; wrong on the right and you get twelve dialogs, all approved unread.</p>
        <ol class="spec-test">
          <li>Is there more than one defensible answer?</li>
          <li>Would a different choice change the conclusion Maya acts on?</li>
          <li>Does answering it need knowledge that isn't in the data?</li>
        </ol>
      </section>
    </div>"""


def spectrum():
    return _write("spectrum_data_prep.html",
                  _page("Data-prep autonomy spectrum", spectrum_body()))


BUILDERS = {"key-driver": card_key_driver, "alert": card_alert, "cleaning": panel_cleaning,
            "spectrum": spectrum}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "all":
        for b in BUILDERS.values():
            b()
    elif cmd in BUILDERS:
        BUILDERS[cmd]()
    else:
        print("usage: components.py [key-driver|alert|cleaning|spectrum|all]")
        sys.exit(1)
