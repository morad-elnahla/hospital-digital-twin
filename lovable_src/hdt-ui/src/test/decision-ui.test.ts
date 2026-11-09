import { describe, expect, it } from "vitest";
import { canActOnDecision, decidePayload, noActionDisplay, noActionKind, previewMatches, runCreatedMessage, statusTone, unmetTotal } from "@/lib/decision-ui";

describe("decidePayload", () => {
  it("approve sends `note` (what app.py reads)", () => {
    expect(decidePayload("approve", "ok")).toEqual({ note: "ok" });
  });
  it("reject sends `reason`, never `note` — otherwise the reason is lost", () => {
    const p = decidePayload("reject", "too risky");
    expect(p).toEqual({ reason: "too risky" });
    expect(p).not.toHaveProperty("note");
  });
});

describe("canActOnDecision", () => {
  const perms = ["read", "run", "decide"];
  it("allows a PENDING decision for a user with `decide`", () => {
    expect(canActOnDecision({ status: "PENDING" }, perms)).toBe(true);
  });
  it("blocks NO_ACTION and closed decisions even for a manager", () => {
    for (const status of ["NO_ACTION", "ESCALATE", "APPLIED", "REJECTED", "ROLLED_BACK", "SUPERSEDED"]) {
      expect(canActOnDecision({ status }, perms)).toBe(false);
    }
  });
  it("blocks analyst and viewer (no `decide` permission)", () => {
    expect(canActOnDecision({ status: "PENDING" }, ["read", "run"])).toBe(false);
    expect(canActOnDecision({ status: "PENDING" }, ["read"])).toBe(false);
    expect(canActOnDecision({ status: "PENDING" }, undefined)).toBe(false);
  });
});

describe("noActionKind", () => {
  it("maps the three backend codes", () => {
    expect(noActionKind({ no_action_code: "none.reason.no_proposals" })).toBe("no_proposals");
    expect(noActionKind({ no_action_code: "none.reason.all_rejected" })).toBe("all_rejected");
    expect(noActionKind({ no_action_code: "none.reason.advisory" })).toBe("advisory");
  });
  it("returns null for missing or unknown codes", () => {
    expect(noActionKind({})).toBeNull();
    expect(noActionKind({ no_action_code: "something.else" })).toBeNull();
  });
});

describe("noActionDisplay", () => {
  it("unmet 0 with no proposals → nothing needs doing", () => {
    const d = noActionDisplay({ no_action_code: "none.reason.no_proposals", card: { unmet: {} } });
    expect(d?.labelKey).toBe("no_action_none_needed");
    expect(d?.unmet).toBe(0);
  });
  it("unmet > 0 with no proposals → need exists but no proposals available", () => {
    const d = noActionDisplay({ no_action_code: "none.reason.no_proposals", card: { unmet: { ICU: 3 } } });
    expect(d?.labelKey).toBe("no_action_need_no_proposals");
    expect(d?.unmet).toBe(3);
  });
  it("unmet > 0 with all proposals rejected → shortfall with no safe action", () => {
    const d = noActionDisplay({ no_action_code: "none.reason.all_rejected", card: { unmet: { WARD: 5 } } });
    expect(d?.labelKey).toBe("no_action_all_rejected");
    expect(d?.unmet).toBe(5);
  });
  it("advisory stays advisory regardless of unmet", () => {
    expect(noActionDisplay({ no_action_code: "none.reason.advisory" })?.labelKey).toBe("no_action_advisory");
  });
  it("reads `unmet` from list items and `card.unmet` from detail views", () => {
    expect(unmetTotal({ unmet: { ICU: 2, WARD: 1 } })).toBe(3);
    expect(unmetTotal({ card: { unmet: { ICU: 4 } } })).toBe(4);
    expect(unmetTotal({})).toBe(0);
  });
  it("returns null for non-NO_ACTION decisions", () => {
    expect(noActionDisplay({ status: "PENDING" })).toBeNull();
  });
});

describe("statusTone", () => {
  it("gives each status its own tone", () => {
    expect(statusTone("PENDING")).toBe("warn");
    expect(statusTone("APPLIED")).toBe("good");
    expect(statusTone("REJECTED")).toBe("bad");
    expect(statusTone("NO_ACTION")).toBe("info");
    expect(statusTone("ESCALATE")).toBe("bad");
    expect(statusTone("ROLLED_BACK")).toBe("info");
  });
});

describe("runCreatedMessage", () => {
  it("shows the backend's actual status, not a hard-coded pending label", () => {
    expect(runCreatedMessage({ status: "PENDING" }, "en")).toContain("Pending");
    expect(runCreatedMessage({ status: "PENDING" }, "ar")).toContain("معلّقة");
  });
  it("shows the NO_ACTION reason when the run closed itself", () => {
    expect(runCreatedMessage({ status: "NO_ACTION", note: "لا يوجد إجراء" }, "ar")).toBe("لا يوجد إجراء");
  });
  it("uses the explicit escalation label for residual shortfall", () => {
    expect(runCreatedMessage({ status: "ESCALATE" }, "en")).toBe("ESCALATE — residual shortfall; manager escalation required");
  });
});

describe("previewMatches", () => {
  const cur = { unit: "ICU", multiplier: 12, asOf: "2026-10-17T08:00:00" };
  it("accepts the exact inputs the preview ran with", () => {
    expect(previewMatches({ ...cur }, cur)).toBe(true);
  });
  it("rejects after changing unit, multiplier or replay moment", () => {
    expect(previewMatches({ ...cur, unit: "WARD" }, cur)).toBe(false);
    expect(previewMatches({ ...cur, multiplier: 5 }, cur)).toBe(false);
    expect(previewMatches({ ...cur, asOf: "2026-10-18T08:00:00" }, cur)).toBe(false);
    expect(previewMatches(null, cur)).toBe(false);
  });
});
