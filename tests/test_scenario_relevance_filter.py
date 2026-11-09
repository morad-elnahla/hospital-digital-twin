import asyncio
from datetime import datetime, timedelta

from hospital_agents import Orchestrator, Settings
from hospital_agents.agents.base import Agent, AgentReport
from hospital_agents.contracts import (Booking, Forecast, Pool, Proposal, Reschedule, SharedInputs,
                                       Slot, SlotKey, TwinSnapshot, Urgency)


class MixedScheduleAgent(Agent):
    name = "appointment"

    async def propose(self, inputs, settings):
        src = SlotKey("OR", "OR-1", datetime(2026, 1, 1, 8))
        dst = SlotKey("OR", "OR-2", datetime(2026, 1, 2, 8))
        clinic_src = SlotKey("CLINIC", "CL-1", datetime(2026, 1, 1, 9))
        clinic_dst = SlotKey("CLINIC", "CL-1", datetime(2026, 1, 2, 9))
        return AgentReport("appointment", proposals=(
            Proposal("clinic-move", "appointment", "Clinic appointment move",
                     (Reschedule("CL-1", clinic_src, clinic_dst),), ()),
            Proposal("icu-surgery", "appointment", "Elective surgery needing ICU move",
                     (Reschedule("S-ICU", src, dst),), ()),
        ))


def test_scenario_arbitration_drops_clinic_moves_but_keeps_icu_surgery():
    as_of = datetime(2026, 1, 1, 6)
    source = SlotKey("OR", "OR-1", datetime(2026, 1, 1, 8))
    target = SlotKey("OR", "OR-2", datetime(2026, 1, 2, 8))
    slots = (
        Slot(source, source.start + timedelta(hours=1), 480, 60, specialty="ORTHO", team_ids=("TEAM-1",)),
        Slot(target, target.start + timedelta(hours=1), 480, 0, specialty="ORTHO", team_ids=("TEAM-1",)),
    )
    booking = Booking("S-ICU", source, Urgency.NON_URGENT, None, True, 60, "TEAM-1", "ORTHO")
    twin = TwinSnapshot(as_of, "scenario-test", {"ICU:beds": Pool("ICU:beds", 4)}, slots, (booking,), as_of + timedelta(days=3))
    inputs = SharedInputs(twin, Forecast("test", {}), scenario_unit="ICU")

    orchestrator = Orchestrator(Settings(language="en"), agents=[MixedScheduleAgent()])
    decision = asyncio.run(orchestrator.run(inputs))

    assert [p.id for p in decision.accepted] == ["icu-surgery"]
    assert [p.id for p in decision.reports[0].proposals] == ["icu-surgery"]
    assert [item["proposal_id"] for item in orchestrator.unrelated_suggestions] == ["clinic-move"]
