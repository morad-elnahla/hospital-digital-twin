# API contract used by the UI

Lists every backend call the UI makes and the response fields it **reads** (not everything the backend returns).
There is no runtime schema validation; most reads use optional chaining.

## Transport

- One client: `api(path, body?)` in `src/lib/api.ts`. No body → `GET`; body (even `{}`) → `POST` JSON with `Content-Type: application/json`.
- `useHdt(endpoint)` in `src/lib/app-state.tsx` → `GET /api/<endpoint>?as_of=<ISO hour>`; with `{scoped:false}` no `as_of`.
- `as_of` starts as `2026-10-17T08:00:00`, then `meta.default_as_of`. `lang`/`language` is `ar` or `en`.
- Auth: `Authorization: Bearer <token>` (token from `/api/login`, kept in sessionStorage `hdt_token`).
- Paths:
  - `VITE_HDT_DIRECT=1` (app.py package): browser calls `/api/...` directly.
  - otherwise: browser calls `/api/hdt/...`; `src/routes/api/hdt.$.ts` forwards to `${HDT_API_URL}/api/...` (query string kept, `Authorization` kept).
- Notation: `[]` array element, `{key}` dynamic object key.

## GET endpoints

| Path | Query | Used by |
|---|---|---|
| `/api/meta` | – | app-state, shell replay bar |
| `/api/me` | – | app-state, shell, permission-gated buttons |
| `/api/twin` | `as_of` | `routes/index.tsx`, `twin/layout.ts`, `twin/scene.tsx` |
| `/api/alerts` | `as_of` | alerts, overview, twin page, shell badge |
| `/api/overview` | `as_of` | overview |
| `/api/capacity` | `as_of` | capacity |
| `/api/staff` | `as_of` | staff |
| `/api/or` | `as_of` | or |
| `/api/forecasts` | `as_of` | forecasts |
| `/api/status` | – | system, overview |
| `/api/quality` | – | system, overview |
| `/api/policies` | – | system |
| `/api/decisions` | – | decisions (list) |
| `/api/decisions/<id>` | `lang` (live only) | decisions (detail) |
| `/api/sandbox` | – | decisions |
| `/api/scenario-drafts` | – | simulator draft list |
| `/api/assistant` | – | assistant (history) |
| `/api/knowledge` | `q` | system |

### `/api/meta`
`default_as_of`, `first_day`, `last_day`

### `/api/me`
`username`, `role_label`, `permissions[]` (UI checks `run`, `decide`, `policy`)

### `/api/twin`
```
departments[].id, .type, .name, .name_ar, .nurses, .doctors, .arrivals, .avg_wait_min, .day,
            .beds_total, .occupied,
            .beds[].id, .beds[].room, .beds[].occupied,
            .rooms[].name, .rooms[].booked_min_on_day, .rooms[].capacity_min
```
Occupancy = `occupied / beds_total`. Building geometry is schematic and computed in the UI.

### `/api/alerts`
`needs_attention`, `alerts[].id, .severity (critical|high|medium|info), .source, .title, .title_ar, .detail, .detail_ar, .page`
`page` → link: `agents`/`simulator` → /simulator, `decisions` → /decisions, `staff` → /staff, else /system.

### `/api/overview`
```
as_of, latest_day, period.from, period.to
cards[].key, .delta_pct, .tone, .value, .unit, .label, .spark[]
departments[].name, .name_ar, .arrivals, .occupancy_pct, .avg_wait_min, .overtime_hours, .absences
inpatient.occupied_now, .beds_total, .occupancy_now_pct
occupancy.dates[], .icu_pct[], .ward_pct[], .er_pct[]
bed_use.used, .available, .closed
performance.er_wait_min, .lwbs_pct, .or_delay_pct, .or_cancel_pct
er.dates[], .arrivals[], .wait_avg[], .wait_p90[]
finance.dates[], .revenue_egp[], .risk_egp[]
forecast_occupancy.ICU[].date, .observed, .predicted, .lower, .upper, .actual
pressure[].id, .type, .delta_pct
```

