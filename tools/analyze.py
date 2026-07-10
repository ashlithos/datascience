"""
analyze.py — a generic, dataset-agnostic analysis engine.

Where the FlowDash tools are hardwired to that schema, this works on ANY loaded
DataFrame (an uploaded CSV or a Hugging Face dataset). It gives the agent — and a
lightweight NL router — the building blocks to answer real data-science questions:

  - run_sql(df, sql)    : DuckDB SQL over the data (table name is `data`), read-only
  - schema(df)          : columns, types, null %, sample values
  - describe(df)        : summary stats
  - value_counts(df, c) : distribution of a column (+ bar chart)
  - group_agg(df, ...)  : metric BY dimension (+ bar chart)
  - correlation(df,x,y) : Pearson r
  - drivers_of(df, t)   : generic key-driver — ranks which columns most explain a
                          target, using effect sizes (eta² for categorical, r² for
                          numeric = proportion of variance explained). No causal claim.
  - route_dataset(df,q) : map a plain-English question to the above; returns a
                          {skill, calls, answer, canvas} dict or None to fall through.

Chart output is base64-embedded so canvases stay self-contained.
"""
import base64
import io
import re

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# palette mirrored from the Jetski design tokens
BG, SURF, GRID = "#111418", "#191c20", "#44474e"
TEXT, DIM = "#e2e2e9", "#c4c6d0"
ACCENT, GOOD, ERO = "#a8c7fa", "#8ed8a9", "#ff8a65"


# --------------------------------------------------------------------------- #
#  duckdb + helpers                                                            #
# --------------------------------------------------------------------------- #
def _con(df):
    import duckdb
    con = duckdb.connect()
    con.register("data", df)
    return con


def run_sql(df, sql):
    sql = sql.strip().rstrip(";")
    if not re.match(r"^\s*(select|with)\b", sql, re.I) or re.search(
            r"\b(insert|update|delete|drop|alter|create|attach|copy|pragma)\b", sql, re.I):
        raise ValueError("Only read-only SELECT/WITH queries are allowed.")
    con = _con(df)
    try:
        return con.execute(sql).fetchdf()
    finally:
        con.close()


def _num(df):
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _cat(df, max_card=25):
    out = []
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            continue
        if df[c].nunique(dropna=True) <= max_card:
            out.append(c)
    return out


def _find_cols(df, q):
    """Columns whose name (or a stem of a token of it) appears in the question.
    Handles prefixes so 'churn' matches 'churned', 'spend' matches 'monthly_spend'."""
    ql = q.lower()
    qtokens = [t for t in re.split(r"[^a-z0-9]+", ql) if len(t) >= 3]
    hits = []
    for c in df.columns:
        cl = str(c).lower()
        ctokens = [t for t in re.split(r"[_\s]+", cl) if t]
        matched = cl in ql
        for ct in ctokens:
            if len(ct) < 3:
                continue
            for qt in qtokens:
                if ct == qt or ct.startswith(qt) or qt.startswith(ct):
                    matched = True
                    break
        if matched:
            hits.append(c)
    return hits


def _tbl(frame, limit=50):
    if isinstance(frame, pd.DataFrame):
        cols = list(frame.columns)
        rows = frame.head(limit).values.tolist()
    else:
        cols, rows = frame
        rows = rows[:limit]
    head = "".join(f'<th class="num">{c}</th>' if i else f"<th>{c}</th>"
                   for i, c in enumerate(cols))
    body = ""
    for r in rows:
        tds = "".join(f'<td class="num">{"" if v is None else v}</td>' if i else
                      f'<td>{"" if v is None else v}</td>' for i, v in enumerate(r))
        body += f"<tr>{tds}</tr>"
    return f'<table class="tbl"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _chart(kind, labels, values, title, color=ACCENT):
    fig, ax = plt.subplots(figsize=(6.6, 3.3))
    fig.patch.set_facecolor(BG); ax.set_facecolor(SURF)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=DIM, labelsize=8); ax.title.set_color(TEXT)
    ax.grid(True, color=GRID, lw=.5, alpha=.4)
    if kind == "hist":
        ax.hist(values, bins=30, color=color)
    else:
        ax.bar([str(x) for x in labels], values, color=color)
        if len(labels) > 6:
            ax.tick_params(axis="x", rotation=40, labelsize=7)
    ax.set_title(title, color=TEXT, fontsize=11, loc="left")
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                                    facecolor=BG); plt.close(fig)
    return ('<img class="chart" src="data:image/png;base64,'
            + base64.b64encode(buf.getvalue()).decode() + '">')


