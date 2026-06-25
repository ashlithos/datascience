# FlowDash DS-Agent — a data-science workflow UX demo

A **demo**, not a production tool. Its purpose is to explore where an agent UX adds
value across the five stages of a data-science workflow — **cleaning → key-driver →
storytelling → alert → orchestration** — driven entirely by **plain-English
conversation** for a non-technical user (our fictional PM, **Maya**).

It is built to be run **inside Claude Code**: the "agent" is Claude Code itself,
orchestrated by [`CLAUDE.md`](CLAUDE.md), calling **skills** that call **tools** that
query a single SQLite file. Mock UI "components" are rendered as self-contained HTML
cards with embedded charts.

> **Design note.** The visual language lives entirely in
> [`assets/theme.css`](assets/theme.css) as design tokens, so it can be re-skinned to
> match the prior **Jetski** demo in one file once that repo is reachable from the
> sandbox. (It wasn't at build time — network is scoped to this repo.)

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
