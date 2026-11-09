import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import { Bot, Play } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-state";
import { runCreatedMessage, statusLabelKey, statusTone } from "@/lib/decision-ui";
import { formatScenarioAction, scenarioMessage } from "@/lib/scenario-ui";
import { cn } from "@/lib/utils";
import { ErrorBox, PageHead, Panel, Pill } from "@/components/hdt/kit";
import { DecisionView } from "@/components/hdt/decision-view";

export const Route = createFileRoute("/agents")({
  head: () => ({
    meta: [
      { title: "AI agents · Hospital Digital Twin" },
      { name: "description", content: "Run the seven specialist agents on a demand scenario and review their accepted and rejected proposals." },
      { property: "og:title", content: "Seven specialist agents" },
      { property: "og:description", content: "Run the agents on an ICU or WARD demand shock and see what arbitration accepts, rejects and why." },
    ],
  }),
  component: Agents,
});

const AGENTS = ["er", "bed", "staff", "resource", "finance", "or", "appointment"] as const;

function Agents() {
  const { t, asOf, lang, can, mode } = useApp();
  const nav = useNavigate();
  const [unit, setUnit] = useState<"ICU" | "WARD">("ICU");
  const [mult, setMult] = useState(12);
  const run = useMutation({
    mutationFn: () => api<any>("/api/run", { as_of: asOf, unit, multiplier: mult, language: lang }),
    onSuccess: (d) => toast.success(runCreatedMessage(d, lang)),
    onError: (e: any) => toast.error(e.message),
  });
  const d = run.data;
  return (
    <div className="space-y-5">
      <PageHead title={t("nav_agents")} sub={t("agents_sub")} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        {AGENTS.map((a, i) => (
          <motion.div
            key={a}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: i * 0.05, ease: [0.22, 1, 0.36, 1] }}
            className="surface p-3"
          >
            <div className="bg-agent/10 text-agent mb-2 grid size-8 place-items-center rounded-lg">
              <Bot className="size-4" />
            </div>
            <b className="block text-[13px]">{t("agent_" + a)}</b>
            <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{t("agent_role_" + a)}</p>
          </motion.div>
        ))}
      </div>

      <Panel prov="agent" title={t("stress_unit")}>
        <div className="flex flex-wrap items-end gap-5">
          <div className="flex rounded-xl bg-muted p-1">
            {(["ICU", "WARD"] as const).map((u) => (
              <button key={u} onClick={() => setUnit(u)} className={cn("relative rounded-lg px-4 py-1.5 text-sm font-semibold", unit === u ? "text-primary-foreground" : "text-muted-foreground")}>
                {unit === u && <motion.span layoutId="agents-unit-pill" className="bg-brand absolute inset-0 rounded-lg" />}
                <span className="relative">{t("unit_" + u)}</span>
              </button>
            ))}
          </div>
          <label className="min-w-56 flex-1">
            <div className="mb-1 flex justify-between text-xs font-semibold text-muted-foreground">
              {t("multiplier")} <span className="num text-base text-foreground">×{mult}</span>
            </div>
            <input type="range" dir="ltr" min={1} max={20} step={0.5} value={mult} onChange={(e) => setMult(+e.target.value)} className="w-full accent-[var(--primary)]" />
          </label>
          <button
            disabled={run.isPending || !can("run")}
            title={!can("run") ? t("no_permission") : undefined}
            onClick={() => run.mutate()}
            className="bg-brand inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-bold text-primary-foreground shadow-float transition-transform hover:scale-[1.02] disabled:opacity-50"
          >
            <Play className="size-4" /> {run.isPending ? t("loading") : t("run_agents")}
          </button>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">{t("stress_note")}</p>
      </Panel>

      {run.error && <ErrorBox error={run.error} />}
      {run.isPending && <div className="h-40 animate-pulse rounded-2xl bg-muted" />}
      {!d && !run.isPending && !run.error && <Panel><p className="py-6 text-center text-sm text-muted-foreground">{t("run_prompt")}</p></Panel>}
      {d && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          <div className="surface flex flex-wrap items-center gap-3 p-4">
            <Pill tone={statusTone(d.status)}>{t(statusLabelKey(d))}</Pill>
            <span className="num text-xs text-muted-foreground" dir="ltr">{d.id}</span>
            <span className="text-xs text-muted-foreground">{t("counts", { a: d.accepted?.length ?? 0, r: d.rejected?.length ?? 0 })}</span>
            <button onClick={() => nav({ to: "/decisions" })} className="ms-auto rounded-lg border px-3 py-1.5 text-xs font-semibold hover:bg-muted">
              {t("open_decisions_btn")}
            </button>
          </div>
          {d.scenario_core && <Panel title={t("scenario_core")} sub={t("assumption_label")} prov="simulation">
            <div className="space-y-2 text-sm">{Object.entries(d.scenario_core.bed_demand ?? {}).map(([key, row]: any) => {
              const unit = t(`unit_${key}`);
              return <div key={key} dir="auto" className="space-y-1">
                {row.residual_message && <p className="font-semibold text-bad">{t("scenario_unit_reason_line", { unit, reason: scenarioMessage(row.residual_message, t) })}</p>}
                {row.why_nothing_moved && <p>{t("scenario_unit_why_line", { unit, label: t("why_nothing_moved"), reason: scenarioMessage(row.why_nothing_moved, t) })}</p>}
                {(row.what_would_help ?? []).map((item: any, i: number) => <p key={i}>{t("scenario_unit_help_line", { unit, label: t("what_would_help"), reason: scenarioMessage(item, t) })}</p>)}
                {row.status === "abstain" && <p>{t("scenario_unit_reason_line", { unit, reason: scenarioMessage({ code: row.reason_code, params: row.reason_params }, t) })}</p>}
              </div>;
            })}</div>
          </Panel>}
          {!!d.unrelated_suggestions?.length && <details className="surface p-4 text-sm">
            <summary className="cursor-pointer font-semibold">{t("unrelated_suggestions_not_scenario", { n: d.unrelated_suggestions.length })}</summary>
            <ul className="mt-2 list-disc space-y-1 ps-5 text-xs text-muted-foreground">{d.unrelated_suggestions.map((item: any, i: number) => <li key={`${item.proposal_id}-${i}`} dir="auto">{t("not_related_action")}: {formatScenarioAction(item.action, lang, t)}</li>)}</ul>
          </details>}
          <DecisionView d={d} />
        </motion.div>
      )}
    </div>
  );
}
