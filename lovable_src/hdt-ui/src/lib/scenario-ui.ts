import { fmtDay, fmtWhen } from "@/lib/i18n";

type T = (key: string, values?: Record<string, string | number>) => string;

export function scenarioMessage(value: any, t: T): string {
  if (!value || typeof value !== "object" || !value.code) return "";
  return t(`scenario_${value.code}`, value.params ?? {});
}

export function scenarioBedViews(unit: string, before: any, after: any, core: any) {
  const d = core?.bed_demand?.[unit] ?? {};
  const delta = core?.before_after_delta?.[unit] ?? {};
  const view = (snapshot: any, demand: number | null | undefined, shortfall: number | null | undefined) => ({
    ...snapshot,
    peak_demand_beds: demand ?? null,
    peak_utilisation_pct: demand == null || !snapshot?.beds ? null : Math.round((100 * demand / snapshot.beds) * 10) / 10,
    shortfall_beds: shortfall ?? null,
  });
  return {
    before: view(before, d.baseline, delta.baseline_shortfall),
    after: view(after, d.demand, delta.scenario_shortfall ?? d.shortfall),
  };
}

function slotLabel(slot: any, lang: "ar" | "en") {
  if (!slot) return "—";
  return `${slot.resource_id ?? slot.domain ?? "—"} · ${fmtWhen(lang, slot.start)}`;
}

export function formatScenarioAction(action: any, lang: "ar" | "en", t: T): string {
  if (!action || typeof action !== "object") return "—";
  if (action.booking_id) {
    return t("scenario_action_reschedule", {
      id: action.booking_id,
      from: slotLabel(action.from_slot, lang),
      to: slotLabel(action.to_slot, lang),
    });
  }
  if (action.pool) return t("scenario_action_pool", { pool: action.pool, delta: action.delta ?? 0 });
  if (action.code) return t("scenario_action_alert", { detail: action.detail ?? action.code });
  return t("scenario_action_unknown");
}

export function formatIntervention(item: any, lang: "ar" | "en", t: T): string {
  if (!item || typeof item !== "object") return "—";
  const unit = item.unit ? t(`unit_${item.unit}`) : "";
  switch (item.type) {
    case "demand_change": return t("scenario_intervention_demand", { unit, multiplier: item.x });
    case "er_arrivals_surge": return t("scenario_intervention_er", { multiplier: item.x });
    case "staff_change": return t("scenario_intervention_staff", { unit, role: t(item.role === "DOCTOR" ? "role_doctor" : "role_nurse"), change: item.absent_pct != null ? `${item.absent_pct}%` : item.delta ?? 0 });
    case "bed_change": return t("scenario_intervention_beds", { unit, change: item.delta ?? 0 });
    case "or_closed": return t("scenario_intervention_or_closed", { room: item.or_id ?? t("all_rooms"), dates: (item.dates ?? []).map((d: string) => fmtDay(lang, d)).join(", ") });
    case "reschedule_surgery": return t("scenario_intervention_surgery", { id: item.booking_id ?? "—", room: item.target?.resource_id ?? "—", when: fmtWhen(lang, item.target?.start) });
    default: return t("scenario_intervention_unknown");
  }
}
