# Reviewing & approving null handling — 7 proposals

*How should Maya (non-technical, can't write SQL) review and ratify what the data-prep
agent does with missing values?*

Null handling is the sharpest version of this demo's core seam. Unlike de-duping or
whitespace-trimming, **there is no correct default** — drop, fill, and flag-and-keep all
produce different answers from the same data, and the choice is a *domain* judgment the
agent cannot make alone. Today `tools/profiler.py` already diagnoses the mechanism
(`_missingness_diagnosis`) and picks a fix; what's missing is the surface where Maya
*reviews* that pick.

## The worked example these proposals use

`data/sample_customers.csv` — 1,215 rows:

```
monthly_spend: 62 missing (5.1%)
  → 100% of the missing rows are plan='free'   (free is 62% of all rows)
  → 65% of the missing rows are churned=1      (churn baseline 53%)
```

Every null is a free-plan customer. So:

| Strategy | What it silently asserts | Damage |
|---|---|---|
| Drop the rows | "free-plan churners aren't part of the population" | removes a segment that churns at 64.5% vs 52.8% overall |
| Fill with median ($21.17) | "free users pay $21/mo" | invents $1,313/mo of revenue that doesn't exist |
| Fill with 0 | "free means zero spend" | probably right — but it's a **business fact**, not a stats fact |
| Flag & keep | "we don't know; carry the uncertainty forward" | safe, but pushes the decision downstream |

The agent can rank these. It cannot know whether free-plan spend is *genuinely zero* or
*merely unrecorded*. That single unknown is what the review surface exists to resolve.

---

## Proposal 1 — Per-column null triage cards (extend the existing approval panel)

The current `components.py cleaning` panel grouped issues **by type**. Do the same for
nulls, one card per affected column, sorted by how much the choice moves the answer.

```
┌ Missing values · approval required ───────────────────────────┐
│ monthly_spend — 62 missing (5.1%)              [high impact]  │
│ Every one of them is a free-plan customer.                    │
│ Proposed: keep the rows, add monthly_spend__missing           │
│ Impact: 0 rows removed · 1 column added                       │
│ [ Approve ]  [ Choose a different fix ▾ ]  [ Show the 62 ]    │
│ ▸ Show the evidence  (crosstab, the rule that fired, the SQL) │
└───────────────────────────────────────────────────────────────┘
```

- **Trust gap:** low — it's the pattern Maya already learned in stage ①.
- **Takeover point:** the `Choose a different fix` dropdown, and per-column Skip.
- **Determinism:** the detection is deterministic; only the *recommendation* is a heuristic,
  and it's visually separated from the counts.
- **Cost:** it asks Maya to approve a *method* (`flag-and-keep`), which is vocabulary she
  doesn't own. Proposal 2 fixes exactly that.

**Ship this as the floor.** It's the smallest change and it's consistent with the rest of
the product. Everything below is a better ceiling.

---

## Proposal 2 — Approve the *consequence*, not the method ⭐

Maya shouldn't have to have an opinion about imputation. She should have an opinion about
**the number**. So compute the metric she actually asked for under each candidate strategy
and let her pick the answer she's willing to defend.

```
You asked: "what's our average revenue per customer?"
Depending on how I handle the 62 missing monthly_spend values:

   Drop those rows        →  ARPU $42.29    ⚠ also drops them from every other
                                              number in this report
   Fill with median $21   →  ARPU $41.21    ⚠ invents $1,313/mo of revenue
   Fill with 0            →  ARPU $40.13    ✓ if "free" really means zero spend
   Flag & keep (my rec.)  →  ARPU $42.29    ✓ same as drop for this metric, but
                                              the 62 customers stay in the data
                                              — reported as "of those we bill"

$2.16 between the highest and lowest — about 5%. Worth your 20 seconds.

[ Go with flag & keep ]   [ Use fill-with-0 ]   [ Show me the 62 ]
```

Note the honest asymmetry: had she asked for **churn** instead, the same four strategies
give 52.2% / 52.8% / 52.8% / 52.8% — a 0.6pt spread. Same nulls, same data, and the choice
barely matters. Proposal 5 is what turns that observation into a rule.

- **Trust gap:** the lowest of any proposal — Maya reviews in the only currency she's
  fluent in (the metric), and the agent's recommendation becomes checkable rather than
  authoritative.
- **Takeover point:** the moment the numbers disagree. Disagreement *is* the interface.
- **Determinism:** each row is deterministic and reproducible; only the ⭐ recommendation
  is probabilistic. That separation is what makes it auditable.
- **Cost:** N× the compute (run the metric once per strategy). On FlowDash-sized data,
  free.
- **Why it's the strongest:** it converts an unanswerable question ("is flag-and-keep
  right?") into an answerable one ("do you believe free users spend $0?"), *and* it
  reveals when the whole debate is moot.

---

## Proposal 3 — Ask the business question, not the statistics question

Nulls are usually a business fact wearing a statistics costume. Have the agent lead with
the domain question and translate the answer into the fix itself.

```
Agent: 62 customers have no monthly_spend — and all 62 are on the free plan.
       Before I pick a treatment: does free-plan spend get recorded as $0,
       or is it just not tracked for free users?

       ○ Free users genuinely spend $0    → I'll fill 0. Revenue metrics stay honest.
       ○ It's tracked but missing here    → I'll flag & keep. I won't guess a value.
       ○ Not sure                         → I'll flag & keep, and note the ambiguity
                                             in every report that touches spend.
```

- **Trust gap:** eliminated at the source — Maya isn't ratifying the agent's judgment, she's
  supplying the one fact it lacks. It's the honest division of labour.
- **Takeover point:** the question itself. "Not sure" is a first-class answer that maps to
  the conservative fix, so ignorance never silently becomes a bad assumption.
- **Determinism:** fully deterministic once answered — the answer *is* the rule.
- **Cost:** interrupts. Only viable for the handful of columns where the mechanism looks
  structured; use Proposal 5 to decide which those are.

---

## Proposal 4 — The why-gate: no fix is offered until the mechanism is shown

Invert the order. The panel's first screen is the **diagnosis**, with no Approve button on
it at all. The treatment options only appear after Maya has seen why the values are absent.

```
Screen 1  ─ Why these values are missing ────────────────
   ████████████████████████████████ free   62 of 62 (100%)
   ·                                pro     0
   ·                                team    0
   Free plan is 62% of all customers, but 100% of the missing.
   This is NOT random. These 62 churn at 64.5% vs 52.8% overall —
   dropping them quietly removes your most at-risk segment.
                                             [ Got it — show me the options → ]

Screen 2  ─ Options (unlocked)
   ...
```

- **Trust gap:** deliberately *raises* friction where the analysis is fragile. That's the
  point — the failure mode with nulls is a confident wrong answer accepted in one click.
- **Takeover point:** the diagnosis screen, before a fix has been framed. Maya can say
  "that's not right, free users do get billed" while the framing is still open.
- **Determinism:** the crosstab is deterministic; the `structured/diffuse/too_few` label is
  a heuristic and should be shown as such (`profiler.py` already thresholds at
  share ≥ 70%, ≥ 25pt above baseline, n ≥ 20 — those numbers belong on screen).
- **Cost:** two screens for every column. Reserve it for `pattern: structured` and let
  diffuse cases go straight to Proposal 1's single card.

---

## Proposal 5 — Sensitivity gate: only interrupt when the choice changes the answer

The alert stage taught us that *the threshold is the etiquette of autonomy*. Apply the same
rule to nulls. The agent runs the downstream metric under every candidate strategy; if they
land within tolerance, it decides on its own and logs it. If they diverge, it escalates.

```
  You asked for churn rate.
  spread across all 4 strategies = 0.6pt  (52.2% … 52.8%)
  → under tolerance. I decided. One-line footnote on the answer:
    "1 null decision made automatically — no strategy moves this
     number by more than 0.6pt. [review]"

  You asked for ARPU.
  spread across all 4 strategies = $2.16 (~5%)
  → over tolerance. Full approval card (Proposal 2), because now it matters.
```

Same column, same nulls — the *question* decides whether Maya's attention is owed.

- **Trust gap:** honest about where trust is even *needed*. Approving 11 identical-outcome
  decisions to reach the one that matters is how approval fatigue kills a gate.
- **Takeover point:** the tolerance itself is user-tunable — same knob as the alert
  threshold, same social contract.
- **Determinism:** the gate is a deterministic rule over probabilistic inputs. Clean fit for
  a classic settings UI.
- **Cost:** requires knowing the downstream metric at prep time. Works when prep is driven
  by a question ("why did WAU drop?"), not when it's a standalone pipeline run.

---

## Proposal 6 — Standing policy, ratified once (approve the rule, not the run)

Per-run approval doesn't scale to a weekly digest that runs while Maya is asleep. Give her a
short policy sheet to ratify once; the agent then applies it silently and only interrupts on
cases the policy doesn't cover.

```
My default null policy — approve once, applies every run:
  1. Structured missingness (concentrated in one segment)  → flag & keep, never drop
  2. Diffuse and < 5% of rows                              → fill (median / mode)
  3. Diffuse and ≥ 5%                                      → flag & keep
  4. > 40% of a column missing                             → drop the column, tell you
  5. Anything outside these                                → ask you

  [ Approve policy ]  [ Edit a rule ]     Every run links the decisions it made.
```

- **Trust gap:** shifts from per-decision to *institutional* — Maya trusts the policy, and
  the policy's track record.
- **Takeover point:** rule 5 is the escape hatch, and the per-run decision log is the audit
  trail. Any run should be re-openable and re-runnable under an amended policy.
- **Determinism:** fully deterministic and diffable — the policy is a config file, and a
  change to it is a reviewable event.
- **Cost:** silent application is exactly the failure mode the demo's iron rules warn about.
  Only safe when paired with a visible, clickable decision log on every output.

---

## Proposal 7 — Provisional apply with one-click revert (approve *after* the fact)

Don't block the answer. Apply the recommended default immediately, keep Maya's flow intact,
and attach a persistent, reversible chip to every artifact the decision touched.

```
   Churn rate: 24.1%
   ⓘ 3 null-handling decisions applied  ·  [ review & change ]

   → clicking re-opens the panel; changing anything recomputes
     the number and every chart derived from it, in place.
```

- **Trust gap:** trades the *gate* for *reversibility* — defensible only because null
  handling is non-destructive by construction (`profiler.apply_fixes` already returns a
  cleaned copy and never mutates the source).
- **Takeover point:** the chip, permanently. The takeover is always available rather than
  offered once and then gone.
- **Determinism:** demands a deterministic, replayable prep step — the decision must be a
  stored value the recompute can be parameterised on, not a thing the model re-decides.
- **Cost:** a number Maya has already screenshotted and pasted into Slack can change
  underneath her. Cap it: provisional only until the result leaves the session (exported,
  scheduled, or shared), then freeze and require explicit approval.

---

## Comparison across the four seams

| # | Proposal | Approves what | Trust gap | Interrupt cost | Fits classic UI? |
|---|---|---|---|---|---|
| 1 | Triage cards | a method | low | medium | yes |
| 2 | **Consequence preview** ⭐ | **a number** | **lowest** | medium | partly — needs the compare view |
| 3 | Business question | a domain fact | none (she supplies it) | high | yes |
| 4 | Why-gate | a diagnosis | deliberately raised | high | yes |
| 5 | Sensitivity gate | a tolerance | low | **lowest** | yes |
| 6 | Standing policy | a rule | institutional | lowest (amortised) | yes |
| 7 | Provisional + revert | nothing up front | deferred | none | needs replayable prep |

## Recommendation

They compose into one flow rather than competing:

> **5 decides whether to ask** → **4 shows why before offering a fix** → **2 asks in the
> currency of the answer** → **3 escalates to a plain-English business question when the
> mechanism is structured** → **6 remembers the outcome as a rule** → **7 keeps it
> reversible afterwards.**

If only one gets prototyped, build **Proposal 2**. It's the one that stops requiring Maya to
have an opinion about imputation, and it makes the agent's recommendation *checkable* instead
of authoritative — the same move the key-driver evidence disclosure made for confidence
scores.

## One-line insight

*Every other cleaning fix has a right answer the user is merely ratifying. Null handling
doesn't — so the review surface can't ask "do you approve my fix?", it has to ask
"which answer are you willing to defend?"*

---

### Notes for implementation

- `profiler.py` already produces the raw material: `_missingness_diagnosis()` returns
  `structured / diffuse / too_few` with the concentration numbers, and each issue carries a
  `fix`, `fix_label`, and plain-language `impact`. Proposals 1, 4, and 6 are presentation
  layers over data that exists today.
- Proposals 2 and 5 need one new capability: **apply a set of candidate fixes and re-run the
  downstream metric for each.** `apply_fixes(df, issues)` is already non-destructive, so the
  loop is cheap to add.
- Proposal 7 needs the prep decisions stored as a replayable parameter set rather than a
  one-shot model choice.
- FlowDash's SQL path (`data_dictionary.md` clean recipe) should honour whatever the
  profiler path settles on, or the two surfaces will teach Maya contradictory habits.
