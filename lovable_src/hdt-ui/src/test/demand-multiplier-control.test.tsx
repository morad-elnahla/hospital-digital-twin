import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DemandMultiplierControl, clampDemandMultiplier, stepDemandMultiplier } from "@/components/hdt/demand-multiplier-control";

describe("demand multiplier control", () => {
  it("accepts exact values in the API range and rejects out-of-range input", () => {
    expect(clampDemandMultiplier(1.3)).toBe(true);
    expect(clampDemandMultiplier(11.9)).toBe(true);
    expect(clampDemandMultiplier(0.09)).toBe(false);
    expect(clampDemandMultiplier(50.1)).toBe(false);
  });

  it("steps by 0.1 and by 0.01 with Shift, clamped at the bounds", () => {
    expect(stepDemandMultiplier(1.3, 1)).toBe(1.4);
    expect(stepDemandMultiplier(1.3, -1, true)).toBe(1.29);
    expect(stepDemandMultiplier(50, 1)).toBe(50);
    expect(stepDemandMultiplier(0.1, -1, true)).toBe(0.1);
  });

  it("keeps exact input, slider, stepper and shifted keyboard changes synchronized", () => {
    const onChange = vi.fn();
    render(<DemandMultiplierControl value={1.3} onChange={onChange} label="Demand multiplier" lang="en" t={(k) => k} />);
    const field = screen.getByRole("spinbutton", { name: "Demand multiplier" });
    fireEvent.change(field, { target: { value: "11.9" } });
    fireEvent.blur(field);
    expect(onChange).toHaveBeenCalledWith(11.9);
    fireEvent.click(screen.getByRole("button", { name: "multiplier_step_up" }));
    expect(onChange).toHaveBeenLastCalledWith(1.4);
    fireEvent.keyDown(field, { key: "ArrowUp", shiftKey: true });
    expect(onChange).toHaveBeenLastCalledWith(1.31);
  });

  it("keeps the control RTL while the exact number stays left-to-right in Arabic", () => {
    render(<DemandMultiplierControl value={1.3} onChange={() => {}} label="مضاعف الطلب" lang="ar" t={(k) => k} />);
    expect(screen.getByRole("slider", { name: "مضاعف الطلب" })).toHaveAttribute("dir", "ltr");
    expect(screen.getByRole("spinbutton", { name: "مضاعف الطلب" })).toHaveAttribute("dir", "ltr");
    expect(screen.getByRole("spinbutton", { name: "مضاعف الطلب" }).parentElement).toHaveAttribute("dir", "rtl");
  });
});
