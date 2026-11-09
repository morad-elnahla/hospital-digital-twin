"""Adapter: the synthetic CSV data pack  ->  the agents' SharedInputs, plus the read-only
queries the dashboard needs. This is the only module that knows the CSV schema.

Replay model: pick any moment `as_of` inside the available history. The twin is rebuilt as it
stood then (beds occupied, staff on shift, future bookings) and the forecast is computed only
from data *before* that moment, so the days after it can be used to check the forecast.

Documented simplifications (all synthetic-data conveniences, none clinical):
  * Forecasts use only prior daily_metrics and nurse coverage; the trend-seasonal model is
    selected only when rolling-origin MAE and WAPE both beat weekday mean. Intervals are unavailable.
  * Staff pools = non-absent shifts covering `as_of`, by role (NURSE, DOCTOR). Staff demand has
    no forecast in the pack, so the Staff agent abstains.
  * OR slot = one OR-day, capacity from the verified or_availability roster when present;
    CLOSED/unrostered days never become destinations. Older days are source-only
    calendar evidence when a surgery is actually recorded on that OR-day.
    Clinic slot = one cardiology
    clinic hour, capacity = rostered clinic doctors x 60 minutes. Durations are minutes.
  * Elective surgeries and FOLLOW_UP appointments are the only movable bookings; the pack has
    no urgency field for appointments, so NEW_CONSULT is treated as not movable.
  * For bookings after `as_of`, the final outcome status is unknown at that time and ignored,
    except CANCELLED/RESCHEDULED which are excluded.
  * Planned ICU need comes from surgeries.icu_bed_required / post_op_destination. Historical ICU stays
    are retained for retrospective comparison and never used as replay decision inputs.
  * Future bookings use planned rows only. Later final status changes have no effective timestamp in
    this data pack, so CANCELLED/RESCHEDULED outcomes are not allowed to rewrite an earlier replay.
  * The booking calendar is only KNOWN up to the last day of the pack. Days after it are not
    modelled at all (no slots), and `TwinSnapshot.calendar_end` says so: an empty future is
    unknown, never "free". Agents and constraints refuse to move a booking into it.
"""
from __future__ import annotations

import csv
import dataclasses
import re
import sqlite3
import statistics
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from .contracts import (Action, Booking, Forecast, ForecastPoint, PoolAdjustment, Pool,
                        Reschedule, SharedInputs, SimulationBaseline, Slot, SlotKey, TwinSnapshot, Urgency)
from .policies import PolicyDoc

BED_UNITS = ("ER", "ICU", "WARD")
FORECAST_DAYS = 7
CLINIC_HOURS = range(8, 17)
STAFF_ROLES = {"NURSE": "nurses", "DOCTOR": "doctors"}


@dataclass(frozen=True)
class Scenario:
    """Versioned deterministic what-if input; first two fields keep the v0 API compatible."""
    unit: str = "ICU"
    demand_multiplier: float = 1.0
    as_of: str | None = None
    horizon: int = FORECAST_DAYS
    interventions: tuple[dict, ...] = ()
    data_version: str = "csv-snapshot-v1"
    policy_version: str = ""
    seed: int = 0
    created_by: str = ""


def _dt(s: str) -> datetime:
    # Python 3.9 truncates excess fractional-second precision inconsistently;
    # the synthetic pack may contain nanosecond-looking timestamps.
    s = re.sub(r"(\.\d{6})\d+(?=Z|[+-]\d{2}:?\d{2}|$)", r"\1", s)
    return datetime.fromisoformat(s)


