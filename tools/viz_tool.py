"""
viz_tool.py — matplotlib charts for the demo, themed to match assets/theme.css.

Each subcommand queries FlowDash and writes a PNG into reports/. Charts are dark,
minimal, and use the same accent/semantic palette as the HTML components so a
chart embedded in a card looks native.

Usage:
    python tools/viz_tool.py wau         # WAU trend, with android x new overlay
    python tools/viz_tool.py driver      # change-% bar chart of the winning crossing cells
    python tools/viz_tool.py feature      # sql_export quiet-growth trend
    python tools/viz_tool.py errors       # week-6 error rate by region + EMEA weekly line
    python tools/viz_tool.py all          # build them all
"""
import os
import sqlite3
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
DB = os.path.join(HERE, "..", "data", "flowdash.db")
OUT = os.path.join(HERE, "..", "reports")
os.makedirs(OUT, exist_ok=True)

# palette mirrored from the Jetski design system (jetski-design/globals.css)
BG, SURF, GRID = "#111418", "#191c20", "#44474e"
TEXT, DIM = "#e2e2e9", "#c4c6d0"
ACCENT, GOOD, WARN = "#a8c7fa", "#8ed8a9", "#dbc66e"   # blue / green / amber(warning)
BAD = "#ff8a65"                                         # coral — erosion/negative only
NEUTRAL = "#bfc6dc"                                     # blue-grey — non-cause series
REGION_CLEAN = ("CASE WHEN REPLACE(UPPER(TRIM(region)),'.','')='EMEA' THEN 'EMEA' "
                "ELSE TRIM(region) END")
CLEAN = "duration_sec > 0"


def con():
    return sqlite3.connect(DB)


def _style(ax, fig):
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(SURF)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=DIM, labelsize=9)
    ax.yaxis.label.set_color(DIM); ax.xaxis.label.set_color(DIM)
    ax.title.set_color(TEXT)
    ax.grid(True, color=GRID, lw=0.6, alpha=0.5)


def save(fig, name):
    p = os.path.join(OUT, name)
    fig.savefig(p, dpi=130, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(p)
    return p


def chart_wau():
    c = con()
    weeks = list(range(1, 9))
    total = [c.execute(f"SELECT COUNT(DISTINCT user_id) FROM sessions WHERE {CLEAN} AND week=?",
                       (w,)).fetchone()[0] for w in weeks]
    an = [c.execute(f"SELECT COUNT(DISTINCT user_id) FROM sessions WHERE {CLEAN} AND week=? "
                    "AND platform='android' AND user_type='new'", (w,)).fetchone()[0] for w in weeks]
    c.close()
    fig, ax = plt.subplots(figsize=(7, 3.6))
    _style(ax, fig)
    ax.plot(weeks, total, "-o", color=ACCENT, lw=2.4, label="All users (WAU)")
    ax.plot(weeks, an, "-o", color=BAD, lw=2.4, label="android × new")
    ax.set_title("Weekly Active Users — overall vs android × new", fontsize=12, loc="left")
    ax.set_xlabel("week"); ax.set_ylabel("distinct users")
    ax.set_ylim(0, max(total) * 1.1)
    lg = ax.legend(facecolor=SURF, edgecolor=GRID, labelcolor=TEXT, fontsize=9)
    return save(fig, "wau_trend.png")


def chart_driver():
    from key_driver import scan
    res = scan()
    cells = res["evidence"]
    labels = [e["cell"] for e in cells]
    vals = [e["change_pct"] for e in cells]
    colors = [BAD if e["is_cause"] else NEUTRAL for e in cells]
    fig, ax = plt.subplots(figsize=(7, 3.8))
    _style(ax, fig)
    ax.barh(labels, vals, color=colors)
    ax.axvline(res["overall"]["change_pct"], color=WARN, ls="--", lw=1.4,
               label=f"overall {res['overall']['change_pct']}%")
    ax.set_title("WAU change by platform × user_type (wk1→wk8)",
                 fontsize=12, loc="left", pad=12)
    ax.set_xlabel("% change"); ax.invert_yaxis(); ax.margins(y=0.12)
    ax.legend(facecolor=SURF, edgecolor=GRID, labelcolor=TEXT, fontsize=9)
    return save(fig, "driver_cells.png")


def chart_feature():
    c = con()
    weeks = list(range(1, 9))
    share = []
    for w in weeks:
        s = c.execute(f"SELECT COUNT(DISTINCT session_id) FROM sessions WHERE {CLEAN} AND week=?",
                      (w,)).fetchone()[0]
        f = c.execute("SELECT COUNT(DISTINCT session_id) FROM feature_events WHERE feature='sql_export' "
                      "AND session_id IN (SELECT session_id FROM sessions WHERE week=?)",
                      (w,)).fetchone()[0]
        share.append(round(100 * f / s, 1))
    c.close()
    fig, ax = plt.subplots(figsize=(7, 3.4))
    _style(ax, fig)
    ax.plot(weeks, share, "-o", color=GOOD, lw=2.4)
    ax.fill_between(weeks, share, color=GOOD, alpha=0.12)
    ax.set_title("sql_export adoption — quietly up ~3× (% of sessions)", fontsize=12, loc="left")
    ax.set_xlabel("week"); ax.set_ylabel("% of sessions")
    return save(fig, "sql_export_trend.png")


def chart_errors():
    c = con()
    reg = c.execute(
        f"SELECT {REGION_CLEAN} r, ROUND(100.0*SUM(had_error)/COUNT(*),2) e "
        f"FROM sessions WHERE week=6 GROUP BY r ORDER BY e DESC").fetchall()
    emea = [c.execute(
        f"SELECT ROUND(100.0*SUM(had_error)/COUNT(*),2) FROM sessions "
        f"WHERE week=? AND {REGION_CLEAN}='EMEA'", (w,)).fetchone()[0] for w in range(1, 9)]
    c.close()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.4, 3.4))
    _style(a1, fig); _style(a2, fig)
    names = [r[0] for r in reg]; vals = [r[1] for r in reg]
    a1.bar(names, vals, color=[BAD if v > 5 else DIM for v in vals])
    a1.axhline(5, color=WARN, ls="--", lw=1.4)
    a1.set_title("Week 6 error rate by region (%)", fontsize=11, loc="left")
    a2.plot(range(1, 9), emea, "-o", color=BAD, lw=2.2)
    a2.axhline(5, color=WARN, ls="--", lw=1.4, label="5% threshold")
    a2.set_title("EMEA error rate by week (%)", fontsize=11, loc="left")
    a2.set_xlabel("week")
    a2.legend(facecolor=SURF, edgecolor=GRID, labelcolor=TEXT, fontsize=8)
    return save(fig, "error_rate.png")


BUILDERS = {"wau": chart_wau, "driver": chart_driver,
            "feature": chart_feature, "errors": chart_errors}

if __name__ == "__main__":
    sys.path.insert(0, HERE)   # so chart_driver can import key_driver
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "all":
        for b in BUILDERS.values():
            b()
    elif cmd in BUILDERS:
        BUILDERS[cmd]()
    else:
        print("usage: viz_tool.py [wau|driver|feature|errors|all]")
        sys.exit(1)
