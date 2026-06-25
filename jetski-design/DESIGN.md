# Jetski — design & visual direction

The visual system behind the **Jetski** data-science-agent demo (chat-driven analytics, the `/shorts` watch-time investigation). Goal of this doc: let another agent reproduce the *look and feel* without the app code. The two reference files next to it are the real source: [`globals.css`](./globals.css) (theme tokens + motion) and [`ui.tsx`](./ui.tsx) (base components).

Stack it was built on: **Next.js (App Router) · React · Tailwind v4 (`@theme inline`, no `tailwind.config.js`) · Recharts**. None of that is required — the direction below is portable.

---

## 1. The feel in one line

A calm, editorial, **Material 3 dark** product — Google-blue primary with a cyan accent — that looks made by a human with taste, not a SaaS template. Restraint over decoration. Every screen has one clear focal point.

**Hard "don't look AI-made" rules (non-negotiable):**
- ❌ No purple→pink or blue→purple gradients. No gradient as primary brand expression. No *animated* gradients.
- ❌ No sparkle / four-pointed-star icons (✨ `Sparkles`, ✦, ✧) anywhere — the single most overused AI cliché.
- ❌ No heavy drop shadows on everything, no neon glow, no bouncy/elastic motion, no pop-in on load.
- ✅ Sentence case for all UI copy (headings, buttons, labels). Uppercase only for intentional micro-labels with letter-spacing.
- ✅ Generous whitespace, strong hierarchy, restrained palette (one strong accent + lots of neutrals).

---

## 2. Color — Material 3 dark, blue/cyan

Defined as CSS variables on `:root` (see `globals.css`). Dark scheme seeded from Google blue; cyan secondary; amber tertiary reserved for *warnings*; red/green semantic.

| Role | Token | Hex | Use |
|---|---|---|---|
| **Primary** | `--primary` | `#a8c7fa` | brand blue — filled buttons, links, active states, chart series 1, accents |
| | `--on-primary` | `#062e6f` | text/icons on primary fills |
| | `--primary-container` | `#0842a0` | tonal primary surfaces |
| | `--on-primary-container` | `#d3e3fd` | text on primary-container |
| **Secondary** | `--secondary` | `#85d2e3` | cyan accent — tonal buttons, chart series 2 |
| | `--secondary-container` | `#004e5a` | tonal cyan surface |
| | `--on-secondary-container` | `#adebff` | |
| **Tertiary (warning)** | `--tertiary` | `#dbc66e` | amber — **warnings/caveats only**, never decoration |
| | `--tertiary-container` | `#544600` | warning chips/banners |
| | `--on-tertiary-container` | `#f9e287` | |
| **Error** | `--error` | `#ffb4ab` | the "bad/down" state, problem cells, negative deltas |
| | `--error-container` | `#93000a` | error fills |
| | `--on-error-container` | `#ffdad6` | |
| **Good** | `--good` | `#8ed8a9` | success/positive delta, "watching/active" pills |
| | `--good-container` | `#1d4a2f` | |
| **Background/Surface** | `--background` / `--surface` | `#111418` | app background (cool near-black, **not** purple-black) |
| | `--on-surface` | `#e2e2e9` | primary text |
| | `--on-surface-variant` | `#c4c6d0` | secondary text |
| | `--surface-container-lowest` | `#0c0e13` | |
| | `--surface-container-low` | `#191c20` | cards, side panels |
| | `--surface-container` | `#1d2024` | raised surfaces |
| | `--surface-container-high` | `#282a2f` | menus, popovers, chips |
| | `--surface-container-highest` | `#33353a` | hover/active layer |
| | `--outline` | `#8e9099` | borders, muted text/icons |
| | `--outline-variant` | `#44474e` | hairline dividers/borders |
| | `--inverse-surface` | `#e2e2e9` | snackbars (light on dark) |
| | `--inverse-on-surface` | `#2e3036` | text on snackbars |

**Data-viz scale** (cool, light tones on dark): `--c1 #a8c7fa` (blue) · `--c2 #85d2e3` (cyan) · `--c3 #8ed8a9` (green) · `--c4 #bfc6dc` (blue-grey) · `--c5 #dbc66e` (amber). Coral `#ff8a65` is used for "erosion/negative" bars. **Color encodes meaning, never sequence** — don't rainbow-cycle.

In Tailwind v4 these are exposed via `@theme inline` as `bg-surface-container-low`, `text-on-surface-variant`, `border-outline-variant`, etc. (1:1 with the token names).

---

## 3. Typography

- **UI font:** Google Sans Flex. **Mono/tabular:** Google Sans Code. (Loaded via `next/font/google`; these are the public Google Fonts releases — the proprietary "Google Sans"/Product Sans is not distributable.)
- Numbers that change use `.tnum` (`font-variant-numeric: tabular-nums`) so they don't jitter.
- **M3 type scale helpers** (see `globals.css`):
  - `.m3-display` 40/1.1/400 · `.m3-headline` 28/1.2/400 · `.m3-title` 20/1.3/500 · `.m3-title-sm` 15/1.35/500
  - `.m3-label` 11px **uppercase, 0.5px tracking, 500** — the small section kickers (e.g. "WEEKLY DATA STORY")
  - `.m3-body` 14.5/1.5/400
- Headlines lean medium (500), not bold. Body stays 400. Two weights, basically.

