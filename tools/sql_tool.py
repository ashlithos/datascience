"""
sql_tool.py — read-only SQL over FlowDash, returned as a markdown table.

This is the agent's text-to-SQL execution tool. The agent writes a query (guided
by data_dictionary.md), runs it here, and gets back a clean markdown table it can
drop straight into the conversation.

Usage:
    python tools/sql_tool.py "SELECT week, COUNT(DISTINCT user_id) wau FROM sessions GROUP BY week"
    python tools/sql_tool.py -f path/to/query.sql
    python tools/sql_tool.py --json "SELECT ..."   # machine-readable output

Safety: only a single read-only statement (SELECT / WITH) is allowed.
"""
import argparse
import json
import os
import re
import sqlite3
import sys

DB = os.path.join(os.path.dirname(__file__), "..", "data", "flowdash.db")
WRITE = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|pragma)\b", re.I)


def run(sql):
    sql = sql.strip().rstrip(";").strip()
    if ";" in sql:
        raise ValueError("Only a single statement is allowed (no ';').")
    if not re.match(r"^\s*(select|with)\b", sql, re.I) or WRITE.search(sql):
        raise ValueError("Only read-only SELECT/WITH queries are permitted.")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(sql).fetchall()
    finally:
        con.close()
    cols = rows[0].keys() if rows else []
    return cols, [list(r) for r in rows]


def to_markdown(cols, rows, limit=100):
    if not cols:
        return "_(query returned no columns)_"
    if not rows:
        return "_(0 rows)_"
    out = ["| " + " | ".join(cols) + " |",
           "| " + " | ".join("---" for _ in cols) + " |"]
    for r in rows[:limit]:
        out.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    if len(rows) > limit:
        out.append(f"\n_…{len(rows) - limit} more rows (showing first {limit})._")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sql", nargs="?", help="SQL string")
    ap.add_argument("-f", "--file", help="read SQL from file")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    ap.add_argument("--limit", type=int, default=100)
    a = ap.parse_args()
    sql = open(a.file).read() if a.file else a.sql
    if not sql:
        ap.error("provide a SQL string or -f file")
    try:
        cols, rows = run(sql)
    except Exception as e:
        print(f"❌ SQL error: {e}", file=sys.stderr)
        sys.exit(1)
    if a.json:
        print(json.dumps({"columns": list(cols), "rows": rows}, default=str))
    else:
        print(to_markdown(cols, rows, a.limit))
        print(f"\n_({len(rows)} row(s).)_")


if __name__ == "__main__":
    main()
