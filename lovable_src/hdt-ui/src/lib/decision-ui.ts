import type { Lang } from "./i18n";
import { translate } from "./i18n";

/** The three NO_ACTION causes the backend reports via `no_action_code`. */
export type NoActionKind = "no_proposals" | "all_rejected" | "advisory" | null;

/** Reads the backend's `no_action_code`; never infers the cause from status text alone. */
export function noActionKind(d: any): NoActionKind {
  const code: string | undefined = d?.no_action_code;
  if (code === "none.reason.no_proposals") return "no_proposals";
  if (code === "none.reason.all_rejected") return "all_rejected";
  if (code === "none.reason.advisory") return "advisory";
  return null;
}

/** Confirmed unmet need, from a list item (`unmet`) or a detail view (`card.unmet`). */
export function unmetOf(d: any): Record<string, number> {
  const u = d?.unmet ?? d?.card?.unmet ?? {};
  return u && typeof u === "object" ? u : {};
}

export function unmetTotal(d: any): number {
  return Object.values(unmetOf(d)).reduce((s, v) => s + (typeof v === "number" ? v : 0), 0);
}

export type NoActionDisplay = { kind: Exclude<NoActionKind, null>; unmet: number; labelKey: string };

/**
 * The precise NO_ACTION story, from the backend's `no_action_code` plus the confirmed
 * shortfall in `card.unmet` — never inferred from the status or proposal counts alone:
 * - unmet 0 → nothing needs doing
 * - unmet > 0, all proposals rejected → forecast shortfall with no safe action available
 * - unmet > 0, no proposals → a need exists but no proposals are available
 * - advisory → recommendations only, nothing to apply
 * (`none.reason.no_proposals` alone does not say whether a shortfall exists — `unmet` does.)
 */
export function noActionDisplay(d: any): NoActionDisplay | null {
  const kind = noActionKind(d);
  if (!kind) return null;
  const unmet = unmetTotal(d);
  if (kind === "advisory") return { kind, unmet, labelKey: "no_action_advisory" };
  if (kind === "all_rejected") return { kind, unmet, labelKey: "no_action_all_rejected" };
  return { kind, unmet, labelKey: unmet > 0 ? "no_action_need_no_proposals" : "no_action_none_needed" };
}

/**
 * Message shown right after POST /api/run succeeds, built from the status the backend
 * actually returned — never a hard-coded "pending" label.
 */
export function runCreatedMessage(d: any, lang: Lang): string {
  if (d?.status === "ESCALATE") return translate(lang, "st_ESCALATE");
  if (d?.status === "NO_ACTION") {
    return d.note ?? d.no_action_reason ?? translate(lang, "st_NO_ACTION");
  }
  const st = translate(lang, "st_" + (d?.status ?? "PENDING"));
  return `${translate(lang, "decision_created")} — ${st}`;
}

/**
 * Payload for the decide endpoints, matching app.py exactly:
 * approve reads `note`, reject reads `reason`. Sending `note` to reject loses the reason.
 */
export function decidePayload(kind: "approve" | "reject", text: string): Record<string, string> {
  return kind === "approve" ? { note: text } : { reason: text };
}

/**
 * Approve/reject buttons may show only for a PENDING decision in the hands of a user
 * with the `decide` permission. NO_ACTION and closed decisions never get buttons.
 */
export function canActOnDecision(d: any, permissions: string[] | undefined): boolean {
  return d?.status === "PENDING" && !!permissions?.includes("decide");
}

/** Pill tone per backend decision status. */
export function statusTone(status: string): "primary" | "good" | "bad" | "info" | "warn" {
  switch (status) {
    case "PENDING":
      return "warn";
    case "ESCALATE":
      return "bad";
    case "APPLIED":
      return "good";
    case "REJECTED":
      return "bad";
    default:
      return "info"; // NO_ACTION, SUPERSEDED, ROLLED_BACK
  }
}

/** Scenario inputs that a simulator preview is valid for. */
export type ScenarioKey = { unit: string; multiplier: number; asOf: string };

export function scenarioKeyOf(s: ScenarioKey): string {
  return `${s.unit}|${s.multiplier}|${s.asOf}`;
}

/**
 * A saved preview is only valid for the exact inputs it was run with. Changing the unit,
 * the multiplier or the replay moment invalidates it, so a stale preview can never be saved.
 */
export function previewMatches(preview: ScenarioKey | null, current: ScenarioKey): boolean {
  return !!preview && scenarioKeyOf(preview) === scenarioKeyOf(current);
}

/**
 * The one status title used by the agents result card, the decisions list and the details:
 * a NO_ACTION with a confirmed shortfall (`card.unmet` > 0) is titled as a shortfall with no
 * safe action, not "no action needed". Other statuses use their plain backend status label.
 */
export function statusLabelKey(d: any): string {
  if (d?.status === "ESCALATE") return "st_ESCALATE";
  if (d?.status !== "NO_ACTION") return "st_" + (d?.status ?? "PENDING");
  const kind = noActionKind(d);
  if (kind === "advisory") return "st_NO_ACTION_advisory";
  if (unmetTotal(d) > 0) return "st_NO_ACTION_shortfall";
  return "st_NO_ACTION";
}
