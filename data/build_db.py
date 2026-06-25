"""
build_db.py — Generate FlowDash, the synthetic dataset for the DS-agent demo.

FlowDash is the (fictional) usage-telemetry database for an internal BI/dashboard
product. It is engineered to contain four deliberate "hooks" so that each stage of
the data-science workflow has something real to bite on:

  1. DIRTY-DATA hook        (for the data-cleaning stage)
       - exact-duplicate session rows  (some session_id logged twice)
       - negative duration_sec values  (clock/instrumentation bug)
       - inconsistent region spelling: "EMEA" / "emea" / "E.M.E.A" / " EMEA "

  2. HIDDEN-DRIVER hook      (for the key-driver-analysis stage)
       - weekly active users (WAU) fall ~18% across 8 weeks
       - the real cause is an INTERACTION: only (platform=android x user_type=new)
         collapses (~-61%); every other cell is roughly flat
       - any SINGLE dimension (region / platform / new-vs-returning) only shows a
         diffuse, partial dip — it takes the cross-tab to localise the cause

  3. TREND-STORY hook        (for the storytelling stage)
       - the "sql_export" feature quietly grows ~3x over the 8 weeks (a good-news
         story hiding under the WAU decline)

  4. THRESHOLD-BREACH hook   (for the alert stage)
       - in week 6, EMEA's error rate breaks the 5% threshold, concentrated in the
         ~2 hours immediately after deployment "v2026.06.03"

The generator is fully deterministic (fixed seed) so the demo is reproducible.

Run:  python data/build_db.py
"""

import os
import random
import sqlite3
from datetime import datetime, timedelta

SEED = 20260625
random.seed(SEED)

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "flowdash.db")

# ---------------------------------------------------------------------------
# Calendar: 8 ISO-ish weeks. Week 1 starts Mon 2026-04-27; week 8 = Jun 15-21.
# "Today" in the demo is 2026-06-25, so all 8 weeks are complete.
# ---------------------------------------------------------------------------
WEEK1_START = datetime(2026, 4, 27)          # Monday
N_WEEKS = 8
def week_start(w):                            # w in 1..8
    return WEEK1_START + timedelta(days=7 * (w - 1))

# ---------------------------------------------------------------------------
# Segment model: platform x user_type cells, with weekly distinct-active counts.
# Only android/new declines; the rest are flat (+/- small noise).
# ---------------------------------------------------------------------------
# week-1 active-user counts per cell
BASE = {
    ("android", "new"):       1500,
    ("android", "returning"):  700,
    ("ios", "new"):            650,
    ("ios", "returning"):      600,
    ("web", "new"):            500,
    ("web", "returning"):     1050,
}
# per-week multiplier applied to the base count for each cell.
# android/new collapses to ~0.39 of base (= -61%); others hover near 1.0.
ANDROID_NEW_CURVE = [1.00, 0.94, 0.86, 0.79, 0.69, 0.58, 0.48, 0.39]

REGION_WEIGHTS = [("NA", 0.40), ("EMEA", 0.30), ("APAC", 0.20), ("LATAM", 0.10)]

# Feature catalogue. sql_export rises week over week; the rest are flat-ish.
FEATURES_FLAT = ["dashboard_view", "apply_filter", "share_link",
                 "export_csv", "configure_alert"]
# probability a given session touches sql_export, by week (quiet 3x climb)
SQL_EXPORT_CURVE = [0.05, 0.06, 0.07, 0.09, 0.10, 0.12, 0.14, 0.16]

# Deployments table (one per week, Wednesday 14:00). Week 6's is the bad one.
def deploy_for_week(w):
    ts = week_start(w) + timedelta(days=2, hours=14)   # Wed 14:00
    ver = "v" + ts.strftime("%Y.%m.%d")
    note = ""
    if w == 6:
        note = "Hotfix to EMEA edge routing; caused elevated 5xx for ~2h."
    return ver, ts, note

