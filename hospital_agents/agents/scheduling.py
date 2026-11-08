"""Agents that move bookings: OR (relieve downstream bed pressure) and Appointment
(rebalance overbooked clinic slots). Both touch NON_URGENT bookings only.

A target slot is accepted only when it is *known*: it exists in the twin's calendar, lies before
the calendar's end (an empty future is unknown, not free), has enough free minutes after the
agent's own earlier claims, and has the booking's provider verified available. Operating-room
moves stay in the booking's own room, so specialty and equipment never change.
"""
from __future__ import annotations

from datetime import timedelta

from ..config import Settings
from ..contracts import (Booking, DemandRelief, Proposal, Reschedule, SharedInputs, Slot, SlotKey,
                         Urgency, ceil_exact, make_id)
from ..messages import Msg
from .base import Agent, AgentReport, Finding


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


def _proposal(agent: str, b: Booking, to: SlotKey, why: tuple, evidence: tuple[str, ...],
              effects: tuple[DemandRelief, ...] = ()) -> Proposal:
    actions = (Reschedule(b.id, b.slot, to),)
    return Proposal(make_id(agent, actions), agent, Msg("title.move", agent=agent, booking=b.id),
                    actions, why, evidence, effects=effects)


def _day(d) -> str:
    return f"{d:%Y-%m-%d}"


def known_until(calendar_end) -> str:
    """Last day the calendar covers (calendar_end is exclusive)."""
    return _day(calendar_end - timedelta(days=1)) if calendar_end else "n/a"


class ORAgent(Agent):
    """When the relief pool (default ICU beds) is forecast short, postpone non-urgent
    procedures that need a bed there into verified-free slots of the same room beyond the
    forecast horizon. The bed relief is an ASSUMPTION (see Settings.beds_per_procedure); it is
    attached to the proposal as a labelled demand relief, never as verified impact."""
    name = "or"

    async def propose(self, inputs: SharedInputs, settings: Settings) -> AgentReport:
        key = settings.or_relief_pool
        pool = inputs.twin.pools.get(key)
        unit, kind = key.split(":", 1)
        demand = inputs.forecast.peak(f"{key}:demand", settings.forecast_stat)
        horizon = inputs.forecast.horizon_end
        if pool is None or demand is None or horizon is None:
            return AgentReport(self.name, notes=(Msg("or.pool_missing", key=key),))
        required = ceil_exact(demand / settings.target_utilization.get(kind, 1.0))
        deficit = required - pool.total
        if deficit <= 0:
            return AgentReport(self.name)
        finding = Finding(key, pool.committed, demand, pool.total, deficit)

        as_of, cal_end = inputs.twin.as_of, inputs.twin.calendar_end
        until = known_until(cal_end)
        candidates = sorted((b for b in inputs.twin.bookings
                             if b.slot.domain == "OR" and b.urgency is Urgency.NON_URGENT
                             and b.needs_icu_bed and as_of < b.slot.start <= horizon),
                            key=lambda b: (b.slot.start, b.id))
        limit = ceil_exact(deficit / settings.beds_per_procedure)
        free = [s for s in inputs.twin.slots if s.key.domain == "OR"]
        used: dict[SlotKey, int] = {}
        proposals, notes = [], []
        for b in candidates[:limit]:
            slot = _target(free, used, b, after=horizon, resource_id=b.slot.resource_id, calendar_end=cal_end)
            if slot is None:
                notes.append(Msg("or.no_slot", booking=b.id, room=b.slot.resource_id, until=until) if cal_end
                             else Msg("or.no_slot_unknown", booking=b.id, room=b.slot.resource_id))
                continue
            before = used.get(slot.key, 0)
            used[slot.key] = before + b.duration
            why = [Msg("or.deficit", key=key, demand=demand, total=pool.total, deficit=deficit),
                   Msg("or.candidate", booking=b.id),
                   Msg("or.assumed", beds=settings.beds_per_procedure),
                   Msg("or.verified_slot", room=slot.key.resource_id, day=_day(slot.key.start),
                       free=slot.free - before, capacity=slot.capacity, until=until)]
            proposals.append(_proposal(self.name, b, slot.key, tuple(why),
                                       (f"forecast:{inputs.forecast.model_version}", f"twin:{inputs.twin.version}"),
                                       (DemandRelief(key, settings.beds_per_procedure, "assumed"),)))
        return AgentReport(self.name, tuple(proposals), (finding,), tuple(notes))


class AppointmentAgent(Agent):
    """Moves non-urgent bookings out of overbooked clinic slots into the nearest later free
    slot of the same clinic where their provider is available."""
    name = "appointment"

    async def propose(self, inputs: SharedInputs, settings: Settings) -> AgentReport:
        slots = [s for s in inputs.twin.slots if s.key.domain == "CLINIC"]
        cal_end = inputs.twin.calendar_end
        used: dict[SlotKey, int] = {}
        proposals, notes = [], []
        for s in sorted(slots, key=lambda s: s.key.start):
            excess = s.booked - s.capacity
            if excess <= 0:
                continue
            movable = sorted((b for b in inputs.twin.bookings
                              if b.slot == s.key and b.urgency is Urgency.NON_URGENT),
                             key=lambda b: b.id)
            to_move, freed = [], 0
            for b in movable:
                if freed >= excess:
                    break
                to_move.append(b)
                freed += b.duration
            start = s.key.start.isoformat()
            if freed < excess:
                notes.append(Msg("appt.partial", resource=s.key.resource_id, start=start, excess=excess, freed=freed))
            for b in to_move:
                to = _target(slots, used, b, after=s.key.start, resource_id=s.key.resource_id, calendar_end=cal_end)
                if to is None:
                    notes.append(Msg("appt.no_slot", booking=b.id, resource=s.key.resource_id))
                    continue
                used[to.key] = used.get(to.key, 0) + b.duration
                proposals.append(_proposal(
                    self.name, b, to.key,
                    (Msg("appt.over", resource=s.key.resource_id, start=start, booked=s.booked, capacity=s.capacity),),
                    (f"twin:{inputs.twin.version}",)))
        return AgentReport(self.name, tuple(proposals), notes=tuple(notes))