# --------------------------------------------------------------------------- #
#  analyses (return canvas HTML fragments)                                     #
# --------------------------------------------------------------------------- #
def schema(df):
    rows = []
    for c in df.columns:
        s = df[c]
        dt = "number" if pd.api.types.is_numeric_dtype(s) else "text"
        nn = f"{s.isna().mean()*100:.0f}%"
        ex = ", ".join(str(v) for v in s.dropna().unique()[:3])
        rows.append([c, dt, f"{s.nunique(dropna=True)}", nn, ex[:60]])
    return (f'<span class="kicker">Dataset · overview</span>'
            f'<h3 class="ctitle">{len(df)} rows × {df.shape[1]} columns</h3>'
            f'<p class="csub">Schema, cardinality, and null share per column.</p>'
            + _tbl((["column", "type", "distinct", "null%", "sample"], rows)))


def describe_stats(df):
    num = _num(df)
    if not num:
        return schema(df)
    d = df[num].describe().T.round(2).reset_index()
    d.columns = ["column"] + list(d.columns[1:])
    return (f'<span class="kicker">Summary statistics</span>'
            f'<h3 class="ctitle">Numeric columns — describe()</h3>'
            + _tbl(d))


def value_counts(df, col, top=15):
    vc = df[col].value_counts(dropna=False).head(top)
    chart = _chart("bar", list(vc.index), list(vc.values), f"Distribution of {col}")
    rows = [[str(k), int(v), f"{v/len(df)*100:.1f}%"] for k, v in vc.items()]
    return (f'<span class="kicker">Distribution</span>'
            f'<h3 class="ctitle">{col} — value counts</h3>{chart}'
            + _tbl((["value", "count", "share"], rows)))


def group_agg(df, metric_col, by_col, agg="mean"):
    fn = {"mean": "AVG", "avg": "AVG", "average": "AVG", "sum": "SUM", "total": "SUM",
          "count": "COUNT", "median": "MEDIAN", "max": "MAX", "min": "MIN"}.get(agg, "AVG")
    if agg == "count" or metric_col is None:
        res = run_sql(df, f'SELECT "{by_col}" AS grp, COUNT(*) AS value '
                          f'FROM data GROUP BY "{by_col}" ORDER BY value DESC LIMIT 30')
        label = f"count by {by_col}"
    else:
        res = run_sql(df, f'SELECT "{by_col}" AS grp, {fn}("{metric_col}") AS value '
                          f'FROM data GROUP BY "{by_col}" ORDER BY value DESC LIMIT 30')
        label = f"{agg} of {metric_col} by {by_col}"
    res["value"] = pd.to_numeric(res["value"], errors="coerce").round(3)
    chart = _chart("bar", list(res["grp"]), list(res["value"]), label, GOOD)
    return (f'<span class="kicker">Aggregation</span>'
            f'<h3 class="ctitle">{label}</h3>{chart}' + _tbl(res))


def correlation(df, x, y):
    r = df[[x, y]].dropna().corr().iloc[0, 1]
    strength = ("strong" if abs(r) > .6 else "moderate" if abs(r) > .3 else "weak")
    return (f'<span class="kicker">Correlation</span>'
            f'<h3 class="ctitle">{x} vs {y}</h3>'
            f'<div class="metrics"><div><div class="mval">{r:+.2f}</div>'
            f'<div class="mlbl">Pearson r ({strength})</div></div></div>'
            f'<p class="foot">Correlation is not causation — r measures linear association only.</p>')


