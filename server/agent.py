"""
agent.py — the REAL agentic loop for the FlowDash DS-agent, via the Claude Agent SDK.

This is the genuine article: an LLM running an agentic loop, deciding which tools to
call, reading the project's skills + data dictionary, and answering Maya like a
colleague. It authenticates through the ambient Claude Code session (the OAuth token
this process already has) — no API key required.

Design:
  - The data-science toolbelt is exposed as IN-PROCESS SDK MCP tools (run_sql,
    key_driver_analysis, feature_adoption, error_scan, wau_trend, detect_data_issues,
    storytelling). Because they run in this very process, each tool can ALSO push a
    rendered "canvas artifact" (the Material 3 card) onto a per-run queue so the UI
    can mount it — the model gets text, the human gets the rich card.
  - The agent additionally has read-only Read/Grep/Glob so it can consult
    data_dictionary.md and the skills itself. No Bash/Write/Edit — mutation stays
    gated (cleaning *apply* happens via the UI's approval buttons, not the agent).
  - run_stream() normalises the SDK message stream into simple events
    (thinking / tool / tool_result / text / artifact / done) for the SSE endpoint.

If the SDK or its auth is unavailable, server/app.py falls back to the rule router.
"""
import contextvars
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "web"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import render          # noqa: E402  shared canvas builders + sqlite helpers
import sql_tool        # noqa: E402

from claude_agent_sdk import (  # noqa: E402
    query, tool, create_sdk_mcp_server, ClaudeAgentOptions,
    AssistantMessage, UserMessage, ResultMessage,
    TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock,
    PermissionResultAllow, PermissionResultDeny,
)

# per-run artifact sink (set at the top of run_stream; tools push canvases here)
_artifacts: "contextvars.ContextVar[list]" = contextvars.ContextVar("artifacts", default=None)


def _emit_artifact(html):
    sink = _artifacts.get()
    if sink is not None and html:
        sink.append(html)


def _txt(s):
    return {"content": [{"type": "text", "text": s}]}


# --------------------------------------------------------------------------- #
#  the data-science toolbelt (real execution against the real SQLite)          #
# --------------------------------------------------------------------------- #
@tool("run_sql", "Run a single read-only SQL SELECT/WITH query against the FlowDash "
      "SQLite database and get a markdown table back. Consult data_dictionary.md for "
      "schema and the semantic traps. Use this for any custom slice.",
      {"sql": str})
async def run_sql(args):
    sql = (args or {}).get("sql", "")
    try:
        cols, rows = sql_tool.run(sql)
    except Exception as e:
        return _txt(f"SQL error: {e}")
    md = sql_tool.to_markdown(cols, rows)
    _, canvas = render.canvas_sql(sql)
    _emit_artifact(canvas)
    return _txt(md + f"\n\n({len(rows)} rows)")


@tool("key_driver_analysis", "Explain WHY weekly active users (WAU) changed: scans all "
      "single dimensions AND pairwise crossings, returns the top driver cell with a "
      "confidence score and the full evidence table. Use for any 'why did X change' question.",
      {})
async def key_driver_analysis(args):
    R = render.scan()
    T, O = R["top_driver"], R["overall"]
    _emit_artifact(render.canvas_driver(R))
    lines = [f"Metric: {R['metric']}",
             f"Overall wk{O['first_week']}->wk{O['last_week']}: {O['wau_first']}->{O['wau_last']} ({O['change_pct']}%)",
             f"Scanned {R['combos_tried']} combinations.",
             f"TOP DRIVER: {T['value']} = {T['change_pct']}% ({T['share_of_base']}% of base). Confidence {R['confidence']}%.",
             "Single-dimension cuts (misleading): " +
             "; ".join(f"{s['dim']}={s['value']} {s['change_pct']}%" for s in R['singles'][:4]),
             "Evidence (all cells of the winning crossing):"]
    for e in R["evidence"]:
        lines.append(f"  {e['cell']}: {e['first']}->{e['last']} ({e['change_pct']:+.0f}%)"
                     + ("  <== cause" if e["is_cause"] else ""))
    return _txt("\n".join(lines))


@tool("feature_adoption", "Report adoption trend for a feature (default sql_export) as a "
      "weekly share of sessions. Surfaces the quiet-growth story.",
      {"feature": str})