---

## 4. Shape & spacing

- Radius scale: `4 / 8 / 12 / 16 / 28px`. Cards use **12px** (`rounded-[12px]`), pills/chips fully rounded, the centered composer **22px**, buttons fully rounded (pill).
- Borders are **hairline**: `1px solid var(--outline-variant)` (or `/60` opacity for softer). Avoid thick borders.
- Dividers: same `outline-variant`. Dashed `outline-variant/70` for "placeholder/skeleton/loading" affordances.

---

## 5. Motion — restrained, real easing

Easing curves (never the CSS defaults, never bounce/elastic):
- `cubic-bezier(0.2, 0, 0, 1)` — fade-up (entrance)
- `cubic-bezier(0.16, 1, 0.3, 1)` — rise-in (confident, decisive)
- `cubic-bezier(0.22, 1, 0.36, 1)` — micro-interactions (press/hover)

Patterns (all in `globals.css`):
- **`.fade-up`** — opacity + 6px rise, 0.32s. The default "content appears" motion; stagger with `style={{animationDelay}}` (~60–90ms steps) for choreography.
- **`.rise-in`** — opacity + 14px rise + 4px blur→sharp, 0.7s. For hero/welcome entrances. Not a pop.
- **`.drift-a` / `.drift-b`** — very slow (19s/23s) drift of heavily-blurred, low-opacity blue/cyan glows behind a hero. Atmospheric depth — *not* an animated gradient. Pair with a cursor-following radial spotlight for the "premium" feel.
- **Press feedback** — `active:scale-[0.96–0.99]` + 150ms transition on buttons/chips/cards.
- **`.shimmer`** — the ONLY shimmer allowed, and only for genuine loading skeletons. Cool tint `rgba(200,225,255,0.07)`.
- **`@media (prefers-reduced-motion: reduce)`** disables all entrance animations and near-zeroes transitions. Always include this.

Durations: 100–150ms feedback · 200–300ms state change · 500–800ms entrance. Exit ≈ 75% of enter.

---

## 6. Base components (see `ui.tsx`)

- **Button** — pill, label 13–14px medium, `transition-all 150ms`, `active:scale-[0.97]`. Variants: `primary` (filled `bg-primary text-on-primary`, hover brightness), `tonal` (`bg-secondary-container`), `outline`, `ghost`. **Primary = the one action that moves the flow forward.**
- **Card** — `rounded-[12px] border border-outline-variant/60 bg-surface-container-low`. Flat; no shadow except functional.
- **Pill / badge** — `rounded-[8px] px-2 py-1 text-[12px] medium`, tones: `neutral`, `good`, `bad` (error), `warn` (tertiary), `accent` (primary-container). Used for deltas, statuses, tags.
- **Label** — the `.m3-label` uppercase kicker, `text-on-surface-variant`.

---

## 7. Signature patterns (the parts worth copying)

- **Chat layout:** chat pane + an artifact "canvas" pane. The canvas only **mounts when there's something to show** (a report/result) — until then the chat is full-width and centered (`max-w-2xl`, `mx-auto`). Panes are **drag-resizable** via a 1.5px handle on the divider (`cursor-col-resize`, width persisted to `localStorage`, clamped 320–760px).
- **One avatar per turn:** the agent avatar (a 24px `bg-primary` circle, single letter) renders **only on the first message after a user message** — never stacked on every line. A same-width spacer keeps continuation lines aligned. One header, never two.
- **Reasoning trace:** thinking + tool calls collapse into one compact unit per step. Light styling — a thin left rule, muted mono, *no* boxed outline; scrollable (`max-h-72`). Shows "Thinking…" with a spinner while running, auto-collapses to "Reasoning · N skills" when done (re-expandable). Tool calls render as `skill · sub` + the call + `→ result`, with a spinner→check.
- **AskUserQuestion card** — reserve for *genuine intent forks* (e.g. "how should the alert trigger?"), not routine "what next?". Inline card: question + 2–4 option buttons; the flow-advancing option gets the **primary filled** style, others outline. **No "recommended" badge** — weight communicates the path.
- **Suggestion chips** — for simple navigation ("what next?"). Row of pills above the composer; the flow action is the filled-primary chip.
- **Data story (report):** rich, with **clear masthead + hierarchy** → a kicker label, a big headline, a meta line with a colored delta, a "throughline" summary box, then **findings that pair a chart with a short insight narrative** (insight gets a 2px colored left-border keyed to its tone — red for the drop, etc.), ending in a highlighted recommendation. Charts + insights together; color used intentionally (red = decline/erosion, blue/cyan = neutral series, green = positive).
- **Snackbar** — `bg-inverse-surface text-inverse-on-surface`, bottom-center, fades up, optional action button; auto-dismiss ~5s.
- **Empty/placeholder fidelity:** when prototyping loosely, represent charts as simple suggestive SVG shapes and body copy as skeleton bars (`bg-on-surface/10`) — but keep the *interaction* (prompt/conversation) high fidelity.

---

## 8. Copy voice

Plain, confident, sentence case. Name the finding, then the "so what." No hype, no "Powered by AI ✨" anything. Demo/synthetic data is always labelled as such (never present fabricated numbers as real).

---

*Want the running app to look at? It's a private repo (`ashlithos/jetski`) — ask the owner for access, or just work from this doc + the two reference files.*
