from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from ..config import Settings
from ..contracts import Proposal, SharedInputs


@dataclass(frozen=True)
class Finding:
    """A detected shortfall; the orchestrator picks the critical bottleneck from these."""
    pool: str
    current: int          # committed today
    projected: float      # forecast peak demand
    total: int
    deficit: int


@dataclass(frozen=True)
class AgentReport:
    agent: str
    proposals: tuple[Proposal, ...] = ()
    findings: tuple[Finding, ...] = ()
    notes: tuple[str, ...] = ()      # abstentions and missing-input explanations
    error: str | None = None
    # Why the agent could not evaluate its domain at all (no demand baseline, no threshold...).
    # Empty means it had what it needs: zero proposals then genuinely means "nothing to do".
    unavailable: tuple[str, ...] = ()
    # error > proposed > unavailable > no_proposal. Derived here so every consumer agrees.
    status: str = field(init=False, default="no_proposal")

    def __post_init__(self) -> None:
        status = ("error" if self.error else "proposed" if self.proposals
                  else "unavailable" if self.unavailable else "no_proposal")
        object.__setattr__(self, "status", status)


class Agent(ABC):
    name: ClassVar[str]

    @abstractmethod
    async def propose(self, inputs: SharedInputs, settings: Settings) -> AgentReport:
        """Pure function of its inputs: same inputs, same proposals."""
