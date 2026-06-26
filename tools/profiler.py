"""
profiler.py — a generic, dataset-agnostic data-quality profiler.

Unlike the FlowDash-specific cleaning (which knows about its three planted issues),
this works on ANY tabular file you drop in: CSV / TSV / JSON / Excel. It scans for the
common real-world problems, returns each as a structured issue (with a sample and a
proposed fix), and can apply the approved fixes non-destructively (it returns a cleaned
copy; it never mutates the source file).

Detected issue types:
  - duplicate_rows      : fully-identical rows
  - missing_values      : nulls in a column (per-column)
  - whitespace          : leading/trailing spaces in text values
  - inconsistent_case   : same category in different casings/spacings ("EMEA"/"emea"/" EMEA ")
  - numeric_as_text     : a column that's numbers stored as strings
  - negative_values     : negatives in a column that shouldn't have them (count/duration/price/age/qty)
  - outliers            : extreme values by the IQR rule
  - constant_column     : a column with a single value (no information)

Usage:
    python tools/profiler.py path/to/data.csv                 # human summary
    python tools/profiler.py --json path/to/data.csv          # structured issues
    python tools/profiler.py --clean all path/to/data.csv     # write *.cleaned.csv
"""
import json
import os
import re
import sys

import numpy as np
import pandas as pd

# columns whose names imply they should never be negative
_NONNEG = re.compile(r"(_sec$|seconds|duration|count|qty|quantity|price|amount|cost|"
                     r"age|year|score|total|num_|_num$|rate$|pct$|percent)", re.I)
_MAX_SAMPLE = 4


