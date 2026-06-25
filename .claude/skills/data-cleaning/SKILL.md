---
name: data-cleaning
description: >
  Detect and (with the user's approval) fix data-quality issues in FlowDash before
  any analysis is trusted. Use when the user asks to "clean", "check the data",
  "is this data ok", or before running aggregates that the dirty rows would distort
  (duplicates, negative durations, inconsistent region spelling). Detection is
  automatic and read-only; every WRITE waits for explicit per-issue approval.
---

# Data Cleaning (shallow-autonomy, approval-gated)

The agent **scans and proposes**, the human **approves**. This is the demo's
"shallow autonomy" pattern: discovery is safe to do unprompted (read-only), but
acting (writing/excluding/normalising) must be ratified.

## When to use
- User asks to clean / validate the data, OR
- You are about to compute aggregates and the known dirty rows would skew them
  (always true for WAU, error rates, region breakdowns on FlowDash).

## Known issues in FlowDash (see `data_dictionary.md` → Data quality)
1. **Duplicate session rows** — same `session_id` logged twice (~35).
2. **Negative `duration_sec`** — clock bug (~28 rows).
3. **Inconsistent `region`** — EMEA as `EMEA` / `emea` / `E.M.E.A` / `" EMEA "`.

## Procedure
1. **Detect (read-only, no approval needed).** Run the detection queries:
   ```bash
   python tools/sql_tool.py "SELECT session_id, COUNT(*) c FROM sessions GROUP BY session_id HAVING c>1"
   python tools/sql_tool.py "SELECT COUNT(*) FROM sessions WHERE duration_sec<0"
   python tools/sql_tool.py "SELECT DISTINCT region FROM sessions ORDER BY 1"
   ```
2. **Propose, don't act.** Render the approval panel and present it:
   ```bash
   python tools/components.py cleaning   # -> reports/panel_cleaning.html
   ```
   Summarise each issue, the proposed fix, and offer per-issue choices
   (Approve / Show sample / Skip). **Do not write anything yet.**
3. **On approval**, apply the fix as a *non-destructive view*, never by mutating
   source rows. The canonical clean recipe is `region_clean` + `duration_sec>0` +
   de-dupe on `session_id` (recipes are in `data_dictionary.md`). For the demo,
   "applying" means: use the clean recipe in all downstream queries and say so.

## UX intent to preserve
- The **approval surface** is the star: show issues *by type*, with a representative
  sample, not a wall of rows.
- Make the read-only/write boundary explicit in words ("I can spot these on my own;
  I won't change anything until you say so").
- Never silently clean — the user must see what was wrong and what you'll do.
