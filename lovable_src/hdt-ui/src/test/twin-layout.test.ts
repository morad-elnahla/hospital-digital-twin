import { describe, expect, it } from "vitest";
import { layoutTwin, deptLoad, FLOOR_OF } from "@/components/twin/layout";

const twin = { departments: [
  { id: "er", type: "ER", name: "Emergency", name_ar: "الطوارئ", beds_total: 12, occupied: 6, beds: Array.from({ length: 12 }, (_, i) => ({ id: `er-${i}`, room: "ER 1", occupied: i < 6 })) },
  { id: "icu", type: "ICU", name: "ICU", name_ar: "العناية", beds_total: 12, occupied: 7, beds: Array.from({ length: 12 }, (_, i) => ({ id: `icu-${i}`, room: "ICU 1", occupied: i < 7 })) },
  { id: "ward", type: "WARD", name: "Ward", name_ar: "القسم", beds_total: 36, occupied: 12, beds: Array.from({ length: 36 }, (_, i) => ({ id: `ward-${i}`, room: "Ward 1", occupied: i < 12 })) },
  { id: "or", type: "OR", name: "OR", name_ar: "العمليات", rooms: [] },
  { id: "clinic", type: "CLINIC", name: "Clinic", name_ar: "العيادات", rooms: [] },
  { id: "imaging", type: "IMAGING", name: "Imaging", name_ar: "الأشعة", rooms: [] },
  { id: "lab", type: "LAB", name: "Lab", name_ar: "المختبر", rooms: [] },
] };

describe("3D twin layout", () => {
  const layout = layoutTwin(twin as any);
  it("places every department from the data on a floor", () => {
    expect(layout.map((d) => d.dept.id).sort()).toEqual(twin.departments.map((d) => d.id).sort());
  });
  it("keeps every bed of the data pack (60) in the model", () => {
    expect(layout.flatMap((d) => d.rooms.flatMap((r) => r.beds)).length).toBe(60);
  });
  it("puts ICU on level 2 and the ward on level 3", () => {
    expect(FLOOR_OF.ICU).toBe(2);
    expect(FLOOR_OF.WARD).toBe(3);
  });
  it("computes ward load from occupied / total beds", () => {
    const ward = twin.departments.find((d) => d.type === "WARD")!;
    expect(deptLoad(ward as any)).toBeCloseTo(12 / 36);
  });
});
