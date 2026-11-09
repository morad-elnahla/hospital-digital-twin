import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Check, RotateCcw, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useApp, useHdt } from "@/lib/app-state";
import { canActOnDecision, decidePayload, noActionDisplay, statusLabelKey, statusTone } from "@/lib/decision-ui";
import { fmtWhen } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Empty, ErrorBox, PageHead, PageSkeleton, Panel, Pill } from "@/components/hdt/kit";
import { DecisionView } from "@/components/hdt/decision-view";

export const Route = createFileRoute("/decisions")({
  head: () => ({
    meta: [
      { title: "Decisions · Hospital Digital Twin" },
      { name: "description", content: "Review, approve, reject and roll back agent decisions in the sandbox." },
      { property: "og:title", content: "Human-reviewed decisions" },
      { property: "og:description", content: "Every agent decision with approval, sandbox state and audit trail." },
    ],
  }),
  component: Decisions,
});

/** Precise NO_ACTION cause in the list, from the item's `no_action_code` + confirmed `unmet`. */
function NoActionLine({ x }: { x: any }) {
  const { t } = useApp();
  if (x.status === "ESCALATE") {
    const residual = Object.entries(x.scenario_core?.bed_demand ?? {}).filter(([, row]: any) => Number(row?.residual_shortfall_beds) > 0);
    return <div className="mt-1 text-[11px] leading-snug text-bad" data-testid="list-escalation">
      {t("st_ESCALATE")}{residual.map(([unit, row]: any) => <span key={unit} className="num"> · {t("unit_" + unit)}: {row.residual_shortfall_beds} {t("shortfall_beds")}</span>)}
    </div>;
  }
  const disp = noActionDisplay(x);
  if (!disp) return x.note ? <div className="mt-1 text-[11px] leading-snug text-muted-foreground">{x.note}</div> : null;
  return (
    <div className="mt-1 text-[11px] leading-snug text-muted-foreground" data-testid={`list-no-action-${disp.kind}`}>
      {t(disp.labelKey)}
      {disp.unmet > 0 && <span className="num font-semibold text-bad"> · {t("unmet_short")}: {disp.unmet}</span>}
    </div>
  );
}

function DecisionItem({ x, open, onOpen }: { x: any; open: boolean; onOpen: () => void }) {
  const { t, lang } = useApp();
  return (
    <li>
      <button onClick={onOpen} className={cn("w-full rounded-xl border p-3 text-start hover:bg-muted", open && "border-primary bg-primary-soft")}>
        <div className="flex items-center justify-between gap-2">
          <b className="num truncate text-xs" dir="ltr">{x.id}</b>
          <Pill tone={statusTone(x.status)}>{t(statusLabelKey(x))}</Pill>
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          {x.scenario?.unit} ×{x.scenario?.demand_multiplier} · {fmtWhen(lang, x.as_of)} · {t("counts", { a: x.accepted ?? 0, r: x.rejected ?? 0 })}
        </div>
        {x.status === "NO_ACTION" && <NoActionLine x={x} />}
        {x.stale && <div className="mt-1 text-[11px] text-warn">{x.stale_reason}</div>}
      </button>
    </li>
  );
}

