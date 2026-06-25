# Exploration Log — FlowDash DS-Agent

The point of this demo is not "does it work" but **where does an agent UX add value**
across the five workflow stages. Per stage: the spark, why it sparks, the trust gap,
the takeover point, how it compares to existing products, and a one-line insight.
Cross-cutting observations follow at the end.

> These are field notes taken *while building*, to be pared down later. Honest about
> where the demo idealises vs. what the data actually shows.

---

## ① Data Cleaning  — *actor + shallow autonomy*

- **Most spark moment:** The approval panel that groups issues **by type** with a
  representative sample ("28 negative durations — here are 3"), instead of dumping
  35+ dirty rows. One glance → informed yes/no.
- **Why it sparks:** It reframes cleaning from a chore into a *decision*. The agent
  did the boring detection; the human only spends attention on the judgment call.
- **Trust gap:** Low for *detection* (it's read-only and verifiable), higher for the
  *proposed fix* — Maya needs to see the sample before trusting "exclude negatives".
- **Takeover point:** "Show all 35" and per-issue **Skip**. The user can veto any
  single fix without aborting the rest.
- **Existing-product comparison:** OpenRefine / Trifacta already do faceted cleaning,
  but they assume a data person. Here the **agent triages and the panel only asks for
  ratification** — augmentation for a non-technical user, not a new IDE to learn.
- **One-line insight:** *Detection wants to be autonomous; mutation wants a signature.
  The seam between them is the whole UX.*

## ② Key Driver  — *route-C orchestration + rule alert*

- **Most spark moment:** Watching single-dimension cuts **lie** — platform=android
  −41%, user_type=new −35% — and then the cross-tab snap the truth into focus:
  `android × new` −61%, everything else flat. The "▸ Show the evidence" panel makes
  that contrast visible.
- **Why it sparks:** It's a genuine analytical insight a busy human would likely get
  *wrong* (blame all of Android). The agent scanning 55 combinations in one breath is
  a real capability jump, not a faster button.
- **Trust gap:** This is the sharpest gap in the demo. A 92% confidence number is
  *not* directly actionable — Maya shouldn't reorg Android onboarding on a heuristic.
  She needs the evidence table. The card is designed so she can't miss it.
- **Takeover point:** The evidence disclosure (which combinations, the cross-tab, the
  reproduce-it SQL). A skeptic can re-run the exact query.
- **Existing-product comparison:** Amplitude/Mixpanel have "root cause" / anomaly
  features, but they're driven by a power user clicking through breakdowns. Here Maya
  asks in English and the agent *chooses* the breakdowns. Replaces the analyst's first
  hour; augments their judgment.
- **One-line insight:** *Confidence without evidence is just a vibe; the evidence
  disclosure is what converts a probabilistic answer into a trustworthy one.*

> **Honesty note:** the brief wanted "no single dimension shows anything." In the data,
> region & returning *are* flat, but platform & new-users show partial dips. That's
> actually a *better* demo: single cuts mislead rather than hide, and the lesson —
> "cross your dimensions" — is more realistic.

## ③ Storytelling  — *B / C bench + scheduled digest*

- **Most spark moment:** Version **B** deciding, on its own, that `sql_export` tripling
  deserved the *headline* — opening on the good news instead of burying it under the
  scary WAU number, which the fixed template (C) would always do.
- **Why it sparks:** It's editorial judgment, not formatting. B made a call about
  *what matters most to this reader this week*. That's the thing templates can't do.
- **Trust gap:** Inverted here. **C is more trustworthy** (predictable, comparable
  week to week, audit-friendly); **B is more useful but riskier** (could over-reach,
  could bury something by choosing a wrong hook). The demo lets you *feel* the trade.
- **Takeover point:** Picking which version ships. For a recurring digest you'd pin C;
  for a one-off exec read you'd want B's instincts.
- **Existing-product comparison:** Notion AI / Tableau Pulse generate summaries, but
  default to fixed templates. B's free-structure mode is the differentiator — and the
  thing that needs the most guardrails.
- **One-line insight:** *Predictability and judgment trade against each other; the
  product decision is which one each surface needs, not "which is better".*

## ④ Alert  — *autonomous by nature*

- **Most spark moment:** The "assume a week passed" time-jump → the agent **comes to
  you first**: "⚠️ EMEA error rate broke 5%, concentrated 2h after deploy v2026.06.03.
  Want me to dig in?" The assistant→colleague flip is palpable.
- **Why it sparks:** Initiative. Every other stage is reactive; this one the agent
  *interrupts you*, which is exactly what a good colleague does — and exactly what a
  bad notification system gets wrong.
- **Trust gap:** It's about *etiquette*, not accuracy. The finding is solid; the open
  question is **was this worth interrupting Maya for?** Cry wolf once and the channel
  is dead.
- **Takeover point:** "Snooze · adjust threshold" — the human tunes the agent's
  interrupt budget. The threshold *is* the UX.
- **Existing-product comparison:** Datadog/PagerDuty alert on thresholds already, but
  they spray noise; the differentiator is the agent **pre-investigating** (it already
  localised the cause to the deploy window) so the interruption arrives *with* its
  homework done.
- **One-line insight:** *Autonomy's hard problem isn't detection, it's the right to
  interrupt — the threshold is a social contract, not a number.*

## ⑤ Orchestration (CLAUDE.md)  — *the dispatch layer*

- **Most spark moment:** The same five capabilities run as a **pipeline** (clean →
  drive → story → alert) or fire **independently** off one English question, routed by
  intent — without Maya knowing a "skill" exists.
- **Why it sparks:** The plumbing is invisible. Maya gets a colleague, not a toolbar.
- **Trust gap:** Routing errors are silent — if intent is misread, Maya may not notice
  the wrong skill fired. Surfacing "here's what I'm about to do" mitigates it.
- **Takeover point:** Intent confirmation on ambiguous asks ("did you mean exports as
  CSV or sql_export?" — the dictionary trap made literal).
- **Existing-product comparison:** This is the layer no current BI tool has — a
  natural-language dispatcher over composable analysis skills. It's the demo's actual
  thesis.
- **One-line insight:** *The orchestration layer's job is to stay invisible; you feel
  it only when it routes wrong.*

---

## Cross-cutting observations (the three seams)

**Hand-off seam (交接缝).** The cleanest hand-offs are where the agent does the
*search* and the human does the *judgment*: cleaning (detect → approve), key-driver
(scan → interpret). The demo is weakest where it tries to hand the human a *conclusion*
(a bare confidence %) with no seam to grab — which is why every probabilistic card
carries an evidence disclosure.

**Absent-state trust (缺席态信任).** The autonomous modes (alert, digest) act when Maya
*isn't watching*. Trust there is bought entirely up front: a track record of not crying
wolf, and arriving with homework done. The threshold/etiquette design matters more than
the model's accuracy.

**Read-only vs write gate (只读 vs 写入把关).** The clarifying line across all five
stages. Read-only (detect, query, scan, draft, notice) → safe to do autonomously.
Write / act (mutate data, ship a report, page someone, reorg priorities) → gated on a
human yes. Every stage in this demo is designed to fall cleanly on one side or the
other, and to *say which side it's on*.

### Determinism map (what fits a classic UI vs needs a new paradigm)
| Stage | Deterministic? | UX implication |
|---|---|---|
| Cleaning detection | Mostly yes | Could be a classic rules UI; agent adds the framing |
| Key-driver scan | Mechanically yes, *interpretation* no | Needs the evidence/confidence paradigm |
| Storytelling C | Deterministic | Template — classic UI is fine |
| Storytelling B | Probabilistic | New paradigm — needs guardrails + human pick |
| Alert detection | Deterministic threshold | Classic; the *interrupt decision* is the new part |

### Spark candidates to carry forward
1. **The cross-tab reveal** (key-driver): single cuts lie, the crossing tells truth —
   most defensible "wow", and the most honest about needing evidence.
2. **The B-version opening on good news** (storytelling): editorial judgment a template
   structurally cannot produce.