def drivers_of(df, target):
    """Generic key-driver: rank columns by how much they explain `target`, using
    effect sizes (proportion of variance explained). Works for a numeric or binary
    target. Returns (canvas_html, summary_text)."""
    t = df[target]
    note = ""
    if not pd.api.types.is_numeric_dtype(t):
        uniq = t.dropna().unique()
        if len(uniq) != 2:
            return (f'<span class="kicker">Key drivers</span><h3 class="ctitle">Can\'t rank drivers of “{target}”</h3>'
                    f'<p class="csub">Pick a numeric or a two-value (binary) target — “{target}” has '
                    f'{len(uniq)} distinct values.</p>', f"target {target} not numeric/binary")
        pos = sorted(map(str, uniq))[-1]
        t = (t.astype(str) == pos).astype(float)
        note = f' (modeling P({target} = “{pos}”))'
    t = pd.to_numeric(t, errors="coerce")
    overall = t.mean()
    tot_ss = float(((t - overall) ** 2).sum())
    results = []
    for c in df.columns:
        if str(c) == str(target):
            continue
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            valid = pd.concat([s, t], axis=1).dropna()
            if len(valid) < 10 or valid.iloc[:, 0].nunique() < 3:
                continue
            r = valid.iloc[:, 0].corr(valid.iloc[:, 1])
            if pd.isna(r):
                continue
            results.append({"col": str(c), "effect": float(r ** 2),
                            "detail": f"numeric · corr r = {r:+.2f}"})
        else:
            if s.nunique(dropna=True) > 25 or s.nunique(dropna=True) < 2:
                continue
            grp = t.groupby(s).mean()
            cnt = t.groupby(s).count()
            between = float((cnt * (grp - overall) ** 2).sum())
            eta2 = between / tot_ss if tot_ss else 0.0
            top = (grp - overall).abs().idxmax()
            results.append({"col": str(c), "effect": eta2,
                            "detail": f'{c} = “{top}”: {grp[top]:.2f} vs {overall:.2f} overall'})
    results.sort(key=lambda d: -d["effect"])
    results = results[:6]
    if not results:
        return (f'<span class="kicker">Key drivers</span><h3 class="ctitle">No clear drivers of “{target}”</h3>'
                f'<p class="csub">No other column explains meaningful variance.</p>', "no drivers")
    top = results[0]
    rowshtml = ""
    for i, d in enumerate(results):
        cls = ' class="cause"' if i == 0 else ""
        rowshtml += (f'<tr{cls}><td>{d["col"]}</td>'
                     f'<td class="num">{d["effect"]*100:.0f}%</td><td>{d["detail"]}</td></tr>')
    canvas = (
        f'<span class="kicker">Key-driver analysis · generic</span>'
        f'<h3 class="ctitle">What explains {target}?{note}</h3>'
        f'<p class="csub">Columns ranked by variance explained (effect size). '
        f'Association, not proven causation.</p>'
        f'<div class="metrics"><div><div class="mval">{top["effect"]*100:.0f}%</div>'
        f'<div class="mlbl">variance explained by {top["col"]}</div></div></div>'
        f'<table class="tbl"><thead><tr><th>column</th><th class="num">explains</th><th>how</th></tr></thead>'
        f'<tbody>{rowshtml}</tbody></table>'
        f'<p class="foot">Effect size = eta² (categorical) / r² (numeric) = share of the target\'s '
        f'variance associated with that column. A causal claim needs an experiment.</p>')
    summ = f"Top driver of {target}: {top['col']} (explains ~{top['effect']*100:.0f}%); {top['detail']}."
    return canvas, summ


# --------------------------------------------------------------------------- #
#  NL router over a loaded dataset                                             #
# --------------------------------------------------------------------------- #
_AGG = r"(mean|average|avg|sum|total|count|median|max|min)"