### `/api/capacity`
```
history_period.from, .to, sources
units.{unit}.occupied_now, .beds_total, .occupancy_now_pct, .nurses_on_shift, .beds_occupied_per_nurse,
            .occupancy_history_pct[], .forecast_pct[].date/.predicted/.lower/.upper/.actual,
            .backtest.days/.wape/.mape
units.ER.flow.window.from/.to, .arrivals_by_hour[], .wait_avg_history[], .wait_p90_history[],
             .queue_peak_history[], .left_without_being_seen_pct, .dispositions.{k}, .visits_in_window, .acuity.{k}
```
`units` is an object keyed by unit (default selected `ICU`).

### `/api/staff`
```
on_shift_now[].unit, .kind (nurses|doctors), .count
observed_beds_per_nurse.{unit}
history_period.from, .to
shifts_per_day.dates[], .values[]
absent_shifts_per_day.values[]
overtime_cost_egp.values[]           (summed in UI)
overtime_hours.dates[], .values[]
workload_distribution.buckets[], .staff[]
workload_by_unit[].unit, .mean_pct, .staff, .at_or_above_90_pct
```

### `/api/or`
```
status_counts.{COMPLETED|SCHEDULED|DELAYED|CANCELLED|...}
surgeries_in_window, delay_rate_pct, cancel_rate_pct, cancelled_expected_margin_egp, sources
history_period.from, .to
by_room[].or_id, .name, .specialty, .planned_utilisation_pct
dates[], utilisation_history_pct[]
upcoming.dates[], .load_pct[], .bookings[], .movable_elective[]
```

### `/api/forecasts`
```
series[].key, .title, .unit, .table,
        .history.dates[], .history.values[],
        .forecast[].date/.predicted/.lower/.upper/.actual,
        .backtest.days/.wape/.mape
```
Translated titles for keys `er_arrivals`, `avg_er_wait_minutes`, `icu_occupancy`, `ward_occupancy`, `or_utilization`.

### `/api/status`
`llm.configured`, `llm.provider`, `llm.model`, `features[].name, .note, .available`

### `/api/quality`
`summary.pass/.warn` (`fail` is optional in the current backend), `days`, `period.from/.to`, `tables.{name}`, `checks[].name, .detail, .status, .value`

### `/api/policies`
`nurse_ratio[].unit, .value, .ratio, .approved, .source` (current = `value ?? ratio`), `fingerprint`. ER is an empty unapproved template until a manager enters a value; only a manager can approve it.

### `/api/decisions` (array)
`[].id, .status, .scenario.unit, .scenario.demand_multiplier, .as_of, .accepted (count), .rejected (count), .note, .stale, .stale_reason, .no_action_code, .unmet.{pool}` (fallback `.card.unmet.{pool}`)
`status === "PENDING"` → "awaiting review" section, others → history.

### `/api/decisions/<id>`
`status`, `stale`, `stale_reason` + all **Decision result** fields below.

### `/api/sandbox`
`applied[]` (each item shown as string or JSON). Rollback button enabled when `applied.length > 0`.

### `/api/assistant`
`history[].role`, `history[].text` (or `.content`)

### `/api/knowledge`
`passages[].title, .source, .text`, `pack_policies[].id, .source, .text`, `sources[].id, .title, .status, .version, .country`

## POST endpoints

| Path | Body | Response fields read |
|---|---|---|
| `/api/login` | `{username, password}` | `token` (user then loaded via `/api/me`) |
| `/api/logout` | `{}` | – (errors ignored) |
| `/api/policies` | `{unit: "ER"\|"ICU"\|"WARD", value: string \| null}` or `{unit:"ER", approve:true}` | – |
| `/api/simulate` | `{as_of, unit: "ER"\|"ICU"\|"WARD", multiplier, horizon, seed, interventions[], language}` | see below |
| `/api/run` | same as simulate | `id, status, note, no_action_reason, accepted[], rejected[]` + **Decision result** |
| `/api/assistant` | `{message, as_of, language}` | `answer, evidence[].id, evidence[].label, suggestions[], notes[], mode, fallback, validation_failures[].claim, validation_failures[].reason` |
| `/api/assistant/reset` | `{}` | – |
| `/api/rollback` | `{note}` | `status` (global, not per decision) |
| `/api/decisions/<id>/approve` | `{note}` | `status` |
| `/api/decisions/<id>/reject` | `{reason}` (**not** `note`) | `status` |
| `/api/scenario-drafts` | `{as_of, unit, multiplier, horizon, seed, interventions[], language}` | `id, status, created_at, created_by, scenario` |

