"""Shared capacity-rebalancing logic used by the ER, Bed, Staff and Resource agents.

For every recipient pool the forecast peak demand is turned into a required total
(demand / target utilisation). The shortfall is covered from (1) headroom up to the pool's
known hard ceiling, then (2) donor units that still cover their *own* forecast demand.
Missing forecast or missing ceiling => no move, never a guess.

Bed moves are also sized to what the unit's nurses can legally staff: when a sourced
patients-per-nurse policy and the unit's nurse pool are both known, a recipient never grows
past floor(nurses x ratio) beds. The arbitration layer still verifies the result, so this is
sizing (propose the largest move that can pass), not a substitute for the gate.
"""
from __future__ import annotations

import math

from ..config import Settings
from ..contracts import PoolAdjustment, Proposal, SharedInputs, ceil_exact, make_id
from ..messages import Msg
from .base import AgentReport, Finding

NURSE_POLICY = "nurse.max_patients_per_nurse"


def _nurse_cap(inputs: SharedInputs, unit: str):
    """(nurses on shift, ratio, max beds they can staff) or None when it cannot be known."""
    policy = inputs.policies.get(f"{NURSE_POLICY}:{unit}")
    nurses = inputs.twin.pools.get(f"{unit}:nurses")
    if policy is None or nurses is None or policy.value <= 0:
        return None
    return nurses.total, policy.value, math.floor(nurses.total * policy.value + 1e-9)


def plan(agent: str, inputs: SharedInputs, settings: Settings, kind: str, *,
         recipients: set[str] | None = None, exclude: set[str] = frozenset(),
         expand: bool = False, donate: bool = True) -> AgentReport:
    pools = {p.unit: p for p in inputs.twin.pools.values() if p.kind == kind}
    target = settings.target_utilization.get(kind, 1.0)
    notes: list[str] = []

    def need(unit: str) -> tuple[float, int] | None:
        demand = inputs.forecast.peak(f"{unit}:{kind}:demand", settings.forecast_stat)
        return None if demand is None else (demand, ceil_exact(demand / target))

    surplus: dict[str, int] = {}
    for u, p in pools.items():
        n = need(u)
        if n is None:
            notes.append(Msg("reb.no_forecast", unit=u, kind=kind))
        else:
            surplus[u] = max(0, p.total - max(p.committed, n[1]))

    proposals, findings = [], []
    for unit in sorted(pools):
        if (recipients is not None and unit not in recipients) or unit in exclude:
            continue
        n = need(unit)
        if n is None:
            continue
        demand, required = n
        pool = pools[unit]
        deficit = required - pool.total
        if deficit <= 0:
            continue
        findings.append(Finding(pool.key, pool.committed, demand, pool.total, deficit))

        # How much of the deficit may this proposal try to cover?
        wanted, nurse_note = deficit, None
        if kind == "beds":
            cap = _nurse_cap(inputs, unit)
            if cap is not None:
                nurses, ratio, max_beds = cap
                allowed = max(0, max_beds - pool.total)
                if allowed >= 1:
                    wanted = min(deficit, allowed)
                    if wanted < deficit:
                        nurse_note = Msg("reb.nurse_cap", unit=unit, nurses=nurses, ratio=ratio, max_beds=max_beds,
                                         covered=wanted, wanted=deficit)
                else:
                    # Nothing can pass: still propose the full move so arbitration rejects it with the exact numbers.
                    notes.append(Msg("reb.nurse_blocked", unit=unit, nurses=nurses, ratio=ratio, max_beds=max_beds, total=pool.total))

        expansion = min(wanted, max(0, pool.hard_max - pool.total)) if expand and pool.hard_max is not None else 0
        remaining, donations = wanted - expansion, []
        if donate and remaining:
            for d in sorted((u for u in surplus if u != unit and surplus[u] > 0),
                            key=lambda u: (-surplus[u], u)):
                take = min(remaining, surplus[d])
                donations.append(PoolAdjustment(pools[d].key, -take))
                surplus[d] -= take
                remaining -= take
                if not remaining:
                    break
        covered = wanted - remaining
        if not covered:
            notes.append(Msg("reb.no_headroom", pool=pool.key, deficit=deficit))
            continue
        unmet = deficit - covered
        actions = [PoolAdjustment(pool.key, covered), *donations]
        rationale = [Msg("reb.need", pool=pool.key, demand=demand, target=target, required=required, total=pool.total),
                     Msg("reb.cover", deficit=deficit, covered=covered, unmet=unmet)]
        if nurse_note is not None:
            rationale.append(nurse_note)
        proposals.append(Proposal(
            id=make_id(agent, actions), agent=agent,
            title=Msg("title.rebalance", agent=agent, pool=pool.key, covered=covered),
            actions=tuple(actions), rationale=tuple(rationale),
            evidence=(f"forecast:{inputs.forecast.model_version}",), unmet=unmet))
    return AgentReport(agent, tuple(proposals), tuple(findings), tuple(notes))
