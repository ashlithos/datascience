---
name: key-driver-analysis
description: >
  Explain WHY a metric moved by scanning single dimensions and pairwise crossings to
  find where the change concentrates, then report the driver with a confidence score
  and an evidence trail. Use when the user asks "why did X go up/down", "what's
  driving", "what caused the drop", or any diagnostic question about a metric trend
  (e.g. "why is weekly active down?"). Always expose the combinations you checked.
---

# Key-Driver Analysis (route-C orchestration)

The signature demo moment. A single-dimension cut only shows a diffuse, misleading
dip; **crossing dimensions localises the real cause**. On FlowDash, WAU is down ~18%,
but the cause is the interaction `platform=android × user_type=new` (~−61%) — every
sibling cell is flat. Single cuts (platform=android −41%, user_type=new −35%) point
vaguely but don't isolate it.

## When to use
Any "why did <metric> change?" question. Default metric = Weekly Active Users.

## Procedure
1. **Clean first.** Use the cleaning recipe (`duration_sec>0`, `region_clean`,
   de-dupe) so the scan isn't fooled by dirty rows. (Invoke `data-cleaning` if the
   user hasn't cleaned yet — at least mention you applied the clean recipe.)
2. **Run the scan engine** (it tries single dims AND pairwise crossings, ranks them,
   and computes confidence):
   ```bash
   python tools/key_driver.py            # human-readable summary
   python tools/key_driver.py --json     # structured (drives the card)
   ```
3. **Summon the finding card** (confidence meter + embedded chart + collapsible
   evidence — the takeover point):
   ```bash
   python tools/viz_tool.py driver       # chart the winning crossing
   python tools/components.py key-driver  # -> reports/card_key_driver.html
   ```
4. **Report like a colleague:**
   - Lead with the answer + confidence: *"82–92% sure it's android × new."*
   - State plainly it is **not** platform-wide or new-user-wide (kill the wrong
     single-dimension conclusions explicitly).
   - Offer the evidence trail: *"Want to see the 55 combinations I checked?"*

## Confidence (be honest about it)
The score is a heuristic over: how much harder the top cell fell vs the headline,
its share of the base, and whether sibling cells are flat. Present it as a
probabilistic claim, not a fact. Direct the user to the evidence before they act.

## UX intent to preserve
- The **"▸ Show the evidence"** disclosure is mandatory — it's where a skeptical
  human takes over and audits the reasoning.
- Show the *misleading* single-dimension cuts too, not just the answer — the
  contrast ("each single cut lied a little") is the insight.
