from datetime import datetime, timedelta

from hospital_agents.arbitration import Arbitrator
from hospital_agents.config import Settings
from hospital_agents.contracts import Booking, PolicyBundle, Pool, Proposal, Reschedule, Slot, SlotKey, TwinSnapshot, Urgency


def _move(team_id, target_teams):
    now = datetime(2026, 1, 1)
    src, dst = SlotKey("OR", "OR-1", now), SlotKey("OR", "OR-2", now + timedelta(days=1))
    booking = Booking("S-1", src, Urgency.NON_URGENT, None, False, 60, team_id, "ORTHO")
    slots = (Slot(src, now + timedelta(days=1), 480, 60, specialty="ORTHO"),
             Slot(dst, now + timedelta(days=2), 480, 0, specialty="ORTHO", team_ids=target_teams))
    snap = TwinSnapshot(now, "test", {"ICU:beds": Pool("ICU:beds", 1)}, slots, (booking,), now + timedelta(days=3))
    proposal = Proposal("p1", "scenario", "move", (Reschedule("S-1", src, dst),), ())
    return Arbitrator(Settings()).resolve(snap, PolicyBundle(), (proposal,))


def test_or_move_fails_closed_without_verifiable_team():
    result = _move("TEAM-1", ())
    assert not result.accepted
    assert any("team" in r.lower() and ("unverifiable" in r.lower() or "verify" in r.lower())
               for r in result.rejected[0].reasons)


def test_or_move_accepted_when_open_compatible_and_free():
    result = _move("TEAM-1", ("TEAM-1",))
    assert len(result.accepted) == 1
    assert not result.rejected
