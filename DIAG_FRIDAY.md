# DIAG_FRIDAY — OR-01 closed-day rescheduling diagnosis

**Scope:** ICU ×1.3; replay `as_of=2026-10-15T10:00`; reported result: four elective surgeries rescheduled to **Friday, 2026-10-23**. Source: provided `hospital_digital_twin - Copy.zip`, active project at its top level (not `.work` scratch copies). **Static, read-only analysis** of source and CSV records; **no execution of the app, agents, scenarios or tests**. The reported four moves were not rerun or independently reproduced.

## Verdict

**App bug caused by a data-contract mismatch; not a valid routine-OR booking.** `TwinData.calendar()` manufactures an active 600-minute slot for every active OR on every date through `calendar_end`. It never reads the per-date `or_availability.csv` schedule. But the latter explicitly says that **OR-01 on 2026-10-23 is `CLOSED`, `capacity_minutes=0`, `rostered_surgeons=0`, `rostered_anesthetists=0`, `planned_bookings=0`**. The agent then treats the manufactured slot as eligible. The existing CSV convention is internally clear about the future closure; changing surgery rows to camouflage it is not justified.

## 1. How `TwinData.calendar()` builds slots and what counts as schedule data

Source: `hospital_agents/twin_data.py` (line numbers refer to the supplied active copy).

- **Lines 125–133:** `calendar_end` is **midnight after the latest date** found among **all** `surgeries.planned_start`, `appointments.scheduled_start` and `staff_shifts.shift_start`. These maxima are all **2026-11-10**, so the exclusive end is **2026-11-11T00:00:00**. This establishes only the **global date boundary**, not proof that any particular OR is staffed/open that day.
- **Lines 135–137:** `days = [as_of.date() + timedelta(days=i) ...]` creates **every calendar day**, inclusive from **2026-10-15 through 2026-11-10**; no weekday or per-day schedule-data filter.
- **Lines 140–149:** non-past, non-`CANCELLED`/`RESCHEDULED` surgeries contribute planned durations to each OR-day's `booked` minutes. **Line 148–149:** surgery bookings have `provider_id=None`.
- **Lines 163–170:** for **each day** and **each** `operating_rooms.csv` record where `is_active == "True"`, create one OR slot at **00:00**, ending at next midnight, with `capacity = int(float(daily_capacity_hours) * 60)`; `booked` is accumulated from surgery durations.

Exact governing excerpt:

```python
# hospital_agents/twin_data.py:125-137
@property
def calendar_end(self) -> datetime:
    planned_dates = (
        [_dt(r["planned_start"]).date() for r in self.t["surgeries"]]
        + [_dt(r["scheduled_start"]).date() for r in self.t["appointments"]]
        + [_dt(r["shift_start"]).date() for r in self.t["staff_shifts"]]
    )
    return datetime.combine(max(planned_dates) + timedelta(days=1), time.min)

def calendar(self, as_of: datetime) -> tuple[tuple[Slot, ...], tuple[Booking, ...]]:
    end_day = (self.calendar_end - timedelta(days=1)).date()
    days = [as_of.date() + timedelta(days=i) for i in range((end_day - as_of.date()).days + 1)]

# hospital_agents/twin_data.py:163-170
slots = []
for day in days:
    midnight = datetime.combine(day, time.min)
    for r in self.t["operating_rooms"]:
        if r["is_active"] == "True":
            key = SlotKey("OR", r["or_id"], midnight)
            slots.append(Slot(key, midnight + timedelta(days=1),
                              int(float(r["daily_capacity_hours"]) * 60), booked[key]))
```

**Direct answer to “this day has schedule data”:** no such predicate exists in `calendar()`. A day is included solely because it lies within the global date range; an OR gets a slot solely because its **room-level `is_active`** is true. Neither `data/or_availability.csv` (per-day `ROSTERED`/`CLOSED` and 480/0 minute capacities) nor `data/calendar_days.csv` (weekend flag) is consulted in `calendar()`.

