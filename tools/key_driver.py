"""
key_driver.py — the key-driver-analysis "orchestration" engine (route C).

Given a metric that moved (here: weekly active users), this scans single
dimensions AND pairwise crossings to find *where* the movement concentrates,
then reports the strongest driver with a transparency trail (which combinations
it tried) and a heuristic confidence score.

The whole point of the demo's key-driver stage: a single-dimension cut only shows
a diffuse/partial dip, but the platform x user_type CROSS localises the cause
(android x new). This tool surfaces that automatically.

Usage:
    python tools/key_driver.py            # full WAU driver scan -> JSON + summary
    python tools/key_driver.py --json     # JSON only (for the component renderer)

Output (JSON): overall change, ranked single-dimension cuts, ranked crossings,
the top driver, the evidence table for that driver, and a confidence score.
"""
import json
import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "flowdash.db")
REGION_CLEAN = ("CASE WHEN REPLACE(UPPER(TRIM(region)),'.','')='EMEA' THEN 'EMEA' "
                "ELSE TRIM(region) END")
CLEAN = "duration_sec > 0"          # drop dirty negative-duration rows
FIRST_W, LAST_W = 1, 8


def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def wau(c, where=""):
    where = (" AND " + where) if where else ""
    q = (f"SELECT week, COUNT(DISTINCT user_id) n FROM sessions "
         f"WHERE {CLEAN}{where} GROUP BY week ORDER BY week")
    d = {r["week"]: r["n"] for r in c.execute(q)}
    return d


def pct(a, b):
    return None if not a else round((b - a) / a * 100, 1)


def scan():
    c = con()
    base = wau(c)
    overall = {"first_week": FIRST_W, "last_week": LAST_W,
               "wau_first": base.get(FIRST_W), "wau_last": base.get(LAST_W),
               "change_pct": pct(base.get(FIRST_W), base.get(LAST_W)),
               "series": [base.get(w, 0) for w in range(FIRST_W, LAST_W + 1)]}

    dims = {
        "region":    f"{REGION_CLEAN}",
        "platform":  "platform",
        "user_type": "user_type",
        "plan":      "plan",
    }

    # ---- single-dimension cuts -------------------------------------------------
    singles = []
    for dim, expr in dims.items():
        vals = [r[0] for r in c.execute(
            f"SELECT DISTINCT {expr} FROM sessions WHERE {CLEAN} ORDER BY 1")]
        for v in vals:
            w = f"{expr} = '{v}'"
            s = wau(c, w)
            singles.append({"dim": dim, "value": v,
                            "first": s.get(FIRST_W, 0), "last": s.get(LAST_W, 0),
                            "change_pct": pct(s.get(FIRST_W, 0), s.get(LAST_W, 0))})
    singles.sort(key=lambda x: (x["change_pct"] is None, x["change_pct"]))

    # ---- pairwise crossings ----------------------------------------------------
    crossings = []
    keys = list(dims.items())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            (d1, e1), (d2, e2) = keys[i], keys[j]
            combos = c.execute(
                f"SELECT DISTINCT {e1} a, {e2} b FROM sessions WHERE {CLEAN}").fetchall()
            for r in combos:
                a, b = r["a"], r["b"]
                w = f"{e1} = '{a}' AND {e2} = '{b}'"
                s = wau(c, w)
                first, last = s.get(FIRST_W, 0), s.get(LAST_W, 0)
                if first < 80:        # ignore tiny, noisy cells
                    continue
                crossings.append({
                    "dims": f"{d1} x {d2}", "value": f"{a} x {b}",
                    "where": w, "first": first, "last": last,
                    "change_pct": pct(first, last),
                    "share_of_base": round(first / overall["wau_first"] * 100, 1),
                })
    crossings.sort(key=lambda x: (x["change_pct"] is None, x["change_pct"]))

    top = crossings[0]

    # ---- confidence heuristic --------------------------------------------------
    # High when: the top crossing falls much harder than the overall metric, it is
    # a meaningful share of the base, and sibling cells are roughly flat.
    drop = -(top["change_pct"] or 0)
    overall_drop = -(overall["change_pct"] or 0)
    sep = drop - overall_drop                       # how much worse than headline
    siblings_flat = all(abs(cr["change_pct"]) < 12
                        for cr in crossings[1:6] if cr["change_pct"] is not None)
    conf = 50
    if drop > 40: conf += 18
    if sep > 25:  conf += 14
    if top["share_of_base"] > 20: conf += 10
    if siblings_flat: conf += 8
    conf = max(40, min(96, conf))

    # ---- evidence table for the winning cross (all cells of that 2-way) ---------
    d1, d2 = top["dims"].split(" x ")
    e1, e2 = dims[d1], dims[d2]
    ev = []
    for r in c.execute(f"SELECT DISTINCT {e1} a, {e2} b FROM sessions WHERE {CLEAN}"):
        a, b = r["a"], r["b"]
        s = wau(c, f"{e1}='{a}' AND {e2}='{b}'")
        first, last = s.get(FIRST_W, 0), s.get(LAST_W, 0)
        if first < 80:
            continue
        ev.append({"cell": f"{a} x {b}", "first": first, "last": last,
                   "change_pct": pct(first, last),
                   "is_cause": (f"{a} x {b}" == top["value"])})
    ev.sort(key=lambda x: x["change_pct"])
    c.close()

    return {"metric": "Weekly Active Users (WAU)",
            "overall": overall, "singles": singles, "crossings": crossings[:8],
            "top_driver": top, "evidence": ev, "confidence": conf,
            "combos_tried": len(singles) + len(crossings)}


def summarize(res):
    o = res["overall"]; t = res["top_driver"]
    lines = [
        f"Metric: {res['metric']}",
        f"Overall wk{o['first_week']}->wk{o['last_week']}: "
        f"{o['wau_first']} -> {o['wau_last']} ({o['change_pct']}%)",
        f"Scanned {res['combos_tried']} dimension combinations.",
        "",
        "Single-dimension cuts only show a diffuse dip (worst 4):",
    ]
    for s in res["singles"][:4]:
        lines.append(f"  - {s['dim']}={s['value']}: {s['change_pct']}%")
    lines += ["",
              f"TOP DRIVER (cross-dimension): {t['value']}  "
              f"({t['change_pct']}%, {t['share_of_base']}% of base)",
              f"Confidence: {res['confidence']}%",
              "", "Evidence — all cells of this crossing:"]
    for e in res["evidence"]:
        flag = "  <== cause" if e["is_cause"] else ""
        lines.append(f"  {e['cell']:24s} {e['first']:5d} -> {e['last']:5d} "
                     f"({e['change_pct']:+.0f}%){flag}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    res = scan()
    if "--json" in sys.argv:
        print(json.dumps(res, indent=2))
    else:
        print(summarize(res))