def _planned_icu_need(surgery: dict) -> bool | None:
    """Return an ICU need only from consistent, explicit planned fields."""
    raw = surgery.get("icu_bed_required", "").strip().lower()
    flag = True if raw in {"true", "1", "yes"} else False if raw in {"false", "0", "no"} else None
    dest = surgery.get("post_op_destination", "").strip().upper()
    destination_need = True if dest == "ICU" else False if dest in {"HOME", "WARD"} else None
    if flag is not None and destination_need is not None and flag != destination_need:
        return None
    return flag if flag is not None else destination_need


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class _SqliteTable(Sequence[dict]):
    """Lazy sequence preserving TwinData's legacy list-of-string-dicts interface."""

    def __init__(self, path: Path, table: str, types: dict[str, str]) -> None:
        self.path, self.table, self.types = path, table, types
        self._quoted = '"' + table.replace('"', '""') + '"'

    def _decode(self, row: sqlite3.Row) -> dict:
        out = {}
        for key in row.keys():
            value = row[key]
            if value is None:
                out[key] = ""
            elif self.types.get(key) == "BOOLEAN":
                out[key] = "True" if bool(value) else "False"
            else:
                out[key] = str(value)
        return out

    def __iter__(self) -> Iterator[dict]:
        with closing(sqlite3.connect(str(self.path))) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(f"SELECT * FROM {self._quoted}")
            try:
                for row in cursor:
                    yield self._decode(row)
            finally:
                cursor.close()

    def __len__(self) -> int:
        with closing(sqlite3.connect(str(self.path))) as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {self._quoted}").fetchone()[0]

    def __getitem__(self, index):
        if isinstance(index, slice):
            return list(self)[index]
        if index < 0:
            index += len(self)
        with closing(sqlite3.connect(str(self.path))) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(f"SELECT * FROM {self._quoted} LIMIT 1 OFFSET ?", (index,)).fetchone()
        if row is None:
            raise IndexError(index)
        return self._decode(row)

    def __add__(self, other):
        return list(self) + list(other)


class _SqliteTables(Mapping[str, _SqliteTable]):
    def __init__(self, path: Path) -> None:
        self.path = path
        self._overrides = {}
        with closing(sqlite3.connect(str(path))) as conn:
            self._types = {}
            names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'hdt_metadata'")]
            for table in names:
                self._types[table] = {r[1]: (r[2] or "").upper() for r in conn.execute(f'PRAGMA table_info("{table}")')}
        self._tables = {name: _SqliteTable(path, name, self._types[name]) for name in names}

    def __getitem__(self, key: str) -> _SqliteTable:
        return self._overrides.get(key, self._tables[key])

    def __setitem__(self, key: str, value) -> None:
        if key not in self._tables:
            raise KeyError(key)
        self._overrides[key] = value

    def __iter__(self):
        return iter(self._tables)

    def __len__(self) -> int:
        return len(self._tables)