function Decisions() {
  const { t, lang, can, mode, user } = useApp();
  const qc = useQueryClient();
  const list = useHdt<any[]>("decisions", { scoped: false });
  const sb = useHdt<any>("sandbox", { scoped: false });
  const [open, setOpen] = useState<string | null>(null);
  const detail = useQuery({ queryKey: ["decision", open, lang], queryFn: () => api<any>("/api/decisions/" + open + (mode === "live" ? "?lang=" + lang : "")), enabled: !!open });
  const [note, setNote] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["hdt"] }).then(() => detail.refetch());
  const act = useMutation({
    mutationFn: ({ kind }: { kind: "approve" | "reject" | "rollback" | "acknowledge-escalation" }) =>
      kind === "rollback" ? api("/api/rollback", { note }) : api(`/api/decisions/${open}/${kind}`, kind === "acknowledge-escalation" ? { note } : decidePayload(kind, note)),
    onSuccess: (d: any, { kind }) => {
      toast.success(kind === "rollback" ? t("rolled_back") : kind === "approve" ? t("applied_ok") : kind === "acknowledge-escalation" ? t("st_ESCALATE") : t("rejected_ok"));
      if (d?.status) toast.info(t("st_" + d.status));
      setNote("");
      refresh();
    },
    onError: (e: any) => toast.error(e.message),
  });
  if (list.error) return <ErrorBox error={list.error} />;
  if (!list.data) return <PageSkeleton />;
  const d = detail.data;
  const pending = list.data.filter((x) => x.status === "PENDING");
  const history = list.data.filter((x) => x.status !== "PENDING");
  const actionable = canActOnDecision(d, user?.permissions);
  return (
    <div className="space-y-5">
      <PageHead title={t("nav_decisions")} sub={t("decisions_sub")} />
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4">
          <Panel title={t("pending_review")} prov="agent">
            {list.data.length === 0 ? (
              <Empty>{t("no_decisions")}</Empty>
            ) : pending.length === 0 ? (
              <Empty>{t("pending_empty")}</Empty>
            ) : (
              <ul className="space-y-1.5">{pending.map((x) => <DecisionItem key={x.id} x={x} open={open === x.id} onOpen={() => setOpen(x.id)} />)}</ul>
            )}
          </Panel>
          {history.length > 0 && (
            <Panel title={t("history")} prov="agent">
              <ul className="space-y-1.5">{history.map((x) => <DecisionItem key={x.id} x={x} open={open === x.id} onOpen={() => setOpen(x.id)} />)}</ul>
            </Panel>
          )}
        </div>
        <Panel className="xl:col-span-2" title={t("sandbox")} sub={t("sandbox_sub")} prov="simulation" right={
          <button disabled={!can("decide") || !sb.data?.applied?.length} onClick={() => act.mutate({ kind: "rollback" })} className="inline-flex items-center gap-1.5 rounded-lg border border-bad/30 px-3 py-1.5 text-xs font-semibold text-bad hover:bg-bad/5 disabled:opacity-40">
            <RotateCcw className="size-3.5" /> {t("rollback_last")}
          </button>
        }>
          {sb.data?.applied?.length ? (
            <ul className="space-y-1 text-sm">{sb.data.applied.map((a: any, i: number) => <li key={i} className="num rounded-lg bg-muted/60 px-3 py-1.5 text-xs" dir="ltr">{typeof a === "string" ? a : JSON.stringify(a)}</li>)}</ul>
          ) : (
            <Empty>{t("sandbox_empty")}</Empty>
          )}
        </Panel>
      </div>
      {open && detail.isLoading && <PageSkeleton />}
      {d && (
        <div className="space-y-4">
          {d.status === "PENDING" && (
            <div className="surface space-y-3 p-4">
              <p className="text-xs leading-relaxed text-muted-foreground">{t("approve_note")}</p>
              {d.stale && <p className="text-xs font-semibold text-warn">{t("stale_msg")} {d.stale_reason}</p>}
              <div className="flex flex-wrap items-center gap-3">
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("note_ph")} className="min-w-48 flex-1 rounded-lg border bg-card px-3 py-2 text-sm" />
                <button disabled={!actionable || d.stale} title={!can("decide") ? t("no_permission") : undefined} onClick={() => act.mutate({ kind: "approve" })} className="bg-brand inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-bold text-primary-foreground disabled:opacity-50"><Check className="size-4" /> {t("approve")}</button>
                <button disabled={!actionable} title={!can("decide") ? t("no_permission") : undefined} onClick={() => act.mutate({ kind: "reject" })} className="inline-flex items-center gap-1.5 rounded-lg border px-4 py-2 text-sm font-semibold hover:bg-muted disabled:opacity-50"><X className="size-4" /> {t("reject")}</button>
              </div>
            </div>
          )}
          {d.status === "ESCALATE" && <div className="surface space-y-3 p-4">
            <p className="text-xs leading-relaxed text-muted-foreground">{t("escalation_cannot_apply")}</p>
            <div className="flex flex-wrap items-center gap-3">
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("escalation_note_label")} className="min-w-48 flex-1 rounded-lg border bg-card px-3 py-2 text-sm" />
              <button disabled={!can("decide") || !note.trim()} title={!can("decide") ? t("no_permission") : undefined} onClick={() => act.mutate({ kind: "acknowledge-escalation" })} className="rounded-lg border px-4 py-2 text-sm font-semibold disabled:opacity-50">{t("acknowledge_escalation")}</button>
            </div>
          </div>}
          <DecisionView d={d} />
        </div>
      )}
    </div>
  );
}