In `data/operating_rooms.csv`, OR-01 has `is_active=True`, `daily_capacity_hours=10.0` → **600 minutes assumed** every day. On **2026-10-23**, `data/or_availability.csv` instead has `availability_status=CLOSED`, `capacity_minutes=0`, no roster, no booking and no operative window. On rostered future workdays, `or_availability.csv` gives **480 minutes**, not 600; the capacity disagreement extends beyond just weekends.

## 2. Day-of-week counts, 2026-10-15 through 2026-11-10, inclusive

Counts were derived by reading **`data/surgeries.csv`** and counting records by their `planned_start` date; **“planned surgery rows” means CSV rows with a planned date**, irrespective of urgency or final status (`COMPLETED`, `DELAYED`, `SCHEDULED`, `CANCELLED`, etc.). The primary surgery column is **OR-01 only**. An all-OR column is included to remove ambiguity. These are **not** counts of new proposals or post-reschedule appointments.

| Weekday (Sun → Sat) | Dates in range | OR-01 slots produced by `calendar()` | OR-01 planned surgery rows | All-OR planned surgery rows |
|:--|--:|--:|--:|--:|
| Sun | 4 | 4 | 11 | 47 |
| Mon | 4 | 4 | 10 | 44 |
| Tue | 4 | 4 | 11 | 55 |
| Wed | 3 | 3 | 6 | 27 |
| Thu | 4 | 4 | 10 | 50 |
| **Fri** | **4** | **4** | **2** | **2** |
| **Sat** | **4** | **4** | **2** | **2** |
| **Total** | **27** | **27** | **52** | **227** |

**Important interpretation:** OR-01's two Friday surgery rows are both `EMERGENCY` on **2026-10-16**. Its two Saturday rows are one `URGENT` and one `EMERGENCY` on **2026-10-17**. Thus there are **zero OR-01 elective surgeries on Fri/Sat** in this range. In particular there are **zero planned surgeries in OR-01 on 2026-10-23** (also zero across all ORs that day). Historical urgent/emergency operations on an earlier weekend do **not** establish routine future Friday/Saturday availability.

`data/or_availability.csv` contains OR-01 per-day rows for **2026-10-21 through 2026-11-10**: **15 `ROSTERED` workdays** and **6 `CLOSED` Fri/Sat days**. There are **no rows in that file for 2026-10-15 through 2026-10-20**; the adapter nevertheless fabricates slots on those six earlier days too. On **2026-10-23, 2026-10-24, 2026-10-30, 2026-10-31, 2026-11-06 and 2026-11-07**, the OR-01 source rows are `CLOSED` with **0 available minutes**, while the current calendar produces a **600-minute slot on each date**.

## 3. How the OR agent picks a target and which safety checks exist

- **`hospital_agents/agents/scheduling.py:61–81`:** `ORAgent.propose()` calculates an ICU bed deficit from forecast demand, selects future, nonurgent ICU-dependent OR bookings whose OR-day falls between `as_of` and the forecast `horizon`, and caps proposals at `ceil_exact(deficit / beds_per_procedure)`.
- **`scheduling.py:82–86`:** it selects all OR slots and invokes `_target(..., after=horizon, resource_id=b.slot.resource_id, calendar_end=cal_end)` for each candidate; the same OR is required.
- **`scheduling.py:20–35`:** `_target()` sorts slots chronologically and returns the **first** one (i) after the horizon and not the original slot, (ii) before exclusive `calendar_end`, (iii) in the same OR, (iv) with enough `s.free` minus previously reserved minutes, and (v) containing the provider **only if `booking.provider_id` is not null**. Surgery bookings currently have no provider ID, so the provider check is **not enforced** for them.
- **`scheduling.py:91–100`:** accepted candidates' target minutes are tracked in `used` before subsequent candidates are evaluated. The agent can therefore fit several surgeries into the same fictitious Friday slot if total modeled durations fit.
- **`hospital_agents/constraints.py:85–128`:** the downstream `SlotAvailability` gate validates booking identity, nonurgency, time range, target slot existence, optional provider, and aggregate free minutes. **It does not consult `or_availability.csv`, Friday/Saturday, `availability_status`, or staffing.** Because the fake Friday slot exists, this safety check does not independently catch its closure.

