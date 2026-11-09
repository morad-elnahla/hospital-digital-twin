import { describe, expect, it } from "vitest";
import { scenarioBedViews, formatScenarioAction } from "@/lib/scenario-ui";
import { fmtWhen } from "@/lib/i18n";

const t = (key: string, v: Record<string, string | number> = {}) =>
  `${key} ${Object.entries(v).map(([k, value]) => `${k}=${value}`).join(" ")}`;

describe("Scenario Lab display", () => {
  it("keeps before/after shortfall and utilization aligned with the scenario table", () => {
    const core = {
      bed_demand: { ICU: { baseline: 11, demand: 12, shortfall: 2 } },
      before_after_delta: { ICU: { baseline_shortfall: 1, scenario_shortfall: 2 } },
    };
    const views = scenarioBedViews("ICU", { beds: 10 }, { beds: 10 }, core);
    expect(views.before.shortfall_beds).toBe(core.before_after_delta.ICU.baseline_shortfall);
    expect(views.after.shortfall_beds).toBe(core.bed_demand.ICU.shortfall);
    expect(views.before.peak_utilisation_pct).toBe(110);
    expect(views.after.peak_utilisation_pct).toBe(120);
  });

  it("renders surgery actions as booking and readable slot details", () => {
    const value = formatScenarioAction({
      booking_id: "B-7",
      from_slot: { domain: "OR", resource_id: "OR-1", start: "2026-10-17T08:00:00" },
      to_slot: { domain: "OR", resource_id: "OR-2", start: "2026-10-18T09:30:00" },
    }, "ar", t);
    expect(value).toContain("id=B-7");
    expect(value).toContain("OR-1");
    expect(value).toContain("OR-2");
    expect(value).not.toContain("{");
  });

  it("formats Arabic scenario times with a 24-hour clock and year", () => {
    const when = fmtWhen("ar", "2026-10-17T08:00:00");
    expect(when).toContain("2026");
    expect(when).not.toMatch(/\b(?:AM|PM)\b/i);
  });
});