Approve is enabled only when `status === "PENDING"`, user has `decide`, and not `stale`. Reject: `PENDING` + `decide`.
Run requires `run`; policy edits require `policy`. Multiplier slider: 1–20, step 0.5, default 12.

### `/api/simulate` response
```
scenario
before.{ER|ICU|WARD}.beds, .peak_demand_beds, .peak_utilisation_pct
after.{ER|ICU|WARD}.beds, .peak_demand_beds, .peak_utilisation_pct, .shortfall_beds,
                    .assumed_relief_beds, .shortfall_if_assumed_beds
bed_change.{ER|ICU|WARD}
capacity_cost_change_egp_per_day, rescheduled_bookings
pack_reference[].id, .name, .results.mean_wait_minutes
cost_note
unavailable[].metric, .reason
decision            → Decision result fields
as_of, scenario.{unit, demand_multiplier, horizon, seed, interventions[]}
scenario_relevant_actions[].agent, .action
not_related_actions[].label, .reason, .action
core.bed_demand.{ER|ICU|WARD}.{status, label, baseline, demand, beds, shortfall, nurse_demand, residual_message, why_nothing_moved, what_would_help[]}
core.before_after_delta.{ER|ICU|WARD}.{baseline_shortfall, scenario_shortfall, delta}
core.notes[], core.rejected[], core.wait_revenue_overtime.{wait|revenue|overtime}.{status, reason}
```

Supported `interventions[].type`: `demand_change` (`unit`, `x`), `er_arrivals_surge` (`x`), `staff_change` (`unit`, `role`, exactly one of `delta` or `absent_pct`), `bed_change` (`unit`, `delta`), `or_closed` (`dates[]`, optional `or_id`), and `reschedule_surgery` (`booking_id`, `target:{domain:"OR",resource_id,start}`). The UI labels the weekday-mean ICU/WARD/nurse/arrival baseline `assumption: unvalidated baseline forecast`; doctor/resource demand abstains when it has no baseline. ER wait/revenue/overtime remain unavailable with backend reasons.

### `/api/scenario-drafts`
GET returns an array. Each row has `id, status, created_at, created_by, scenario`. POST saves a draft only. A reviewer can load and preview it, create a decision through `/api/run`, then approve that decision through `/api/decisions/<id>/approve`; clinicians never receive `decide` permission.

## Decision result (shared)

Used at the root of `/api/decisions/<id>` and `/api/run`, and under `decision` of `/api/simulate`.
```
status, no_action_code, no_action_reason
unmet.{pool}                       (preferred; fallback card.unmet.{pool})
card.unmet_if_assumed.{pool}, card.critical_bottleneck, card.waiting_minutes_saved, card.confidence,
card.summary, card.assumptions[], card.unverified[], card.warnings[]
accepted[].id, .title, .rationale[]
rejected[].proposal.id, .proposal.title, .reasons[]
reports[].agent, .proposals (length only), .findings[].pool, .projected, .total
```
`no_action_code`: `none.reason.no_proposals` | `none.reason.all_rejected` | `none.reason.advisory`.
NO_ACTION title: advisory → advisory label; unmet total > 0 → "Forecast shortfall — no safe action available"; else "No action needed".
Statuses styled: `PENDING`, `APPLIED`, `REJECTED`, `NO_ACTION`, `SUPERSEDED`, `ROLLED_BACK` (others get a neutral style).

## Errors

- Non-2xx: UI reads `error` from the JSON body and shows it.
- `401` (except on `/api/login`): token cleared → sign-in screen once `/api/me` fails.
- `403` / `409`: no special handling; the backend's `error` text is shown in a toast.
- Proxy only: `503 {"error":"backend not configured"}`, `502 {"error":"backend unreachable"}`.

## Live-only behavior

The UI has no recorded-response fallback. Every operational value comes from the connected backend; when it
is unavailable, the UI displays the API error and does not substitute snapshot or fabricated values.