class TwinData:
    def __init__(self, data_dir: str | Path, prefer_sqlite: bool = True) -> None:
        d = Path(data_dir)
        if d.is_file() and d.suffix in {".sqlite", ".db"}:
            db_path = d
        else:
            db_path = d.parent / "runtime" / "hdt.sqlite"
        if prefer_sqlite and db_path.exists():
            t = _SqliteTables(db_path)
            self.storage_backend = "sqlite"
        else:
            # Kept for callers/tests that construct an isolated TwinData from an unbuilt pack.
            t = {p.stem: _read(p) for p in d.glob("*.csv")}
            self.storage_backend = "csv-fallback"
        self.t = t
        self.dept = {r["department_id"]: r for r in t["departments"]}
        self.dept_by_type = {r["department_type"]: r["department_id"] for r in t["departments"]}
        room_dept = {r["room_id"]: r["department_id"] for r in t["rooms"]}
        self.beds = [(b["bed_id"], self.dept[room_dept[b["room_id"]]]["department_type"])
                     for b in t["beds"] if b["status"] == "AVAILABLE"]
        open_stay_end = datetime(2100, 1, 1)
        self.stays = [(s["bed_id"], _dt(s["start_time"]),
                       _dt(s["end_time"]) if s["end_time"] else open_stay_end)
                      for s in t["bed_stays"]]
        self.historical_icu_visits = {s["visit_id"] for s in t["bed_stays"] if s["bed_id"].startswith("BED-ICU")}
        # Compatibility alias for historical-truth comparisons only; decision logic uses planned surgery fields.
        self.icu_visits = self.historical_icu_visits
        self.staff_role = {s["staff_id"]: (s["department_id"], s["role"]) for s in t["staff"]}
        self.shifts = [(_dt(s["shift_start"]), _dt(s["shift_end"]), s["staff_id"], s["status"])
                       for s in t["staff_shifts"]]
        # A daily OR capacity is not a repeating weekly schedule: the real roster explicitly
        # closes Fridays/Saturdays and may close any other room-day.
        self.or_availability = {(r["date"], r["or_id"]): r for r in t.get("or_availability", [])}
        self.or_roster_start = min((r["date"] for r in t.get("or_availability", [])), default=None)
        self.metrics = defaultdict(dict)                     # date -> dept_id -> row
        for r in t["daily_metrics"]:
            self.metrics[r["metric_date"]][r["department_id"]] = r
        self.finance = defaultdict(dict)
        for r in t["financial_daily"]:
            self.finance[r["metric_date"]][r["department_id"]] = r
        self.first_day, self.last_day = min(self.metrics), max(self.metrics)
        # Three days before the end: leaves 3 days of actuals for the forecast check and a calendar
        # of future bookings. Shift coverage is dataset- and date-dependent.
        self.default_as_of = _dt(self.last_day) - timedelta(days=3) + timedelta(hours=8)
        self.beds_total = defaultdict(int)
        for _, unit in self.beds:
            self.beds_total[unit] += 1

    # ───────────────────────── twin snapshot ─────────────────────────

    def pools(self, as_of: datetime) -> dict[str, Pool]:
        out: dict[str, Pool] = {}
        occupied = defaultdict(int)
        bed_unit = dict(self.beds)
        for bed, start, end in self.stays:
            if start <= as_of < end and bed in bed_unit:
                occupied[bed_unit[bed]] += 1
        for unit in BED_UNITS:
            n = self.beds_total[unit]
            # hard_max stays None: the pack gives no ceiling for converting beds between units, so
            # a unit may only grow inside a capacity-neutral (donor) move.
            out[f"{unit}:beds"] = Pool(f"{unit}:beds", n, occupied[unit])
        on_shift = defaultdict(int)
        for start, end, staff, status in self.shifts:
            if start <= as_of < end and status != "ABSENT":
                dept, role = self.staff_role[staff]
                if role in STAFF_ROLES:
                    on_shift[(self.dept[dept]["department_type"], STAFF_ROLES[role])] += 1
        for unit in {r["department_type"] for r in self.dept.values()}:
            for kind in STAFF_ROLES.values():
                if any(self.staff_role[s][0] == self.dept_by_type[unit] and STAFF_ROLES.get(self.staff_role[s][1]) == kind
                       for s in self.staff_role):
                    out[f"{unit}:{kind}"] = Pool(f"{unit}:{kind}", on_shift[(unit, kind)], 0)
        return out

    @property
    def calendar_end(self) -> datetime:
        """Exclusive end of the known booking calendar: midnight after the last day of the pack."""
        planned_dates = (
            [_dt(r["planned_start"]).date() for r in self.t["surgeries"]]
            + [_dt(r["scheduled_start"]).date() for r in self.t["appointments"]]
            + [_dt(r["shift_start"]).date() for r in self.t["staff_shifts"]]
        )
        return datetime.combine(max(planned_dates) + timedelta(days=1), time.min)

    def calendar(self, as_of: datetime) -> tuple[tuple[Slot, ...], tuple[Booking, ...]]:
        end_day = (self.calendar_end - timedelta(days=1)).date()
        days = [as_of.date() + timedelta(days=i) for i in range((end_day - as_of.date()).days + 1)]
        booked: dict[SlotKey, int] = defaultdict(int)
        bookings: list[Booking] = []
        for r in self.t["surgeries"]:
            start = _dt(r["planned_start"])
            if start <= as_of:
                continue
            key = SlotKey("OR", r["or_id"], datetime.combine(start.date(), time.min))
            dur = int(r["planned_duration_minutes"])
            booked[key] += dur
            bookings.append(Booking(
                r["surgery_id"], key, Urgency.NON_URGENT if r["urgency"] == "ELECTIVE" else Urgency.URGENT,
                None, _planned_icu_need(r), dur, None, r["specialty"] or None))
        clinic = self.dept_by_type.get("CLINIC")
        for r in self.t["appointments"]:
            start = _dt(r["scheduled_start"])
            if r["department_id"] != clinic or start <= as_of:
                continue
            key = SlotKey("CLINIC", clinic, start.replace(minute=0, second=0))
            dur = int(r["duration_minutes"])
            booked[key] += dur
            bookings.append(Booking(
                r["appointment_id"], key,
                Urgency.NON_URGENT if r["appointment_type"] == "FOLLOW_UP" else Urgency.URGENT,
                None, False, dur))
        slots = []
        for day in days:
            midnight = datetime.combine(day, time.min)
            for r in self.t["operating_rooms"]:
                if r["is_active"] == "True":
                    key = SlotKey("OR", r["or_id"], midnight)
                    availability = self.or_availability.get((day.isoformat(), r["or_id"]))
                    if availability is not None:
                        # Fail closed on unrostered or closed days, regardless of generic OR hours.
                        if (availability["availability_status"] != "ROSTERED"
                                or int(availability["rostered_surgeons"]) <= 0
                                or int(availability["rostered_anesthetists"]) <= 0):
                            continue
                        capacity = int(availability["capacity_minutes"])
                        if capacity <= 0:
                            continue
                        # Turnover is known from the verified roster, and must not be lost
                        # when calculating free space for a move.
                        used = max(booked[key], int(availability["booked_minutes_with_turnover"]))
                    else:
                        # Missing entries inside the roster period are UNKNOWN, never free.
                        if self.or_roster_start is not None and day.isoformat() >= self.or_roster_start:
                            continue
                        # Historical/pre-roster OR-days are included ONLY if actual source
                        # booking data establishes the existence of this room-day.
                        if key not in booked:
                            continue
                        capacity = int(float(r["daily_capacity_hours"]) * 60)
                        used = booked[key]
                    slots.append(Slot(key, midnight + timedelta(days=1), capacity, used,
                                      specialty=r["specialty"] or None))
            for h in CLINIC_HOURS:
                if clinic:
                    key = SlotKey("CLINIC", clinic, midnight + timedelta(hours=h))
                    slot_end = key.start + timedelta(hours=1)
                    on_slot = {staff for start, end, staff, status in self.shifts
                               if start <= key.start and end >= slot_end and status != "ABSENT"
                               and self.staff_role.get(staff) == (clinic, "DOCTOR")}
                    slots.append(Slot(key, slot_end, len(on_slot) * 60, booked[key]))
        return tuple(slots), tuple(sorted(bookings, key=lambda b: b.id))

    def snapshot(self, as_of: datetime, version_suffix: str = "") -> TwinSnapshot:
        slots, bookings = self.calendar(as_of)
        return TwinSnapshot(as_of, f"replay@{as_of.isoformat()}{version_suffix}", self.pools(as_of), slots, bookings,
                            self.calendar_end)

    # ───────────────────────── forecast ─────────────────────────

    def occupancy_forecast(self, as_of: datetime, unit: str, days: int = FORECAST_DAYS) -> list[dict]:
        """Occupancy forecast from history strictly before `as_of`; no uncalibrated interval."""
        from .forecasting import build
        points = build(self, as_of).get(f"{unit}:occupancy", {}).get("points", ())
        return list(points[:days])

    def forecast(self, as_of: datetime, scenario: Scenario = Scenario()) -> Forecast:
        from .forecasting import build
        analyzed = build(self, as_of)
        series = {}
        for unit in ("ER", "ICU", "WARD"):
            result = analyzed.get(f"{unit}:occupancy")
            if not result or not result["beats_baseline"]:
                continue
            k = scenario.demand_multiplier if unit == scenario.unit else 1.0
            n = self.beds_total[unit]
            points = tuple(ForecastPoint(_dt(p["date"] + "T08:00:00"), p["predicted"] * n * k)
                           for p in result["points"])
            if points:
                series[f"{unit}:beds:demand"] = points
        for unit in ("ER", "ICU", "WARD"):
            result = analyzed.get(f"{unit}:nurses")
            if not result or not result["beats_baseline"]:
                continue
            points = tuple(ForecastPoint(_dt(p["date"] + "T08:00:00"), p["predicted"])
                           for p in result["points"])
            if points:
                series[f"{unit}:nurses:demand"] = points
        return Forecast("rolling_origin_selected_v1", series, confidence=None)

    def backtest(self, as_of: datetime) -> dict:
        """WAPE/MAPE of the occupancy forecast on the days after `as_of` that exist in the data."""
        out = {}
        for unit in ("ICU", "WARD"):
            rows = [r for r in self.occupancy_forecast(as_of, unit) if r["actual"] is not None]
            tot = sum(r["actual"] for r in rows)
            out[unit] = {
                "days": len(rows),
                "wape": round(sum(abs(r["predicted"] - r["actual"]) for r in rows) / tot, 3) if tot else None,
                "mape": round(statistics.fmean(abs(r["predicted"] - r["actual"]) / r["actual"]
                                               for r in rows if r["actual"]) , 3)
                        if any(r["actual"] for r in rows) else None}
        return out

    # ───────────────────────── shared inputs ─────────────────────────

    def revenue_at_risk_7d(self, as_of: datetime) -> float:
        total = 0.0
        for i in range(1, 8):
            day = (as_of.date() - timedelta(days=i)).isoformat()
            total += sum(float(r["cancelled_procedure_risk_egp"] or 0) for r in self.finance.get(day, {}).values())
        return round(total, 2)

    def inputs(self, as_of: datetime, scenario: Scenario = Scenario(), applied: Sequence[Sequence[Action]] = (),
               policies=None) -> SharedInputs:
        snap = self.snapshot(as_of, f"|sandbox:{len(applied)}")
        for actions in applied:
            snap = apply_actions(snap, actions)
        sim = SimulationBaseline(f"history-7d-before-{as_of.date()}", None,
                                 {"revenue_at_risk_egp": self.revenue_at_risk_7d(as_of)})
        kw = {"policies": policies} if policies is not None else {}
        return SharedInputs(snap, self.forecast(as_of, scenario), sim, **kw)

    def policy_docs(self) -> list[PolicyDoc]:
        """Text-only policies from the pack; never numeric constraints (they are test examples)."""
        return [PolicyDoc(r["document_id"], f"{r['title']} [{r['source_label']}, approved={r['approved']}]",
                          r["content"]) for r in self.t["policy_documents"]]


# ───────────────────────── sandbox overlay ─────────────────────────

def apply_actions(snap: TwinSnapshot, actions: Iterable[Action]) -> TwinSnapshot:
    """Apply approved actions to a snapshot (sandbox execution). Alerts change nothing."""
    pools, slots, bookings = dict(snap.pools), {s.key: s for s in snap.slots}, {b.id: b for b in snap.bookings}
    for a in actions:
        if isinstance(a, PoolAdjustment):
            p = pools[a.pool]
            pools[a.pool] = dataclasses.replace(p, total=p.total + a.delta)
        elif isinstance(a, Reschedule):
            b = bookings[a.booking_id]
            for key, sign in ((a.from_slot, -1), (a.to_slot, +1)):
                slots[key] = dataclasses.replace(slots[key], booked=slots[key].booked + sign * b.duration) \
                    if key in slots else slots.get(key)
            bookings[b.id] = dataclasses.replace(b, slot=a.to_slot)
    return dataclasses.replace(snap, pools=pools, slots=tuple(s for s in slots.values() if s),
                               bookings=tuple(sorted(bookings.values(), key=lambda b: b.id)))