DEPLOYS = {w: deploy_for_week(w) for w in range(1, N_WEEKS + 1)}

BASE_ERROR_RATE = 0.015        # background error rate everywhere
EMEA_SPIKE_RATE = 0.55         # error rate inside the week-6 post-deploy window

# region spelling variants used ONLY for EMEA rows (dirty-data hook)
EMEA_VARIANTS = ["EMEA", "emea", "E.M.E.A", " EMEA ", "EMEA"]


def pick_region():
    r = random.random()
    cum = 0.0
    for name, w in REGION_WEIGHTS:
        cum += w
        if r <= cum:
            return name
    return "NA"


def dirty_region(canonical):
    """EMEA rows get inconsistent spelling; everyone else stays clean."""
    if canonical == "EMEA":
        return random.choice(EMEA_VARIANTS)
    return canonical


def gen_user_pool(cell, size):
    code = {"android": "a", "ios": "i", "web": "w"}[cell[0]] + cell[1][0]
    return [f"u-{code}-{i:05d}" for i in range(size)]


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE deployments (
            deploy_id   TEXT PRIMARY KEY,
            deployed_at TEXT NOT NULL,
            notes       TEXT
        );
        CREATE TABLE sessions (
            session_id   TEXT NOT NULL,
            user_id      TEXT NOT NULL,
            started_at   TEXT NOT NULL,   -- ISO datetime
            week         INTEGER NOT NULL,-- convenience 1..8 (also derivable from date)
            region       TEXT NOT NULL,   -- DIRTY: EMEA spelled inconsistently
            platform     TEXT NOT NULL,   -- android / ios / web
            user_type    TEXT NOT NULL,   -- new / returning
            plan         TEXT NOT NULL,   -- free / pro  (semantic trap vs user_type)
            duration_sec INTEGER NOT NULL,-- DIRTY: some negative; wall-clock length
            active_sec   INTEGER NOT NULL,-- engaged (foreground) secs <= duration_sec
            had_error    INTEGER NOT NULL,-- 0/1, at least one error in session
            app_version  TEXT NOT NULL    -- deploy active when session started
        );
        CREATE TABLE feature_events (
            event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            feature    TEXT NOT NULL,
            used_at    TEXT NOT NULL
        );
        """
    )

    for w in range(1, N_WEEKS + 1):
        ver, ts, note = DEPLOYS[w]
        cur.execute("INSERT INTO deployments VALUES (?,?,?)", (ver, ts.isoformat(), note))

    # generous per-cell user pools so weekly active sets overlap naturally
    pools = {cell: gen_user_pool(cell, int(n * 1.6) + 50) for cell, n in BASE.items()}

    session_rows = []
    feature_rows = []
    sid = 0

    for w in range(1, N_WEEKS + 1):
        wstart = week_start(w)
        ver, deploy_ts, _ = DEPLOYS[w]
        for cell, base_n in BASE.items():
            platform, user_type = cell
            if cell == ("android", "new"):
                active_n = int(base_n * ANDROID_NEW_CURVE[w - 1])
            else:
                active_n = int(base_n * random.uniform(0.96, 1.04))  # flat + noise
            active_users = random.sample(pools[cell], min(active_n, len(pools[cell])))

            for uid in active_users:
                n_sessions = random.choices([1, 2, 3], weights=[55, 32, 13])[0]
                for _ in range(n_sessions):
                    sid += 1
                    session_id = f"s-{w}-{sid:07d}"
                    # timestamp uniformly within the week (business-ish hours)
                    day = random.randint(0, 6)
                    hour = random.choices(range(7, 23), k=1)[0]
                    minute = random.randint(0, 59)
                    started = wstart + timedelta(days=day, hours=hour, minutes=minute)

                    canonical_region = pick_region()
                    region = dirty_region(canonical_region)

                    plan = random.choices(["free", "pro"],
                                          weights=[78, 22] if user_type == "new" else [55, 45])[0]

                    duration = max(5, int(random.lognormvariate(5.3, 0.7)))   # ~ secs
                    active = int(duration * random.uniform(0.45, 0.92))

                    # ---- error model -------------------------------------------------
                    had_error = 1 if random.random() < BASE_ERROR_RATE else 0
                    # week-6 EMEA post-deploy spike (2h window after deploy)
                    if (w == 6 and canonical_region == "EMEA"
                            and deploy_ts <= started <= deploy_ts + timedelta(hours=2)):
                        had_error = 1 if random.random() < EMEA_SPIKE_RATE else 0

                    session_rows.append((session_id, uid, started.isoformat(), w,
                                         region, platform, user_type, plan,
                                         duration, active, had_error, ver))

                    # ---- features ----------------------------------------------------
                    used_feats = set(random.sample(
                        FEATURES_FLAT, k=random.randint(1, 3)))
                    if random.random() < SQL_EXPORT_CURVE[w - 1]:
                        used_feats.add("sql_export")
                    for f in used_feats:
                        fmin = random.randint(0, max(1, duration // 60))
                        fts = started + timedelta(minutes=fmin)
                        feature_rows.append((session_id, f, fts.isoformat()))

    # ---- inject extra EMEA sessions into the week-6 spike window ----------------
    # (so the weekly EMEA error rate clearly clears 5%, with the spike concentrated)
    ver6, deploy_ts6, _ = DEPLOYS[6]
    spike_pool = pools[("android", "returning")] + pools[("ios", "returning")]
    for _ in range(220):
        sid += 1
        session_id = f"s-6-{sid:07d}"
        offset_min = random.randint(0, 120)
        started = deploy_ts6 + timedelta(minutes=offset_min)
        uid = random.choice(spike_pool)
        platform = random.choice(["android", "ios", "web"])
        user_type = random.choice(["new", "returning"])
        plan = random.choice(["free", "pro"])
        duration = max(5, int(random.lognormvariate(5.0, 0.6)))
        active = int(duration * random.uniform(0.4, 0.9))
        had_error = 1 if random.random() < EMEA_SPIKE_RATE else 0
        session_rows.append((session_id, uid, started.isoformat(), 6,
                             dirty_region("EMEA"), platform, user_type, plan,
                             duration, active, had_error, ver6))
        feature_rows.append((session_id, random.choice(FEATURES_FLAT), started.isoformat()))

    # ---- DIRTY HOOK 1: negative durations (instrumentation bug) -----------------
    neg_idx = random.sample(range(len(session_rows)), 28)
    for i in neg_idx:
        r = list(session_rows[i])
        r[8] = -abs(r[8])               # duration_sec negative
        session_rows[i] = tuple(r)

    cur.executemany(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", session_rows)
    cur.executemany(
        "INSERT INTO feature_events (session_id, feature, used_at) VALUES (?,?,?)",
        feature_rows)

    # ---- DIRTY HOOK 2: exact-duplicate session rows -----------------------------
    dup_sample = random.sample(session_rows, 35)
    cur.executemany(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", dup_sample)

    con.commit()

    # ---- quick self-check printout ----------------------------------------------
    def q(sql):
        return cur.execute(sql).fetchall()

    print(f"DB written: {DB_PATH}")
    print("sessions rows:", q("SELECT COUNT(*) FROM sessions")[0][0],
          "| feature_events:", q("SELECT COUNT(*) FROM feature_events")[0][0])
    print("duplicate session_ids:",
          q("SELECT COUNT(*) FROM (SELECT session_id FROM sessions "
            "GROUP BY session_id HAVING COUNT(*)>1)")[0][0])
    print("negative durations:",
          q("SELECT COUNT(*) FROM sessions WHERE duration_sec<0")[0][0])
    print("distinct region spellings:",
          [r[0] for r in q("SELECT DISTINCT region FROM sessions ORDER BY 1")])

    con.close()


if __name__ == "__main__":
    main()
