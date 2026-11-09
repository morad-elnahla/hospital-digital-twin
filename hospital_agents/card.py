from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from .agents import AgentReport, Finding
from .arbitration import Rejection
from .config import Settings
from .contracts import (Action, Alert, ImpactEstimate, PoolAdjustment, Proposal, Reschedule,
                        SharedInputs, ceil_exact, to_jsonable)
from .messages import Msg
from .ports import Explanation, Passage


@dataclass(frozen=True)
class ExecutiveCard:
    decision_id: str
    critical_bottleneck: str | None
    expected_demand_change_pct: float | None
    waiting_minutes_saved: float | None
    revenue_at_risk_before_egp: float | None
    revenue_at_risk_after_egp: float | None
    recommended_actions: tuple[str, ...]
    rejected_count: int
    confidence: float | None
    assumptions: tuple[str, ...]
    unverified: tuple[str, ...]
    degraded_agents: tuple[str, ...]
    unmet: Mapping[str, int]            # pool -> deficit still open after the accepted actions
    approval_required_from: str = "Operations Manager"
    rollback_prepared: bool = False
    # Impact accounting. `unmet` counts ONLY capacity that accepted actions really add (confirmed).
    # Demand relief that rests on an assumption (e.g. postponed procedures) is reported apart,
    # with its basis, and never subtracted from `unmet`.
    capacity_added: Mapping[str, int] = field(default_factory=dict)       # pool -> beds/people added (confirmed arithmetic)
    assumed_relief: Mapping[str, float] = field(default_factory=dict)     # pool -> demand relief, ASSUMED, not simulated
    unmet_if_assumed: Mapping[str, int] = field(default_factory=dict)     # pool -> deficit IF the assumed relief holds
    warnings: tuple[str, ...] = ()                                        # pre-existing conditions worth knowing about
    summary: str | None = None                                            # executive wording, set by the caller


@dataclass(frozen=True)
class Decision:
    id: str
    created_at: datetime
    versions: Mapping[str, str]
    accepted: tuple[Proposal, ...]
    rejected: tuple[Rejection, ...]
    reports: tuple[AgentReport, ...]
    joint_impact: ImpactEstimate | None
    rollback_actions: tuple[Action, ...]
    card: ExecutiveCard
    explanation: Explanation
    policy_passages: tuple[Passage, ...] = ()

    def to_dict(self) -> dict:
        return to_jsonable(self)


def describe(a: Action) -> str:
    if isinstance(a, PoolAdjustment):
        return Msg("act.pool", pool=a.pool, delta=a.delta)
    if isinstance(a, Reschedule):
        return Msg("act.move", booking=a.booking_id,
                   src=f"{a.from_slot.resource_id}@{a.from_slot.start:%Y-%m-%d %H:%M}",
                   dst=f"{a.to_slot.resource_id}@{a.to_slot.start:%Y-%m-%d %H:%M}")
    return Msg("act.alert", detail=a.detail)


def baseline_ratio_warnings(inputs: SharedInputs) -> list[str]:
    """Show baseline comparisons against clearly unapproved template ratios."""
    out = []
    for unit, limit in (("ICU", 2), ("WARD", 3)):
        beds, nurses = inputs.twin.pools.get(f"{unit}:beds"), inputs.twin.pools.get(f"{unit}:nurses")
        if beds and nurses and (nurses.total <= 0 or beds.total / nurses.total > limit + 1e-9):
            observed = round(beds.total / nurses.total, 1) if nurses.total else "∞"
            out.append(Msg("warn.baseline_ratio", unit=unit, beds=beds.total, nurses=nurses.total,
                           observed_ratio=observed, limit=limit))
    return out


