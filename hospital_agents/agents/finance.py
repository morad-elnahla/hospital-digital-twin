from __future__ import annotations

from ..config import Settings
from ..contracts import Alert, AlertCode, Proposal, SharedInputs, make_id
from ..messages import Msg
from .base import Agent, AgentReport


class FinanceAgent(Agent):
    """Advisory only. Emits an internal alert when baseline revenue-at-risk crosses an explicit
    business threshold. It carries no resource effects, so it can never trade safety for money;
    money enters the ranking only as the lowest priority tier, via simulator impact."""
    name = "finance"

    async def propose(self, inputs: SharedInputs, settings: Settings) -> AgentReport:
        threshold = settings.revenue_alert_threshold_egp
        base = inputs.simulation.metrics.get("revenue_at_risk_egp") if inputs.simulation else None
        if threshold is None or base is None:
            return AgentReport(self.name, notes=(Msg("fin.abstain"),))
        if base <= threshold:
            return AgentReport(self.name)
        actions = (Alert(AlertCode.REVENUE_AT_RISK, Msg("fin.alert", base=base, threshold=threshold)),)
        return AgentReport(self.name, (Proposal(
            make_id(self.name, actions), self.name, Msg("title.finance"), actions,
            (Msg("fin.rationale", run=inputs.simulation.run_id, base=base), Msg("fin.threshold", threshold=threshold)),
            (f"simulation:{inputs.simulation.run_id}",)),))