async def feature_adoption(args):
    _emit_artifact(render.canvas_feature())
    rows = render._q(
        "SELECT s.week, ROUND(100.0*COUNT(DISTINCT CASE WHEN f.feature='sql_export' "
        "THEN s.session_id END)/COUNT(DISTINCT s.session_id),1) pct "
        "FROM sessions s LEFT JOIN feature_events f USING(session_id) "
        "WHERE duration_sec>0 GROUP BY s.week ORDER BY s.week")
    series = ", ".join(f"wk{r['week']}={r['pct']}%" for r in rows)
    return _txt(f"sql_export share of sessions by week: {series}. ~3x growth.")


@tool("error_scan", "Scan error rates by region and week to find threshold breaches "
      "(>5%). Returns the week-6 EMEA breach and its post-deploy concentration.",
      {})
async def error_scan(args):
    _emit_artifact(render.canvas_alert())
    rows = render._q(
        f"SELECT {render.REGION_CLEAN} region, ROUND(100.0*SUM(had_error)/COUNT(*),2) err "
        "FROM sessions WHERE week=6 GROUP BY region ORDER BY err DESC")
    s = "; ".join(f"{r['region']} {r['err']}%" for r in rows)
    return _txt(f"Week-6 error rate by region: {s}. EMEA breaches 5%, concentrated in the "
                "~2h after deploy v2026.06.03.")


@tool("wau_trend", "Get the weekly active users trend (cleaned: deduped, duration>0).", {})
async def wau_trend(args):
    _emit_artifact(render.canvas_wau())
    rows = render._q("SELECT week, COUNT(DISTINCT user_id) wau FROM sessions "
                     "WHERE duration_sec>0 GROUP BY week ORDER BY week")
    return _txt("WAU by week: " + ", ".join(f"wk{r['week']}={r['wau']}" for r in rows))


@tool("detect_data_issues", "Detect data-quality issues (duplicates, negative durations, "
      "inconsistent region spelling) WITHOUT changing anything. Renders the approval "
      "panel; the human approves fixes via the UI buttons (writes stay gated).",
      {})
async def detect_data_issues(args):
    _emit_artifact(render.canvas_cleaning())
    dups = render._q("SELECT COUNT(*) c FROM (SELECT session_id FROM sessions GROUP BY "
                     "session_id HAVING COUNT(*)>1)")[0]["c"]
    negs = render._q("SELECT COUNT(*) c FROM sessions WHERE duration_sec<0")[0]["c"]
    spell = [r["region"] for r in render._q(
        "SELECT DISTINCT region FROM sessions WHERE "
        "REPLACE(UPPER(TRIM(region)),'.','')='EMEA' ORDER BY 1")]
    return _txt(f"Found 3 issues (read-only): {dups} duplicate session rows; {negs} negative "
                f"durations; region spelled {spell}. Proposed fixes shown for approval. "
                "I will not write anything until the user approves.")


@tool("storytelling", "Produce the weekly summary in two structures: C (fixed template) "
      "and B (agent-decided, may open on the sql_export surprise). Renders both.",
      {})
async def storytelling(args):
    _emit_artifact(render.canvas_story())
    return _txt("Wrote two versions. C = Overview/Findings/Evidence/Recs (predictable). "
                "B = agent-structured, leads on the sql_export good-news hook. Both cite the "
                "same facts: WAU -18%, android x new -61%, sql_export ~3x, EMEA wk6 errors ~7%.")


@tool("profile_data", "Profile the user's UPLOADED dataset (any CSV/TSV/JSON/Excel) for "
      "data-quality issues — duplicates, nulls, whitespace, inconsistent labels, "
      "numeric-as-text, bad negatives, outliers, constant columns — and render the "
      "approval panel. Use this for 'is my data clean' when a file has been uploaded; "
      "detection only, writes stay gated behind the panel's buttons.",
      {})
async def profile_data(args):
    u = render.UPLOAD
    if u["df"] is None:
        return _txt("No dataset uploaded yet — ask the user to upload a CSV with the file button.")
    _emit_artifact(render.canvas_profile())
    lines = [f"Profiled {u['name']}: {len(u['df'])} rows × {u['df'].shape[1]} columns. "
             f"Found {len(u['issues'])} issue(s):"]
    for it in u["issues"]:
        lines.append(f"  [{it['severity']}] {it['title']}")
    lines.append("Proposed fixes shown for approval; nothing is written until the user approves.")
    return _txt("\n".join(lines))


DS_TOOLS = [run_sql, key_driver_analysis, feature_adoption, error_scan,
            wau_trend, detect_data_issues, storytelling, profile_data]
