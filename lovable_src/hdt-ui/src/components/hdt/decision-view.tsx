import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { useApp } from "@/lib/app-state";
import { noActionDisplay, noActionKind, statusLabelKey, unmetOf } from "@/lib/decision-ui";
import { fmt } from "@/lib/i18n";
import { scenarioMessage } from "@/lib/scenario-ui";
import { Empty, Panel, Pill, Unavailable } from "./kit";

type T = (k: string, v?: Record<string, string | number>) => string;

/** Banner explaining a NO_ACTION decision, driven by the backend's `no_action_code` + `card.unmet`. */
function NoActionBanner({ d, t }: { d: any; t: T }) {
  const disp = noActionDisplay(d);
  if (!disp) return null;
  const unmetList = Object.entries(unmetOf(d)).map(([k, v]) => `${k}: ${v}`).join(", ");
  if (disp.kind === "all_rejected") {
    return (
      <div className="rounded-2xl border border-bad/30 bg-bad/5 p-4" data-testid="no-action-all-rejected">
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-bad" />
          <div>
            <b className="text-sm text-bad" data-testid="no-action-title">{t(statusLabelKey(d))}</b><p className="mt-1 text-sm">{t(disp.labelKey)}</p>
            {unmetList && <p className="mt-1 text-sm font-semibold text-bad">{t("unmet_after", { list: unmetList })}</p>}
            {d.no_action_reason && <p className="mt-1 text-sm">{d.no_action_reason}</p>}
            <p className="mt-1 text-xs text-muted-foreground">{t("rejection_is_safety")}</p>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-2xl border border-primary/25 bg-primary-soft p-4" data-testid={`no-action-${disp.kind}`}>
      <div className="flex items-start gap-2">
        <Info className="mt-0.5 size-4 shrink-0 text-primary" />
        <div>
          <b className="text-sm" data-testid="no-action-title">{t(statusLabelKey(d))}</b><p className="mt-1 text-sm">{t(disp.labelKey)}</p>
          {disp.kind === "no_proposals" && unmetList && (
            <p className="mt-1 text-sm font-semibold text-bad">{t("unmet_after", { list: unmetList })}</p>
          )}
          {d.no_action_reason && <p className="mt-1 text-sm text-muted-foreground">{d.no_action_reason}</p>}
        </div>
      </div>
    </div>
  );
}

function EscalationBanner({ d, t }: { d: any; t: T }) {
  const rows = Object.entries(d?.scenario_core?.bed_demand ?? {}) as [string, any][];
  const residuals = rows.filter(([, row]) => Number(row?.residual_shortfall_beds) > 0);
  if (!residuals.length) return null;
  return <div className="rounded-2xl border border-bad/30 bg-bad/5 p-4" data-testid="decision-escalation">
    <b className="text-sm text-bad">{t("st_ESCALATE")}</b>
    <ul className="mt-2 space-y-2 text-sm">{residuals.map(([unit, row]) => <li key={unit}>
      <p className="font-semibold">{t("unit_" + unit)}: {t("escalation_residual", { beds: row.residual_shortfall_beds })}</p>
      {(row.what_would_help ?? []).map((item: any, i: number) => <p key={i} className="text-muted-foreground">{t("what_would_help")}: {scenarioMessage(item, t)}</p>)}
    </li>)}</ul>
    {d.escalation_note && <p className="mt-2 text-xs">{t("escalation_note_label")}: {d.escalation_note}</p>}
  </div>;
}

/** Pure body so tests can render it with a plain `t` function (no app context). */
export function DecisionViewBody({ d, t }: { d: any; t: T }) {
  const card = d.card ?? {};
  const kind = noActionKind(d);
  return (
    <div className="space-y-4">
      {d.status === "ESCALATE" ? <EscalationBanner d={d} t={t} /> : <NoActionBanner d={d} t={t} />}
      <Panel title={t("exec_card")} prov="agent">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl bg-muted/60 p-3">
            <div className="text-[11px] text-muted-foreground">{t("bottleneck")}</div>
            <b className="num">{card.critical_bottleneck ?? t("none_found")}</b>
          </div>
          <div className="rounded-xl bg-muted/60 p-3">
            <div className="text-[11px] text-muted-foreground">{t("wait_saved")}</div>
            <b>{card.waiting_minutes_saved ?? t("unavailable")}</b>
          </div>
          <div className="rounded-xl bg-muted/60 p-3">
            <div className="text-[11px] text-muted-foreground">{t("confidence")}</div>
            <b>{card.confidence ?? t("unavailable")}</b>
          </div>
        </div>
        {kind !== "all_rejected" && card.unmet && Object.keys(card.unmet).length > 0 && (
          <p className="mt-3 text-sm text-bad">{t("unmet_after", { list: Object.entries(card.unmet).map(([k, v]) => `${k}: ${v}`).join(", ") })}</p>
        )}
        {card.unmet_if_assumed && Object.keys(card.unmet_if_assumed).length > 0 && (
          <p className="mt-1 text-sm text-warn">{t("relief_note", { list: Object.entries(card.unmet_if_assumed).map(([k, v]) => `${k}: ${v}`).join(", ") })}</p>
        )}
        {!kind && d.no_action_reason && <p className="mt-3 text-sm">{d.no_action_reason}</p>}
        {card.summary && <p className="mt-3 text-sm leading-relaxed">{card.summary}</p>}
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {card.assumptions?.length > 0 && (
            <div>
              <h4 className="mb-1 text-xs font-bold text-muted-foreground">{t("assumptions")}</h4>
              <ul className="list-disc space-y-0.5 ps-4 text-xs" dir="auto">{card.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul>
            </div>
          )}
          {card.unverified?.length > 0 && (
            <div>
              <h4 className="mb-1 text-xs font-bold text-muted-foreground">{t("not_verified")}</h4>
              <ul className="list-disc space-y-0.5 ps-4 text-xs" dir="auto">{card.unverified.map((a: string) => <li key={a}>{a}</li>)}</ul>
            </div>
          )}
        </div>
      </Panel>
      {card.warnings?.length > 0 && (
        <Panel title={t("safety_warnings")} prov="agent">
          <ul className="space-y-2" data-testid="safety-warnings">
            {card.warnings.map((w: string, i: number) => (
              <li key={i} className="flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/5 p-3 text-sm leading-relaxed break-words">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" />
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={t("accepted")} sub={t("accepted_sub")} prov="agent">
          {d.accepted?.length ? (
            <ul className="space-y-2">
              {d.accepted.map((p: any) => (
                <li key={p.id} className="rounded-xl border border-good/30 bg-good/5 p-3">
                  <div className="flex items-center gap-2"><CheckCircle2 className="size-4 text-good" /><b className="text-sm" dir="auto">{p.title}</b></div>
                  <ul className="mt-1.5 list-disc ps-6 text-xs text-muted-foreground" dir="auto">{p.rationale?.map((r: string) => <li key={r}>{r}</li>)}</ul>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>{t("no_actions")}</Empty>
          )}
        </Panel>
        <Panel title={t("rejected")} sub={t("rejected_sub")} prov="agent">
          {d.rejected?.length ? (
            <ul className="space-y-2">
              {d.rejected.map((r: any) => (
                <li key={r.proposal.id} className="rounded-xl border border-bad/30 bg-bad/5 p-3">
                  <div className="flex items-center gap-2"><XCircle className="size-4 text-bad" /><b className="text-sm" dir="auto">{r.proposal.title}</b></div>
                  <ul className="mt-1.5 space-y-1 text-xs leading-relaxed break-words text-bad/90" data-testid="rejection-reasons">{r.reasons?.map((x: string) => <li key={x} className="rounded-lg bg-bad/5 px-2 py-1">{x}</li>)}</ul>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>—</Empty>
          )}
        </Panel>
      </div>
      {d.reports?.length > 0 && (
        <Panel title={t("agent_reports")} prov="agent">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {d.reports.map((r: any) => (
              <div key={r.agent} className="rounded-xl bg-muted/60 p-3">
                <div className="flex items-center justify-between">
                  <b className="text-sm">{t("agent_" + r.agent)}</b>
                  <Pill tone={r.proposals.length ? "primary" : "info"}>{r.proposals.length ? t("proposed", { n: r.proposals.length }) : t("no_proposal")}</Pill>
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground">{t("agent_role_" + r.agent)}</p>
                {r.findings?.map((f: any, i: number) => (
                  <div key={i} className="num mt-1 text-[11px]" dir="ltr">{f.pool}: {fmt(f.projected)} / {f.total}</div>
                ))}
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}

/** Renders the agents' output (accepted, rejected, card, reports) exactly as the backend returns it. */
export function DecisionView({ d }: { d: any }) {
  const { t } = useApp();
  return <DecisionViewBody d={d} t={t} />;
}

export function UnavailableList({ items }: { items: { metric: string; reason: string }[] }) {
  return (
    <div className="grid gap-2 md:grid-cols-3">
      {items.map((u) => (
        <Unavailable key={u.metric} title={u.metric} why={u.reason} />
      ))}
    </div>
  );
}