Exact target selector (`scheduling.py:20–35`):

```python
def _target(slots: list[Slot], used: dict[SlotKey, int], booking: Booking, *,
            after, resource_id: str | None = None, calendar_end=None) -> Slot | None:
    """Earliest free slot after `after` where the booking's provider is verified available."""
    for s in sorted(slots, key=lambda s: s.key.start):
        if s.key.start <= after or s.key == booking.slot:
            continue
        if calendar_end is not None and s.key.start >= calendar_end:
            continue
        if resource_id is not None and s.key.resource_id != resource_id:
            continue
        if s.free - used.get(s.key, 0) < booking.duration:
            continue
        if booking.provider_id and booking.provider_id not in s.provider_ids:
            continue
        return s
    return None
```

**There is no closed-day/weekday restriction in either target selection or the slot constraint.** The slot is described as “verified,” but availability verification here only means “present in the synthetic calendar with enough computed free minutes,” not “operationally rostered.”

## 4. Smallest recommended fix — text diff only; **NOT APPLIED**

**Fix in the app's data adapter**, not by rewriting surgeries or removing emergency-weekend history. Respect real OR availability where the pack provides it. For days from the first dated OR schedule onward, **fail closed** on absent, non-`ROSTERED`, or zero-capacity OR records. Before the first OR availability date (the replay's earlier historical dates), preserve legacy behavior because the CSV lacks schedule rows there. This also uses the 480-minute operational capacity instead of 600 on rostered days. The day-level slot remains a simplification; block-by-block fitting, turnover and actual surgeon/anesthetist assignment are separate issues.

```diff
--- a/hospital_agents/twin_data.py
+++ b/hospital_agents/twin_data.py
@@ def calendar(self, as_of: datetime) -> tuple[tuple[Slot, ...], tuple[Booking, ...]]:
-        slots = []
+        or_schedule = {
+            (row["date"], row["or_id"]): row
+            for row in self.t.get("or_availability", [])
+        }
+        first_scheduled_day = min((date for date, _ in or_schedule), default=None)
+        slots = []
         for day in days:
             midnight = datetime.combine(day, time.min)
             for r in self.t["operating_rooms"]:
                 if r["is_active"] == "True":
+                    capacity = int(float(r["daily_capacity_hours"]) * 60)
+                    if first_scheduled_day is not None and day.isoformat() >= first_scheduled_day:
+                        schedule = or_schedule.get((day.isoformat(), r["or_id"]))
+                        if schedule is None or schedule["availability_status"] != "ROSTERED":
+                            continue
+                        capacity = int(schedule["capacity_minutes"])
+                        if capacity <= 0:
+                            continue
                     key = SlotKey("OR", r["or_id"], midnight)
                     slots.append(Slot(key, midnight + timedelta(days=1),
-                                      int(float(r["daily_capacity_hours"]) * 60), booked[key]))
+                                      capacity, booked[key]))
```

**Expected effect, not test-verified:** OR-01 would have **no target slot on Friday 2026-10-23**. The OR agent would search later eligible `ROSTERED` days, subject to actual modeled free minutes, or report no target. Other ORs' closed days would also be excluded if identified in the schedule. No data changes required.

**Caveat:** This is the smallest targeted fix for the observed source data. If a real hospital allows emergency procedures on a nominally closed routine-OR day, that requires a **separate explicitly authorized emergency-capacity model**, not pretending elective procedures can use a general-purpose 600-minute Friday slot. The present OR agent only moves `NON_URGENT` cases.

## Change and verification record

- Read existing `.py`, `.md` and relevant `.csv` bytes only. **Did not print, open, copy or include any `.env` content.**
- Did not run `app.py`, scenario runners, agents, tests, generators, migrations, or any new test harness.
- Did not edit source code or CSV data, delete original files or modify the supplied archive.
- Only this diagnostic report and a **separate cleaned delivery ZIP** were created. Cleaning is by **excluding temporary, duplicate, cache, VCS, historical backup, and runtime-state files from the *new ZIP***; nothing was deleted from the original archive.