# --------------------------------------------------------------------------- #
#  loading                                                                     #
# --------------------------------------------------------------------------- #
def load_any(path):
    """Load CSV/TSV/JSON/XLSX into a DataFrame, sniffing by extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if ext == ".json":
        return pd.read_json(path)
    if ext in (".tsv", ".tab"):
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)            # default csv (pandas sniffs the separator poorly; csv is the norm)


def _samples(values, n=_MAX_SAMPLE):
    out = []
    for v in values:
        if len(out) >= n:
            break
        out.append("" if v is None else str(v))
    return out


def _is_text(s):
    # robust across pandas versions: pandas 3.0 uses a dedicated `str`/StringDtype
    # for text columns (not `object`). Treat anything non-numeric/bool/datetime as text.
    return not (pd.api.types.is_numeric_dtype(s)
                or pd.api.types.is_bool_dtype(s)
                or pd.api.types.is_datetime64_any_dtype(s))


# --------------------------------------------------------------------------- #
#  profiling                                                                   #
# --------------------------------------------------------------------------- #
def profile(df):
    """Return {shape, columns, issues:[...]} for a DataFrame. Each issue carries
    a stable id, a human title, a severity, the affected column, a count, a small
    sample, and a `fix` descriptor the apply step dispatches on."""
    issues = []
    n = len(df)

    # 1. duplicate full rows
    dup_mask = df.duplicated(keep="first")
    if dup_mask.any():
        c = int(dup_mask.sum())
        issues.append({
            "id": "duplicate_rows", "type": "duplicate_rows", "column": None,
            "title": f"{c} duplicate rows", "severity": "high", "count": c,
            "detail": "Fully-identical rows appear more than once.",
            "sample": _samples([str(df[dup_mask].iloc[i].to_dict())[:90] for i in range(min(2, c))]),
            "fix": {"kind": "drop_duplicate_rows"}, "fix_label": "Drop duplicate rows (keep first)"})

    for col in df.columns:
        s = df[col]

        # 2. missing values
        miss = int(s.isna().sum())
        if miss:
            dtype_kind = "numeric" if pd.api.types.is_numeric_dtype(s) else "categorical"
            strat = "median" if dtype_kind == "numeric" else "mode"
            issues.append({
                "id": f"missing::{col}", "type": "missing_values", "column": col,
                "title": f"{miss} missing values in “{col}” ({miss/n*100:.0f}%)",
                "severity": "high" if miss / n > 0.2 else "medium", "count": miss,
                "detail": f"Nulls in a {dtype_kind} column.",
                "sample": [], "fix": {"kind": "fill_missing", "strategy": strat},
                "fix_label": f"Fill with column {strat}" if miss / n < 0.5 else "Drop rows with this missing"})

        if _is_text(s):
            non_null = s.dropna().astype(str)

            # 3. whitespace
            ws_mask = non_null != non_null.str.strip()
            if ws_mask.any():
                c = int(ws_mask.sum())
                issues.append({
                    "id": f"whitespace::{col}", "type": "whitespace", "column": col,
                    "title": f"Leading/trailing spaces in “{col}” ({c} values)",
                    "severity": "low", "count": c, "detail": "Stray spaces around text values.",
                    "sample": _samples([repr(v) for v in non_null[ws_mask].unique()[:_MAX_SAMPLE]]),
                    "fix": {"kind": "strip_whitespace"}, "fix_label": "Trim whitespace"})

            # 4. inconsistent casing / spacing collapsing to the same key
            keyed = non_null.str.strip().str.lower()
            groups = {}
            for raw, key in zip(non_null, keyed):
                groups.setdefault(key, set()).add(raw)
            inconsistent = {k: v for k, v in groups.items() if len(v) > 1}
            if inconsistent:
                variant_count = sum(len(v) for v in inconsistent.values())
                example = max(inconsistent.values(), key=len)
                issues.append({
                    "id": f"case::{col}", "type": "inconsistent_case", "column": col,
                    "title": f"Inconsistent labels in “{col}” ({len(inconsistent)} groups)",
                    "severity": "medium", "count": variant_count,
                    "detail": "The same category written several ways (case/spacing).",
                    "sample": _samples([repr(v) for v in list(example)[:_MAX_SAMPLE]]),
                    "fix": {"kind": "normalize_case"}, "fix_label": "Normalise to the most common form"})

            # 5. numeric-looking text
            coerced = pd.to_numeric(non_null.str.replace(",", "", regex=False), errors="coerce")
            frac_num = coerced.notna().mean() if len(coerced) else 0
            if 0.9 <= frac_num < 1.0 or (frac_num == 1.0 and len(non_null) > 0):
                # only flag if it's genuinely a number column stored as text
                if frac_num >= 0.95:
                    issues.append({
                        "id": f"numtext::{col}", "type": "numeric_as_text", "column": col,
                        "title": f"“{col}” looks numeric but is stored as text",
                        "severity": "medium", "count": int(coerced.notna().sum()),
                        "detail": "Values parse as numbers — coercing enables math/aggregation.",
                        "sample": _samples([str(v) for v in non_null.unique()[:_MAX_SAMPLE]]),
                        "fix": {"kind": "to_numeric"}, "fix_label": "Convert to a number"})

        # 6. negatives where the column name implies non-negative
        if pd.api.types.is_numeric_dtype(s) and _NONNEG.search(str(col)):
            neg_mask = s < 0
            if neg_mask.any():
                c = int(neg_mask.sum())
                issues.append({
                    "id": f"neg::{col}", "type": "negative_values", "column": col,
                    "title": f"{c} negative values in “{col}”",
                    "severity": "high", "count": c,
                    "detail": "Negatives in a column that should be ≥ 0 (likely a bug).",
                    "sample": _samples([str(v) for v in s[neg_mask].unique()[:_MAX_SAMPLE]]),
                    "fix": {"kind": "drop_negatives"}, "fix_label": "Exclude negatives from analysis"})

        # 7. numeric outliers (IQR) — only for reasonably-sized numeric columns
        if pd.api.types.is_numeric_dtype(s) and s.notna().sum() > 20:
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
                out_mask = (s < lo) | (s > hi)
                c = int(out_mask.sum())
                if 0 < c <= max(1, int(0.05 * n)):     # only if outliers are a small minority
                    issues.append({
                        "id": f"outlier::{col}", "type": "outliers", "column": col,
                        "title": f"{c} extreme outliers in “{col}”",
                        "severity": "low", "count": c,
                        "detail": f"Values outside [{lo:.1f}, {hi:.1f}] (3×IQR).",
                        "sample": _samples([str(v) for v in s[out_mask].unique()[:_MAX_SAMPLE]]),
                        "fix": {"kind": "clip_outliers", "lo": float(lo), "hi": float(hi)},
                        "fix_label": "Clip to the 3×IQR fence"})

        # 8. constant column
        if s.nunique(dropna=True) == 1 and n > 1:
            issues.append({
                "id": f"const::{col}", "type": "constant_column", "column": col,
                "title": f"“{col}” is constant (one value)", "severity": "low", "count": n,
                "detail": "No information — every row is the same.",
                "sample": _samples([str(s.dropna().iloc[0])]) if s.notna().any() else [],
                "fix": {"kind": "drop_column"}, "fix_label": "Drop the column"})

    sev_rank = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (sev_rank.get(i["severity"], 3), -i["count"]))
    return {"rows": n, "cols": len(df.columns), "columns": list(map(str, df.columns)),
            "issues": issues}


# --------------------------------------------------------------------------- #
#  applying fixes (non-destructive — returns a cleaned copy)                    #
# --------------------------------------------------------------------------- #
def apply_fixes(df, issues):
    """Apply each issue's proposed fix to a COPY of df. Returns (clean_df, log[])."""
    out = df.copy()
    log = []
    for issue in issues:
        fix = issue.get("fix", {})
        kind = fix.get("kind")
        col = issue.get("column")
        try:
            if kind == "drop_duplicate_rows":
                before = len(out); out = out.drop_duplicates(keep="first")
                log.append(f"dropped {before - len(out)} duplicate rows")
            elif kind == "fill_missing":
                if fix.get("strategy") == "median" and pd.api.types.is_numeric_dtype(out[col]):
                    out[col] = out[col].fillna(out[col].median())
                else:
                    m = out[col].mode(dropna=True)
                    out[col] = out[col].fillna(m.iloc[0] if len(m) else "")
                log.append(f"filled missing in {col}")
            elif kind == "strip_whitespace":
                out[col] = out[col].astype(str).str.strip().where(out[col].notna())
                log.append(f"trimmed whitespace in {col}")
            elif kind == "normalize_case":
                non_null = out[col].dropna().astype(str)
                keyed = non_null.str.strip().str.lower()
                canon = {}
                for key, grp in non_null.groupby(keyed):
                    canon[key] = grp.value_counts().idxmax()      # most common spelling
                out[col] = out[col].apply(
                    lambda v: canon.get(str(v).strip().lower(), v) if pd.notna(v) else v)
                log.append(f"normalised labels in {col}")
            elif kind == "to_numeric":
                out[col] = pd.to_numeric(out[col].astype(str).str.replace(",", "", regex=False),
                                         errors="coerce")
                log.append(f"converted {col} to numeric")
            elif kind == "drop_negatives":
                before = len(out); out = out[~(out[col] < 0)]
                log.append(f"excluded {before - len(out)} negative rows in {col}")
            elif kind == "clip_outliers":
                out[col] = out[col].clip(fix["lo"], fix["hi"])
                log.append(f"clipped outliers in {col}")
            elif kind == "drop_column":
                out = out.drop(columns=[col]); log.append(f"dropped column {col}")
        except Exception as e:
            log.append(f"skip {issue.get('id')}: {e}")
    return out, log


def summarize(prof):
    lines = [f"Profiled {prof['rows']} rows × {prof['cols']} columns.",
             f"Found {len(prof['issues'])} data-quality issue(s):", ""]
    for i in prof["issues"]:
        lines.append(f"  [{i['severity']:<6}] {i['title']}")
        if i["sample"]:
            lines.append(f"            e.g. {', '.join(i['sample'])}")
    if not prof["issues"]:
        lines.append("  (clean — nothing flagged)")
    return "\n".join(lines)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    if not args:
        print("usage: profiler.py [--json] [--clean all] <file>"); sys.exit(1)
    path = args[-1]
    df = load_any(path)
    prof = profile(df)
    if "--json" in flags:
        print(json.dumps(prof, indent=2, default=str))
    elif "--clean" in flags:
        clean, log = apply_fixes(df, prof["issues"])
        out = os.path.splitext(path)[0] + ".cleaned.csv"
        clean.to_csv(out, index=False)
        print(summarize(prof)); print("\nApplied:", "; ".join(log)); print("Wrote:", out)
    else:
        print(summarize(prof))
