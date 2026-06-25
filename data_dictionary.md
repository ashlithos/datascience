# FlowDash — Data Dictionary

> **Why this file exists.** It is the single source of truth for text-to-SQL. When a
> non-technical user (our PM, **Maya**) asks a question in plain English, the agent
> translates it to SQL using *these* definitions. The accuracy of the whole demo
> rests on the agent reading this file before writing queries — especially the
> **⚠️ semantic traps** below, where two fields sound alike but mean different things.

FlowDash is the usage-telemetry database for an internal BI / dashboard product.
Single SQLite file: `data/flowdash.db`. Three tables: `sessions`, `feature_events`,
`deployments`. Data spans **8 weeks**, Mon 2026-04-27 → Sun 2026-06-21. "Today" in
the demo is **2026-06-25** (all 8 weeks complete).

---

## Table: `sessions`
One row per app session. **This table contains known data-quality issues — see
"Data quality" at the bottom. Clean before trusting aggregates.**

| Column | Type | Meaning | Notes |
|---|---|---|---|
| `session_id` | TEXT | Unique id for a session. | **Not unique in practice** — a few sessions were double-logged (duplicate rows). De-dupe on this. |
| `user_id` | TEXT | The user who owned the session. | A user has many sessions. For "active users" count **DISTINCT user_id**, never row count. |
| `started_at` | TEXT (ISO datetime) | When the session began, e.g. `2026-06-03T14:37:00`. | Local-naive timestamps. |
| `week` | INTEGER | Convenience week index **1–8** (1 = week of 2026-04-27). | Pre-computed from `started_at`. Use it for weekly trends; it always agrees with the date. |
| `region` | TEXT | User's region: `NA`, `EMEA`, `APAC`, `LATAM`. | **⚠️ DIRTY** — EMEA is spelled inconsistently: `EMEA`, `emea`, `E.M.E.A`, `" EMEA "`. Normalise before grouping (see recipe below). |
| `platform` | TEXT | Client platform: `android`, `ios`, `web`. | Clean. |
| `user_type` | TEXT | `new` (first 30 days) vs `returning`. | Clean. **⚠️ Not the same as `plan` — see trap #2.** |
| `plan` | TEXT | Billing plan: `free` vs `pro`. | **⚠️ Independent of `user_type`.** A `new` user can be `pro`; a `returning` user can be `free`. |
| `duration_sec` | INTEGER | **Total wall-clock** length of the session, in seconds (open → close). | **⚠️ DIRTY** — some values are negative (instrumentation bug). Filter `duration_sec > 0`. **⚠️ Not the same as `active_sec` — see trap #1.** |
| `active_sec` | INTEGER | **Engaged** time only — seconds the app was in the foreground and the user was actually interacting. Always ≤ `duration_sec`. | Use this for "time spent" / engagement. Use `duration_sec` only for "how long was the session open". |
| `had_error` | INTEGER | `1` if the session hit at least one error, else `0`. | **Error rate = SUM(had_error) / COUNT(\*)** over the relevant rows. |
| `app_version` | TEXT | The deployment that was live when the session started, e.g. `v2026.06.03`. | Joins to `deployments.deploy_id`. |

## Table: `feature_events`
One row each time a feature is used within a session. A session can touch several
features (and the same feature more than once).

| Column | Type | Meaning |
|---|---|---|
| `event_id` | INTEGER | Auto-increment primary key. |
| `session_id` | TEXT | Session the event belongs to (joins to `sessions.session_id`). |
| `feature` | TEXT | One of: `dashboard_view`, `apply_filter`, `share_link`, `export_csv`, `configure_alert`, `sql_export`. |
| `used_at` | TEXT (ISO datetime) | When the feature was used. |

> **Feature naming trap #3:** `export_csv` and `sql_export` are **different features**.
> `export_csv` = download the current view as a CSV. `sql_export` = run a raw SQL
> query and export its result set (a power-user feature). When Maya says "exports",
> ask which one — they trend very differently.

## Table: `deployments`
One row per release. Releases ship Wednesdays ~14:00.

| Column | Type | Meaning |
|---|---|---|
| `deploy_id` | TEXT | Version string, e.g. `v2026.06.03`. Joins to `sessions.app_version`. |
| `deployed_at` | TEXT (ISO datetime) | Release timestamp. |
| `notes` | TEXT | Release notes (mostly empty; the week-6 release has a note). |

---

## ⚠️ Semantic traps (read before writing SQL)

1. **`duration_sec` vs `active_sec`.** Both are "time", but `duration_sec` is the
   session's open→close wall-clock (and is sometimes negative/dirty), while
   `active_sec` is real engaged time. "How long did people spend / engagement" →
   `active_sec`. "How long were sessions open" → `duration_sec` (with `> 0` filter).
2. **`user_type` vs `plan`.** `new`/`returning` is tenure; `free`/`pro` is billing.
   They are independent. Never assume new = free.
3. **`export_csv` vs `sql_export`.** Two distinct features (see above).
4. **"Active users" = DISTINCT `user_id`,** not number of session rows. Always.

## Canonical recipes (copy these)

**Normalise region (fixes the EMEA spelling mess):**
```sql
CASE WHEN REPLACE(UPPER(TRIM(region)), '.', '') = 'EMEA' THEN 'EMEA'
     ELSE TRIM(region) END AS region_clean
```

**Weekly active users (WAU), clean:**
```sql
SELECT week, COUNT(DISTINCT user_id) AS wau
FROM sessions
WHERE duration_sec > 0          -- drop the negative-duration junk rows
GROUP BY week ORDER BY week;
```

**Error rate by region for a given week:**
```sql
SELECT
  CASE WHEN REPLACE(UPPER(TRIM(region)),'.','')='EMEA' THEN 'EMEA' ELSE TRIM(region) END AS region_clean,
  ROUND(100.0 * SUM(had_error) / COUNT(*), 2) AS error_rate_pct
FROM sessions WHERE week = 6
GROUP BY region_clean ORDER BY error_rate_pct DESC;
```

## Data quality (the cleaning stage operates on these)
- **Duplicate rows:** ~35 sessions are logged twice (same `session_id`). De-dupe.
- **Negative `duration_sec`:** ~28 rows (clock bug). Filter or null them.
- **Inconsistent `region`:** EMEA appears as `EMEA` / `emea` / `E.M.E.A` / `" EMEA "`.
  Normalise to `EMEA`.