TOOL_NAMES = ["mcp__ds__" + t.name for t in DS_TOOLS]


SYSTEM_PROMPT = """You are FlowDash's data-science agent, talking to Maya, a non-technical
product manager. Answer like a trusted colleague, not a query console.

Rules:
- Lead with the answer in plain English. Keep SQL/methods in the background.
- ALWAYS use a tool to get real numbers before answering — never invent figures.
  Prefer the specialised tools (key_driver_analysis, feature_adoption, error_scan,
  wau_trend, detect_data_issues, storytelling); use run_sql for anything custom.
- The data is synthetic and has dirty rows; the tools already apply the clean recipe
  (dedupe, duration>0, region normalisation). Mention you used cleaned data.
- Every probabilistic claim (a driver, a confidence score) must be offered with its
  evidence — tell Maya she can open the evidence on the right.
- Detection is free (read-only); WRITING/changing data needs Maya's approval. Never
  claim you changed data — propose, and let her approve via the panel.
- If the user has UPLOADED their own dataset, use `profile_data` for cleaning/quality
  questions (it works on any CSV); otherwise the FlowDash tools above apply.
- Be concise: 2-5 sentences. The rich card on the right carries the detail.
- Consult data_dictionary.md (via Read) if you're unsure about a field; it documents
  traps like duration_sec vs active_sec, user_type vs plan, export_csv vs sql_export.

Default metric for "why is usage down" questions is Weekly Active Users (WAU)."""


_ALLOW_BUILTIN = {"Read", "Grep", "Glob"}


async def _can_use(name, tool_input, ctx):
    """Allow-list permission callback (headless-safe; avoids the root-blocked
    --dangerously-skip-permissions flag). Approves our DS tools + read-only builtins,
    denies anything that could mutate or reach the network."""
    if name in TOOL_NAMES or name in _ALLOW_BUILTIN:
        return PermissionResultAllow()
    return PermissionResultDeny(message=f"{name} is not permitted in this demo")


def _options():
    server = create_sdk_mcp_server(name="ds", version="1.0.0", tools=DS_TOOLS)
    return ClaudeAgentOptions(
        mcp_servers={"ds": server},
        allowed_tools=TOOL_NAMES + ["Read", "Grep", "Glob"],
        disallowed_tools=["Bash", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch"],
        system_prompt=SYSTEM_PROMPT,
        permission_mode="acceptEdits",    # headless; our tools are pre-approved below
        setting_sources=["project"],      # load CLAUDE.md + .claude/skills
        skills="all",
        cwd=os.path.abspath(ROOT),
        max_turns=14,
        model=os.environ.get("AGENT_MODEL") or None,
        env={**os.environ},
    )


def available():
    return True


async def run_stream(question):
    """Yield normalised events for one user turn:
      {type:'tool',name,input} {type:'thinking',text} {type:'tool_result',name}
      {type:'text',text} {type:'artifact',html} {type:'done',cost,turns} {type:'error',msg}
    """
    sink = []
    _artifacts.set(sink)
    emitted_artifacts = 0
    answer_parts = []
    try:
        async for msg in query(prompt=question, options=_options()):
            if isinstance(msg, AssistantMessage):
                for b in msg.content:
                    if isinstance(b, ThinkingBlock):
                        yield {"type": "thinking", "text": b.thinking}
                    elif isinstance(b, ToolUseBlock):
                        name = b.name.replace("mcp__ds__", "")
                        yield {"type": "tool", "name": name, "input": b.input}
                    elif isinstance(b, TextBlock):
                        answer_parts.append(b.text)
                        yield {"type": "text", "text": b.text}
            elif isinstance(msg, UserMessage):
                for b in (msg.content if isinstance(msg.content, list) else []):
                    if isinstance(b, ToolResultBlock):
                        yield {"type": "tool_result"}
            elif isinstance(msg, ResultMessage):
                pass
            # drain any artifacts produced so far
            while emitted_artifacts < len(sink):
                yield {"type": "artifact", "html": sink[emitted_artifacts]}
                emitted_artifacts += 1
    except Exception as e:
        yield {"type": "error", "msg": f"{type(e).__name__}: {e}"}
        return
    yield {"type": "done", "answer": "".join(answer_parts)}


if __name__ == "__main__":
    import anyio

    async def _demo():
        q = " ".join(sys.argv[1:]) or "Why is weekly active down?"
        async for ev in run_stream(q):
            print(json.dumps(ev)[:200])
    anyio.run(_demo)
