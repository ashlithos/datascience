---
name: storytelling
description: >
  Turn findings into a narrative report (markdown + charts) for a non-technical
  reader. Use when the user asks for a "summary", "writeup", "report", "weekly
  digest", "tell the story", or "make this presentable". Supports two modes — C
  (fixed structure: Overview → Key findings → Evidence → Recommendations) and B
  (agent decides the structure, may lead with a surprise hook). Offer both for
  comparison when the user wants to see the difference.
---

# Storytelling (B vs C comparison bench)

Same facts, two narrative strategies. The demo shows the trade-off between a
**predictable** template and an agent that exercises **on-the-spot editorial
judgment**.

## When to use
Any request to summarise / write up / present findings, or to produce a weekly digest.

## Inputs (gather facts first)
Run the analyses you'll narrate, so both versions cite real numbers:
```bash
python tools/key_driver.py            # the WAU decline + driver
python tools/viz_tool.py wau feature  # trend charts
python tools/sql_tool.py "SELECT week, ROUND(100.0*COUNT(DISTINCT CASE WHEN feature='sql_export' THEN session_id END)/COUNT(DISTINCT s.session_id),1) FROM sessions s LEFT JOIN feature_events f USING(session_id) GROUP BY week"
```
The hidden good-news angle to surface: **`sql_export` is quietly up ~3×** while WAU
falls — a positive story buried under the headline decline.

## Version C — fixed structure (predictable)
Always these four sections, in this order:
1. **Overview** — the headline metric and the one-line takeaway.
2. **Key findings** — bulleted, each with a number.
3. **Evidence** — charts + the cross-tab / query trail.
4. **Recommendations** — concrete next steps.

Write it to `reports/story_C.md`. Strength: scannable, comparable week to week,
never buries the lede in the wrong place.

## Version B — agent-decided structure (editorial)
You choose the shape. You MAY:
- open with the surprise (e.g. lead on "sql_export is taking off" as a hook, then
  pivot to the WAU risk),
- merge or reorder sections, add a "what I'd watch next" aside,
- pick the framing that best serves *this* set of facts.
Write it to `reports/story_B.md`. Strength: a human-feeling narrative that can catch
a signal a template would bury. Risk: less predictable, can over-reach.

## Presenting the comparison
Show both, then name the trade-off out loud:
*"C is predictable and audit-friendly; B noticed sql_export deserved the opening and
restructured around it. C is safer for a recurring report; B is better for a one-off
exec read."* Let the human feel C's predictability vs B's judgment.

## UX intent to preserve
- Both versions must be **honest about the same numbers** — only the *structure*
  differs, never the facts.
- For a **scheduled weekly digest**, design it to be *worth opening*: lead with the
  one thing that changed, not a wall of unchanged metrics.