def route_dataset(df, q):
    """Best-effort mapping of a plain-English question to an analysis. Returns a
    dict {skill, calls, answer, canvas} or None (let the caller fall through)."""
    ql = q.lower().strip()
    name = "your dataset"

    # raw SQL over the loaded data
    if re.match(r"^\s*(select|with)\b", ql):
        try:
            res = run_sql(df, q)
        except Exception as e:
            return {"skill": "analyze", "calls": ["duckdb · error"],
                    "answer": f"SQL error: {e}", "canvas": schema(df)}
        return {"skill": "analyze", "calls": [f"duckdb · {q[:60]}…"],
                "answer": f"Ran your query over {name} — {len(res)} row(s).",
                "canvas": f'<span class="kicker">Query result</span>'
                          f'<div class="ds-code">{q}</div>' + _tbl(res)}

    # schema / describe / overview
    if _has(ql, "schema", "columns", "what columns", "describe", "summary", "overview",
            "what's in", "whats in", "shape of"):
        canvas = describe_stats(df) if _has(ql, "describe", "stat", "summary") else schema(df)
        return {"skill": "analyze", "calls": ["schema + describe"],
                "answer": f"Here's the shape of {name}: {len(df)} rows × {df.shape[1]} columns. "
                          "Overview on the right.", "canvas": canvas}

    # key drivers / what predicts / explains X
    m = re.search(r"(?:driv\w*|predict\w*|explain\w*|caus\w*|influenc\w*|factor\w*)\s+(?:of|for|the|behind)?\s*([\w ]+)?", ql)
    if _has(ql, "driver", "predict", "explain", "what causes", "what drives", "factor", "influence") and not _has(ql, "sql"):
        cols = _find_cols(df, q)
        target = cols[-1] if cols else None
        if target is None:
            return {"skill": "analyze", "calls": ["need a target column"],
                    "answer": "Which column do you want to explain? e.g. “what drives churn?”",
                    "canvas": schema(df)}
        canvas, summ = drivers_of(df, target)
        return {"skill": "key-driver-analysis",
                "calls": [f"scan columns · effect sizes vs {target}"],
                "answer": summ, "canvas": canvas}

    # metric BY dimension
    m = re.search(_AGG + r"\s+(?:of\s+)?([\w]+)?\s*(?:\bby\b|per|across|grouped by)\s+([\w]+)", ql)
    if m or (_has(ql, " by ", " per ") and _has(ql, "avg", "average", "mean", "sum", "count", "total")):
        if m:
            agg, mcol_hint, bcol_hint = m.group(1), m.group(2), m.group(3)
        else:
            agg, mcol_hint, bcol_hint = "mean", None, None
        by = _resolve(df, bcol_hint) or (_find_cols(df, q)[-1] if _find_cols(df, q) else None)
        metric = _resolve(df, mcol_hint)
        if by is None:
            return None
        canvas = group_agg(df, metric, by, agg)
        return {"skill": "analyze", "calls": [f"group by {by} · {agg}"],
                "answer": f"{agg} of {metric or 'rows'} by {by} — on the right.", "canvas": canvas}

    # distribution / value counts / breakdown of X
    if _has(ql, "distribution", "value counts", "breakdown", "histogram", "how many of each", "spread of"):
        cols = _find_cols(df, q)
        if cols:
            return {"skill": "analyze", "calls": [f"value_counts({cols[0]})"],
                    "answer": f"Distribution of {cols[0]} on the right.",
                    "canvas": value_counts(df, cols[0])}

    # correlation between X and Y
    if _has(ql, "correlat", "relationship between", "related to"):
        nums = [c for c in _find_cols(df, q) if pd.api.types.is_numeric_dtype(df[c])]
        if len(nums) >= 2:
            return {"skill": "analyze", "calls": [f"corr({nums[0]},{nums[1]})"],
                    "answer": f"Correlation between {nums[0]} and {nums[1]} on the right.",
                    "canvas": correlation(df, nums[0], nums[1])}

    # how many rows / count
    if _has(ql, "how many rows", "row count", "how big", "number of rows"):
        return {"skill": "analyze", "calls": ["COUNT(*)"],
                "answer": f"{name} has {len(df)} rows and {df.shape[1]} columns.",
                "canvas": schema(df)}
    return None


def _resolve(df, hint):
    if not hint:
        return None
    hint = hint.strip().lower()
    for c in df.columns:
        cl = str(c).lower()
        if cl == hint or hint in cl or cl in hint:
            return c
    return None


def _has(text, *words):
    return any(w in text for w in words)


if __name__ == "__main__":
    import sys
    df = pd.read_csv(sys.argv[1])
    q = " ".join(sys.argv[2:]) or "describe"
    r = route_dataset(df, q)
    print(r["answer"] if r else "(no match)")