def build_card(decision_id: str, inputs: SharedInputs, settings: Settings,
               reports: Sequence[AgentReport], accepted: Sequence[Proposal],
               rejected: Sequence[Rejection], joint: ImpactEstimate | None) -> ExecutiveCard:
    findings: list[Finding] = [f for r in reports for f in r.findings]
    worst = max(findings, key=lambda f: (f.deficit / max(f.total, 1), f.pool.endswith(":beds"), f.pool), default=None)
    demand_pct = None
    if worst and worst.current > 0:
        demand_pct = round((worst.projected / worst.current - 1) * 100, 1)

    base = inputs.simulation.metrics.get("revenue_at_risk_egp") if inputs.simulation else None
    after = None if base is None or joint is None else base - joint.revenue_protected_egp

    verified = sum(1 for p in accepted if p.impact is not None)
    fc = inputs.forecast.confidence
    confidence = None
    if accepted and fc is not None and verified:
        confidence = round(fc * verified / len(accepted), 2)

    has_forecast_bound = any(p.hi is not None for points in inputs.forecast.series.values() for p in points)
    forecast_stat = settings.forecast_stat if has_forecast_bound else Msg("forecast.point_no_interval")
    assumptions = [Msg("as.forecast", model=inputs.forecast.model_version, stat=forecast_stat),
                   Msg("as.twin", version=inputs.twin.version)]
    assumptions += [Msg("as.target", kind=k, value=v) for k, v in sorted(settings.target_utilization.items())]
    if any(p.agent == "or" for p in accepted):
        assumptions.append(Msg("as.beds_per_procedure", beds=settings.beds_per_procedure))
    if inputs.twin.calendar_end is not None and any(isinstance(a, Reschedule) for p in accepted for a in p.actions):
        assumptions.append(Msg("as.calendar", until=f"{inputs.twin.calendar_end - timedelta(days=1):%Y-%m-%d}"))
    units = {a.pool.split(":", 1)[0] for p in accepted for a in p.actions if isinstance(a, PoolAdjustment)}
    assumptions += sorted((Msg("as.policy", key=k, value=v.value, source=v.source)
                           for k, v in inputs.policies.values.items() if k.rsplit(":", 1)[-1] in units), key=str)

    unverified = []
    if len(accepted) and verified < len(accepted):
        unverified.append(Msg("unv.no_impact", n=len(accepted) - verified))
    if joint is None and accepted:
        unverified.append(Msg("unv.no_joint"))
    if fc is None:
        unverified.append(Msg("unv.no_conf"))

    covered: dict[str, int] = {}
    for p in accepted:
        for a in p.actions:
            if isinstance(a, PoolAdjustment) and a.delta > 0:
                covered[a.pool] = covered.get(a.pool, 0) + a.delta
    unmet = {f.pool: f.deficit - covered.get(f.pool, 0) for f in findings if f.deficit > covered.get(f.pool, 0)}

    relief: dict[str, float] = {}
    for p in accepted:
        for e in p.effects:
            relief[e.pool] = relief.get(e.pool, 0.0) + e.beds
    unmet_if_assumed: dict[str, int] = {}
    for pool, beds in sorted(relief.items()):
        if pool in unmet and beds > 0:
            target = settings.target_utilization.get(pool.split(":", 1)[1], 1.0)
            unmet_if_assumed[pool] = max(0, ceil_exact(unmet[pool] - beds / target))
            unverified.append(Msg("unv.relief", pool=pool, relief=beds, unmet=unmet[pool], unmet_assumed=unmet_if_assumed[pool]))

    return ExecutiveCard(
        decision_id=decision_id,
        critical_bottleneck=worst.pool if worst else None,
        expected_demand_change_pct=demand_pct,
        waiting_minutes_saved=joint.waiting_minutes_saved if joint else None,
        revenue_at_risk_before_egp=base, revenue_at_risk_after_egp=after,
        recommended_actions=tuple(Msg("act.line", agent=p.agent, actions=[describe(a) for a in p.actions]) for p in accepted),
        rejected_count=len(rejected), confidence=confidence,
        assumptions=tuple(assumptions), unverified=tuple(unverified),
        degraded_agents=tuple(r.agent for r in reports if r.error), unmet=unmet,
        rollback_prepared=bool(accepted), capacity_added=covered,
        assumed_relief={k: v for k, v in relief.items() if v}, unmet_if_assumed=unmet_if_assumed,
        warnings=tuple(baseline_ratio_warnings(inputs)))
