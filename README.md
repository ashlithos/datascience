# FlowDash DS-Agent — a data-science workflow UX demo

A **demo**, not a production tool. Its purpose is to explore where an agent UX adds
value across the five stages of a data-science workflow — **cleaning → key-driver →
storytelling → alert → orchestration** — driven entirely by **plain-English
conversation** for a non-technical user (our fictional PM, **Maya**).

It runs as a **real agent** two ways: (1) inside Claude Code, orchestrated by
[`CLAUDE.md`](CLAUDE.md); and (2) as a standalone **Claude Agent SDK** loop
([`server/agent.py`](server/agent.py)) behind a web UI — an LLM that reads the skills,
decides which tools to call, runs real SQL, and streams its reasoning so you can review
it. Both call the same **skills → tools → SQLite** stack. UI "components" are Material 3
cards with embedded charts.

> **Design note.** The visual language is the **Jetski** design system (Material 3
> dark, Google-blue primary + cyan accent), reproduced from
> [`jetski-design/`](jetski-design/) (`DESIGN.md` + `globals.css` + `ui.tsx`). It
> lives entirely in [`assets/theme.css`](assets/theme.css) as design tokens, so the
> whole demo re-themes from one file.

## Architecture (three layers)
```
Maya → AGENT (CLAUDE.md) → SKILLS (.claude/skills/*) → TOOLS (tools/*.py) → DATA (flowdash.db + dictionary)
```

## Layout
```
.claude/skills/
  data-cleaning/        custom thin skill — detect & approve-gated fixes
  key-driver-analysis/  custom thin skill — scan dims+crossings, confidence + evidence
  storytelling/         custom thin skill — B/C narrative bench
  pdf/  xlsx/           official-skill STUBS (install via openskills; see their SKILL.md)
data/
  flowdash.db           the synthetic dataset (generated)
  build_db.py           deterministic generator (re-run to rebuild)
data_dictionary.md      text-to-SQL source of truth (semantic traps + clean recipes)
tools/
  sql_tool.py           read-only text-to-SQL → markdown
  key_driver.py         the key-driver scan/orchestration engine
  viz_tool.py           matplotlib charts → reports/*.png
  components.py          mock HTML cards (key-driver / alert / cleaning) → reports/*.html
assets/theme.css        design tokens (the only place style lives)
reports/                generated charts, cards, and B/C stories
CLAUDE.md               the orchestration / dispatch layer
exploration-log.md      the UX exploration findings (a deliverable)
```

## The UI — a real agent you can review

The live app (`server/app.py`) reproduces the Jetski **chat + canvas** layout
(Material 3 dark) and runs in two engines, switchable in the header:

### Agent mode — a REAL agentic loop (default)
`server/agent.py` runs a genuine LLM agent via the **Claude Agent SDK**. It reads the
project's **skills** (`.claude/skills/*`) and `data_dictionary.md`, **decides which
tools to call**, runs **real SQL** against the real SQLite, and **streams its
thinking + tool calls + answer** to the UI over Server-Sent Events — so you can review
exactly how it reasoned. The data-science toolbelt (`run_sql`, `key_driver_analysis`,
`feature_adoption`, `error_scan`, `wau_trend`, `detect_data_issues`, `storytelling`) is
exposed as in-process SDK tools that also render the Material 3 cards. It's read-only
(no Bash/Write); cleaning **writes stay gated** behind the UI's approval buttons.

```bash
pip install -r requirements.txt        # matplotlib, pandas, claude-agent-sdk
python data/build_db.py && python tools/viz_tool.py all
python server/app.py                    # → http://localhost:8000
#   AGENT_MODEL=claude-sonnet-4-6 python server/app.py   # faster model
```
**Auth:** the SDK drives the `claude` CLI, so install it (`npm i -g
@anthropic-ai/claude-code`, then run `claude` once to log in) **or** set
`ANTHROPIC_API_KEY`. If the SDK/auth isn't present, the server logs it and silently
falls back to Fast mode — the app still works.

### Fast mode — deterministic rule router
A zero-LLM intent router (`web/render.py`) that maps the question to a real query and
renders the same cards instantly. Pure standard library. Good for offline/snappy demos;
also the automatic fallback. Cleaning **approval buttons are functional** in both modes.

### Static scripted preview (no server) — `web/index.html`
One self-contained file (charts inlined), zero setup — Maya clicks a question → scripted
reasoning trace → card. This is what gets the **hosted link**: connect the repo to Vercel
(Add New → Project → import `ashlithos/datascience`); `vercel.json` + `.vercelignore`
serve it at the root, so every push/PR gets a preview URL. (The agent backend needs a
host that runs Python + has SDK auth; the static page is pure front-end.)

```bash
python web/build_web.py        # regenerate; then open web/index.html
```

## Setup
```bash
pip install matplotlib pandas      # plotting + data
python data/build_db.py            # build data/flowdash.db (deterministic)
```
Optional, to preview the HTML cards as images:
```bash
pip install playwright             # Chromium is pre-installed in this env
```

## The four data "hooks" (why each stage has something real to bite)
| Hook | For stage | What's in the data |
|---|---|---|
| Dirty rows | Cleaning | ~35 duplicate sessions, ~28 negative durations, EMEA spelled 4 ways |
| Hidden interaction | Key-driver | WAU −18%, but the cause is `android × new` (−61%); single dims mislead |
| Quiet uptrend | Storytelling | `sql_export` adoption up ~3× (5% → 15% of sessions) |
| Threshold breach | Alert | Week-6 EMEA error rate ~7% (>5%), in the 2h after deploy `v2026.06.03` |

## Demo script (try these as Maya)
1. **"Is this data clean enough to trust?"** → cleaning scan + approval panel.
2. **"Why is weekly active down?"** → the key-driver "wow": `android × new`, 92%
   confidence, with a *Show the evidence* trail. *(P0 main line.)*
3. **"Write me the weekly summary."** → two reports, `story_C.md` (fixed) vs
   `story_B.md` (agent-structured, leads on the `sql_export` surprise).
4. **"Assume a week passed."** → the agent proactively raises the EMEA error alert.

## Run the pieces directly
```bash
python tools/key_driver.py                 # the driver finding (text)
python tools/viz_tool.py all               # all charts
python tools/components.py all             # all mock cards → reports/*.html
python tools/sql_tool.py "SELECT week, COUNT(DISTINCT user_id) wau FROM sessions WHERE duration_sec>0 GROUP BY week"
```

## Scope (per the brief)
- **P0 (done):** FlowDash + dictionary with all four hooks; key-driver interactive
  end-to-end; three-layer architecture runs.
- **P1 (done):** storytelling B/C bench; an autonomous mode (alert + simulated
  time-jump, weekly digest); mock components with *Show the evidence* takeover points.
- **P2 (interfaces stubbed):** cleaning action-triggered autonomy + approval surface
  (panel renders; "apply" is non-destructive/simulated); PDF/RAG line (stubbed,
  deferred); multi-skill pipeline transparency.
```
