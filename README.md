# FlowDash DS-Agent — a data-science workflow UX demo

A **demo**, not a production tool. Its purpose is to explore where an agent UX adds
value across the five stages of a data-science workflow — **cleaning → key-driver →
storytelling → alert → orchestration** — driven entirely by **plain-English
conversation** for a non-technical user (our fictional PM, **Maya**).

It is built to be run **inside Claude Code**: the "agent" is Claude Code itself,
orchestrated by [`CLAUDE.md`](CLAUDE.md), calling **skills** that call **tools** that
query a single SQLite file. Mock UI "components" are rendered as self-contained HTML
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

## The UI — two ways to see it

The conversation *is* the primary interface (the agent is Claude Code driven by
`CLAUDE.md`). On top of that there are two visual front-ends, both reproducing the
Jetski **chat + canvas** layout (Material 3 dark, blue/cyan):

### 1. Live backend (real queries) — `server/app.py`
A real, typeable chat wired to the database. Type a question (or paste a `SELECT…`);
the backend routes intent to the actual tools, runs **real SQL against the real
SQLite**, and mounts the result/card/chart in the canvas. Cleaning **approval buttons
are functional** (Approve/Skip flips each issue to an "Applied" state, non-destructive).

```bash
python data/build_db.py && python tools/viz_tool.py all   # data + charts (once)
python server/app.py                                       # → http://localhost:8000
#   PORT=9000 python server/app.py    to change port
```
Pure standard-library Python — no Flask, no pip installs. Intent routing is rule-based
by default; if `ANTHROPIC_API_KEY` is set, the NL→SQL hook (`web/render.py`) can upgrade
`/api/ask` to true text-to-SQL.

### 2. Static scripted preview (no server) — `web/index.html`
One self-contained file (charts inlined), zero setup. Maya clicks a question → the
agent plays a reasoning trace → answers → mounts the card. Good for a hosted link.

```bash
python web/build_web.py        # regenerate web/index.html
# open web/index.html directly, or:  python -m http.server -d web 8000
```

**Hosted link:** connect this repo to Vercel (Add New → Project → import
`ashlithos/datascience`). `vercel.json` + `.vercelignore` serve `web/index.html` at the
root, so every push/PR gets a preview URL. (The build sandbox can't reach Vercel —
network is scoped to the repo — so trigger the deploy from your side via the git
integration or `npx vercel deploy`. The live backend needs a host that runs Python.)

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
