"""Hard constraints. Each check sees a *set* of proposals and returns violations naming the
proposals involved. Unverifiable means violated: a missing policy or missing pool never passes.

`joint=True` constraints only make sense for the final set (a bed increase and the nurse
increase that supports it are individually non-compliant but jointly fine); they are checked
after the greedy pass, with the lowest-ranked implicated proposals dropped until clean.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol, Sequence

from .contracts import (PoolAdjustment, PolicyBundle, Proposal, Reschedule, SlotKey,
                        TwinSnapshot, Urgency)
from .messages import Msg


@dataclass(frozen=True)
class Violation:
    constraint: str
    proposals: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class CheckContext:
    snapshot: TwinSnapshot
    policies: PolicyBundle


class Constraint(Protocol):
    name: str
    joint: bool

    def check(self, ctx: CheckContext, proposals: Sequence[Proposal]) -> list[Violation]: ...


def _pool_deltas(proposals: Sequence[Proposal]) -> tuple[dict[str, int], dict[str, set[str]]]:
    delta: dict[str, int] = defaultdict(int)
    touched: dict[str, set[str]] = defaultdict(set)
    for p in proposals:
        for a in p.actions:
            if isinstance(a, PoolAdjustment):
                delta[a.pool] += a.delta
                touched[a.pool].add(p.id)
    return delta, touched


class PoolBounds:
    name, joint = "pool_bounds", False

    def check(self, ctx, proposals):
        out = []
        delta, touched = _pool_deltas(proposals)
        for key, d in delta.items():
            ids = tuple(sorted(touched[key]))
            pool = ctx.snapshot.pools.get(key)
            if pool is None:
                out.append(Violation(self.name, ids, Msg("pool.unknown", pool=key)))
                continue
            new = pool.total + d
            if new < max(0, pool.committed):
                out.append(Violation(self.name, ids,
                                     Msg("pool.below_committed", pool=key, new=new, committed=pool.committed)))
            if pool.hard_max is not None and new > pool.hard_max:
                out.append(Violation(self.name, ids, Msg("pool.over_max", pool=key, new=new, hard_max=pool.hard_max)))
        # Growth beyond a known ceiling is never implied: a pool without hard_max may only
        # grow inside a proposal that is capacity-neutral for that kind.
        for p in proposals:
            by_kind: dict[str, int] = defaultdict(int)
            for a in p.actions:
                if isinstance(a, PoolAdjustment):
                    by_kind[a.pool.split(":", 1)[1]] += a.delta
            for a in p.actions:
                if isinstance(a, PoolAdjustment) and a.delta > 0:
                    pool = ctx.snapshot.pools.get(a.pool)
                    if pool and pool.hard_max is None and by_kind[a.pool.split(":", 1)[1]] > 0:
                        out.append(Violation(self.name, (p.id,), Msg("pool.no_max", pool=a.pool)))
        return out


class SlotAvailability:
    name, joint = "slot_availability", False

    def check(self, ctx, proposals):
        out, claims, moved = [], defaultdict(set), defaultdict(set)
        snap = ctx.snapshot
        for p in proposals:
            for a in p.actions:
                if not isinstance(a, Reschedule):
                    continue
                b, dst = snap.booking(a.booking_id), snap.slot(a.to_slot)

                def bad(why, p=p):
                    out.append(Violation(self.name, (p.id,), Msg("slot.booking", booking=a.booking_id, why=why)))

                if b is None:
                    bad(Msg("slot.unknown_booking"))
                elif b.urgency is not Urgency.NON_URGENT:
                    bad(Msg("slot.not_movable"))
                elif b.slot != a.from_slot:
                    bad(Msg("slot.from_mismatch"))
                elif snap.calendar_end is not None and a.to_slot.start >= snap.calendar_end:
                    bad(Msg("slot.beyond_calendar", start=a.to_slot.start.isoformat(),
                            until=(snap.calendar_end - timedelta(days=1)).strftime("%Y-%m-%d")))
                elif dst is None:
                    bad(Msg("slot.missing"))
                elif a.to_slot.domain != a.from_slot.domain or a.to_slot.start <= snap.as_of:
                    bad(Msg("slot.domain_or_past"))
                elif b.provider_id and b.provider_id not in dst.provider_ids:
                    bad(Msg("slot.provider", provider=b.provider_id))
                else:
                    claims[a.to_slot].add(p.id)
                    moved[a.booking_id].add(p.id)
        for key, ids in claims.items():
            n = sum(snap.booking(a.booking_id).duration for p in proposals if p.id in ids
                    for a in p.actions if isinstance(a, Reschedule) and a.to_slot == key)
            if n > snap.slot(key).free:
                out.append(Violation(self.name, tuple(sorted(ids)),
                                     Msg("slot.overclaimed", resource=key.resource_id, start=key.start.isoformat(),
                                         claimed=n, free=snap.slot(key).free)))
        for bid, ids in moved.items():
            if len(ids) > 1:
                out.append(Violation(self.name, tuple(sorted(ids)), Msg("slot.moved_twice", booking=bid)))
        return out


class NurseRatio:
    """Joint check of staffed beds per nurse against a *sourced* policy; no policy, no change.

    A change passes only when the unit ends compliant with *verified* nursing capacity: at least one
    nurse on shift and beds / nurses <= the policy ratio. Zero nurses is never compliant for a unit
    that keeps beds, however the arithmetic is arranged (0 nurses makes every ratio infinite, and
    "infinite is not worse than infinite" must never read as "safe").

    The one exception keeps a donor from being blamed for a condition it did not create: a unit that
    still ends above the ratio passes only if the change strictly helps it on both axes (no bed added,
    no nurse removed, and at least one of them moved the right way). A recipient that ends above the
    ratio, or any unit that gets a bed it cannot staff, is rejected with the numbers needed to see why.
    """
    name, joint = "nurse_ratio", True
    POLICY = "nurse.max_patients_per_nurse"

    def check(self, ctx, proposals):
        out = []
        delta, touched = _pool_deltas(proposals)
        units = {k.split(":", 1)[0] for k in delta if k.split(":", 1)[1] in ("beds", "nurses")}
        for unit in sorted(units):
            ids = tuple(sorted(touched.get(f"{unit}:beds", set()) | touched.get(f"{unit}:nurses", set())))
            policy = ctx.policies.get(f"{self.POLICY}:{unit}")
            beds, nurses = ctx.snapshot.pools.get(f"{unit}:beds"), ctx.snapshot.pools.get(f"{unit}:nurses")
            limit = policy.value if policy is not None else None
            if limit is None or not math.isfinite(limit) or limit <= 0 or beds is None or nurses is None:
                out.append(Violation(self.name, ids, Msg("nurse.unverifiable", unit=unit)))
                continue
            b0, n0 = beds.total, nurses.total
            b, n = b0 + delta.get(beds.key, 0), n0 + delta.get(nurses.key, 0)
            if n >= 0 and (b <= 0 or (n > 0 and b / n <= limit + 1e-9)):
                continue                                           # compliant after the change, with nurses actually on shift
            strictly_helps = b <= b0 and n >= n0 and (b < b0 or n > n0)
            if n >= 0 and strictly_helps:
                continue                                           # still above the ratio, but better on both axes: pre-existing, reported elsewhere
            out.append(Violation(self.name, ids, Msg(
                "nurse.exceeds", unit=unit, beds=b, nurses=n, limit=limit, required=math.ceil(b / limit - 1e-9),
                supported=math.floor(max(n, 0) * limit + 1e-9), source=policy.source.split(" | ", 1)[0])))
        return out


def default_constraints() -> list[Constraint]:
    return [PoolBounds(), SlotAvailability(), NurseRatio()]
