import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { FlaskConical, Plus, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useApp, useHdt } from "@/lib/app-state";
import { fmt, fmtWhen } from "@/lib/i18n";
import { formatIntervention, formatScenarioAction, scenarioBedViews, scenarioMessage } from "@/lib/scenario-ui";
import { cn } from "@/lib/utils";
import { Empty, ErrorBox, PageHead, PageSkeleton, Panel, Pill } from "@/components/hdt/kit";
import { DecisionView, UnavailableList } from "@/components/hdt/decision-view";

export const Route = createFileRoute("/simulator")({
  head: () => ({ meta: [{ title: "Scenario Lab · Hospital Digital Twin" }, { name: "description", content: "Compose and review operational scenarios against the hospital data." }] }),
  component: Simulator,
});

type InterventionType = "demand_change" | "er_arrivals_surge" | "staff_change" | "bed_change" | "or_closed" | "reschedule_surgery";
type Intervention = Record<string, any> & { type: InterventionType };
const UNITS = ["ER", "ICU", "WARD"] as const;
const TYPES: InterventionType[] = ["demand_change", "er_arrivals_surge", "staff_change", "bed_change", "or_closed", "reschedule_surgery"];
const blank = (type: InterventionType): Intervention => ({
  demand_change: { type, unit: "ICU", x: 1.2 },
  er_arrivals_surge: { type, x: 1.2 },
  staff_change: { type, unit: "ICU", role: "NURSE", delta: 1 },
  bed_change: { type, unit: "ICU", delta: 1 },
  or_closed: { type, or_id: "", dates: [""] },
  reschedule_surgery: { type, booking_id: "", target: { domain: "OR", resource_id: "", start: "" } },
}[type]);

function Simulator() {
  const { t, asOf, setAsOf, lang, can, mode, user } = useApp();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [unit, setUnit] = useState<"ER" | "ICU" | "WARD">("ICU");
  const [mult, setMult] = useState(1.3);
  const [horizon, setHorizon] = useState(7);
  const [seed, setSeed] = useState(0);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const rooms = useHdt<any>("or").data?.by_room ?? [];
  const drafts = useQuery({ queryKey: ["scenario-drafts", mode, user?.username], queryFn: () => api<any[]>("/api/scenario-drafts"), enabled: mode === "live" && !!user?.permissions.includes("run") });
  const body = useMemo(() => ({ as_of: asOf, unit, multiplier: mult, horizon, seed, interventions, language: lang, scenario_lab: true }), [asOf, unit, mult, horizon, seed, interventions, lang]);
  const currentKey = JSON.stringify(body);
  const sim = useMutation({ mutationFn: () => api<any>("/api/simulate", body), onSuccess: () => setPreviewKey(currentKey) });
  const run = useMutation({
    mutationFn: () => api<any>("/api/run", body),
    onSuccess: (d) => { toast.success(`${t("scenario_decision_created")} · ${d.status}`); nav({ to: "/decisions" }); },
    onError: (e: any) => toast.error(e.message),
  });
  const save = useMutation({
    mutationFn: () => api<any>("/api/scenario-drafts", body),
    onSuccess: (d) => { toast.success(t("draft_saved", { id: String(d.id).slice(0, 8) })); qc.invalidateQueries({ queryKey: ["scenario-drafts"] }); },
    onError: (e: any) => toast.error(e.message),
  });
  const previewValid = previewKey === currentKey;
  const r = previewValid ? sim.data : null;
  const setInt = (i: number, patch: Partial<Intervention>) => setInterventions((xs) => xs.map((x, n) => n === i ? { ...x, ...patch } : x));
  const reviewDraft = (d: any) => {
    const s = d.scenario;
    setAsOf(String(s.as_of ?? asOf)); setUnit(s.unit); setMult(s.demand_multiplier); setHorizon(s.horizon ?? 7); setSeed(s.seed ?? 0); setInterventions(s.interventions ?? []); setPreviewKey(null); sim.reset();
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return <div className="space-y-5">
    <PageHead title={t("nav_simulator")} sub={t("sim_sub")} />
    <Panel prov="simulation" title={t("scenario_lab")} sub={t("scenario_lab_sub")}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="space-y-1 text-xs font-semibold">{t("as_of")}
          <input lang={lang} type="datetime-local" value={asOf.slice(0, 16)} onChange={(e) => setAsOf(e.target.value ? `${e.target.value}:00` : asOf)} className="num block w-full rounded-lg border bg-card px-3 py-2" />
        </label>
        <label className="space-y-1 text-xs font-semibold">{t("horizon_days")}
          <input type="number" min={1} max={30} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} className="num block w-full rounded-lg border bg-card px-3 py-2" />
        </label>
        <label className="space-y-1 text-xs font-semibold">{t("scenario_unit")}
          <select value={unit} onChange={(e) => setUnit(e.target.value as any)} className="block w-full rounded-lg border bg-card px-3 py-2">{UNITS.map((u) => <option key={u} value={u}>{t("unit_" + u)}</option>)}</select>
        </label>
        <label className="space-y-1 text-xs font-semibold">{t("seed")}
          <input type="number" min={0} max={2147483647} value={seed} onChange={(e) => setSeed(Number(e.target.value))} className="num block w-full rounded-lg border bg-card px-3 py-2" />
        </label>
      </div>
      <label className="mt-4 block max-w-2xl text-xs font-semibold">{t("demand_multiplier")} <span className="num ms-2 text-base">×{mult}</span>
        <input type="range" dir="ltr" min={0.1} max={50} step={0.1} value={mult} onChange={(e) => setMult(+e.target.value)} className="mt-2 w-full accent-[var(--primary)]" />
      </label>
      <div className="mt-5 space-y-3">
        {interventions.map((x, i) => <InterventionEditor key={i} value={x} index={i} rooms={rooms} onChange={(p) => setInt(i, p)} onType={(type) => setInt(i, blank(type))} onRemove={() => setInterventions((xs) => xs.filter((_, n) => n !== i))} />)}
        <div className="flex flex-wrap items-center gap-2">
          <select id="intervention-type" className="rounded-lg border bg-card px-3 py-2 text-sm">{TYPES.map((type) => <option key={type} value={type}>{t(`intervention_${type}`)}</option>)}</select>
          <button onClick={() => { const el = document.getElementById("intervention-type") as HTMLSelectElement; setInterventions((xs) => [...xs, blank(el.value as InterventionType)]); setPreviewKey(null); }} className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-semibold hover:bg-muted"><Plus className="size-4" />{t("add_intervention")}</button>
        </div>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <button disabled={!can("run") || sim.isPending} onClick={() => sim.mutate()} className="bg-brand inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-bold text-primary-foreground disabled:opacity-50"><FlaskConical className="size-4" />{sim.isPending ? t("loading") : t("run_preview")}</button>
        <button disabled={!previewValid || !can("run") || save.isPending} onClick={() => save.mutate()} title={!previewValid ? t("preview_stale") : undefined} className="inline-flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-semibold disabled:opacity-50"><Save className="size-4" />{t("save_scenario_draft")}</button>
        <button disabled={!previewValid || !can("run") || run.isPending} onClick={() => run.mutate()} title={!can("decide") ? t("draft_manager_review") : t("submit_for_approval")} className="inline-flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-semibold disabled:opacity-50">{t("submit_for_approval")}</button>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">{t("scenario_lab_note")} · {t("schematic")}</p>
      {sim.data && !previewValid && <p className="mt-2 text-xs font-semibold text-warn">{t("preview_stale")}</p>}
      {sim.error && <div className="mt-3"><ErrorBox error={sim.error} /></div>}
    </Panel>

    {drafts.data && <Panel title={t("scenario_drafts")} sub={t("draft_review_help")} prov="agent">
      {user?.role === "clinician" && <p className="mb-3 rounded-lg bg-muted/60 p-3 text-xs">{t("draft_clinician_note")}</p>}
      {drafts.data.length ? <ul className="space-y-2">{drafts.data.map((d: any) => <li key={d.id} className="flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm"><span className="num text-xs">{String(d.id).slice(0, 8)}</span><b>{t(`unit_${d.scenario?.unit}`)} ×{d.scenario?.demand_multiplier}</b><span className="text-xs text-muted-foreground">{fmtWhen(lang, d.scenario?.as_of)} · {d.status} · {d.created_by}</span><button onClick={() => reviewDraft(d)} className="ms-auto rounded-lg border px-3 py-1.5 text-xs font-semibold">{t("review_draft")}</button></li>)}</ul> : <Empty>{t("no_scenario_drafts")}</Empty>}
      {drafts.error && <ErrorBox error={drafts.error} />}
    </Panel>}

    {r && <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
      <div className="surface flex flex-wrap items-center gap-3 p-4"><Pill tone="info">{t("as_of")}: <bdi className="num">{fmtWhen(lang, r.as_of)}</bdi></Pill><Pill tone="warn">{t("assumption_label")}</Pill><span className="text-xs text-muted-foreground">{t(`unit_${r.scenario?.unit}`)} ×{r.scenario?.demand_multiplier} · {t("horizon_days")}: {r.scenario?.horizon}</span></div>
      <ScenarioCore r={r} />
      {r.scenario?.interventions?.length > 0 && <Panel title={t("scenario_interventions")} prov="simulation"><ul className="list-disc space-y-1 ps-5 text-sm">{r.scenario.interventions.map((item: any, i: number) => <li key={i} dir="auto">{formatIntervention(item, lang, t)}</li>)}</ul></Panel>}
      <Panel title={t("before_after")} sub={t("capacity_arith")} prov="simulation">
        <div className="grid gap-3 md:grid-cols-3">{UNITS.map((u) => { const view = scenarioBedViews(u, r.before[u], r.after[u], r.core); return <BeforeAfter key={u} unit={u} b={view.before} a={view.after} change={r.bed_change[u]} />; })}</div>
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4"><Fact l={t("cost")} v={`${fmt(r.capacity_cost_change_egp_per_day, 0)} ${t("u_EGP/day")}`} /><Fact l={t("rescheduled")} v={fmt(r.rescheduled_bookings, 0)} /></div>
      </Panel>
      <Panel title={t("proposed_actions")} sub={t("proposed_actions_sub")} prov="agent">
        {r.scenario_relevant_actions?.length ? <ul className="list-disc space-y-1 ps-5 text-sm">{r.scenario_relevant_actions.map((a: any, i: number) => <li key={i} dir="auto">{t(`agent_${a.agent}`)}: {formatScenarioAction(a.action, lang, t)}</li>)}</ul> : <Empty>{t("no_scenario_actions")}</Empty>}
        {!!r.not_related_actions?.length && <details className="mt-3 rounded-lg border p-3 text-sm"><summary className="cursor-pointer font-semibold">{t("unrelated_suggestions_not_scenario", { n: r.not_related_actions.length })}</summary><ul className="mt-2 list-disc space-y-1 ps-5 text-xs text-muted-foreground">{r.not_related_actions.map((a: any, i: number) => <li key={`${a.proposal_id}-${i}`} dir="auto">{t(a.label_code)}: {formatScenarioAction(a.action, lang, t)}</li>)}</ul></details>}
      </Panel>
      {r.core?.notes?.length > 0 && <Panel title={t("scenario_warnings")} prov="simulation"><ul className="list-disc space-y-1 ps-5 text-sm">{r.core.notes.map((n: any, i: number) => <li key={i} dir="auto">{scenarioMessage({ code: n.warning_code, params: n.warning_params }, t)}</li>)}</ul></Panel>}
      {r.core?.rejected?.length > 0 && <Panel title={t("intervention_rejections")} prov="simulation"><ul className="list-disc space-y-1 ps-5 text-sm">{r.core.rejected.map((n: any, i: number) => <li key={i} dir="auto">{formatIntervention(n.intervention, lang, t)} — {scenarioMessage({ code: n.reason_code, params: n.reason_params }, t)}</li>)}</ul></Panel>}
      <UnavailableList items={r.unavailable} />
      {r.core?.wait_revenue_overtime && <Panel title={t("unavailable_metrics")} prov="simulation"><ul className="space-y-1 text-sm">{Object.entries(r.core.wait_revenue_overtime).map(([k, v]: any) => <li key={k}><b>{t(`metric_${k}`)}</b>: {t(`status_${v.status}`)} — {scenarioMessage({ code: v.reason_code, params: v.reason_params }, t)}</li>)}</ul></Panel>}
      <DecisionView d={r.decision} />
    </motion.div>}
  </div>;
}

function InterventionEditor({ value: x, index, rooms, onChange, onType, onRemove }: { value: Intervention; index: number; rooms: any[]; onChange: (p: Partial<Intervention>) => void; onType: (t: InterventionType) => void; onRemove: () => void }) {
  const { t } = useApp();
  const field = (label: string, value: any, change: (v: string) => void, type = "text", extra: any = {}) => <label className="min-w-32 flex-1 space-y-1 text-[11px] font-semibold">{label}<input type={type} value={value ?? ""} onChange={(e) => change(e.target.value)} className="block w-full rounded-lg border bg-card px-2.5 py-2 text-sm" {...extra} /></label>;
  const unitField = <label className="min-w-32 flex-1 space-y-1 text-[11px] font-semibold">{t("scenario_unit")}<select value={x.unit ?? "ICU"} onChange={(e) => onChange({ unit: e.target.value })} className="block w-full rounded-lg border bg-card px-2.5 py-2 text-sm">{UNITS.map((u) => <option key={u}>{u}</option>)}</select></label>;
  const roomField = <label className="min-w-32 flex-1 space-y-1 text-[11px] font-semibold">{t("operating_room")}<select value={x.or_id ?? ""} onChange={(e) => onChange({ or_id: e.target.value || null })} className="block w-full rounded-lg border bg-card px-2.5 py-2 text-sm"><option value="">{t("all_rooms")}</option>{rooms.map((r: any) => <option key={r.or_id} value={r.or_id}>{r.name} · {r.or_id}</option>)}</select></label>;
  let inputs: any;
  if (x.type === "demand_change") inputs = <>{unitField}{field(t("multiplier_x"), x.x, (v) => onChange({ x: Number(v) }), "number", { min: 0.1, max: 50, step: 0.1 })}</>;
  else if (x.type === "er_arrivals_surge") inputs = field(t("multiplier_x"), x.x, (v) => onChange({ x: Number(v) }), "number", { min: 0.1, max: 50, step: 0.1 });
  else if (x.type === "staff_change") inputs = <>{unitField}<label className="min-w-32 flex-1 space-y-1 text-[11px] font-semibold">{t("staff_role")}<select value={x.role} onChange={(e) => onChange({ role: e.target.value })} className="block w-full rounded-lg border bg-card px-2.5 py-2 text-sm"><option>NURSE</option><option>DOCTOR</option></select></label>{field(t("staff_delta"), x.delta ?? x.absent_pct, (v) => onChange(x.absent_pct != null ? { absent_pct: Number(v), delta: undefined } : { delta: Number(v), absent_pct: undefined }), "number")}</>;
  else if (x.type === "bed_change") inputs = <>{unitField}{field(t("bed_delta"), x.delta, (v) => onChange({ delta: Number(v) }), "number", { step: 1 })}</>;
  else if (x.type === "or_closed") inputs = <>{roomField}{field(t("closure_dates"), (x.dates ?? []).join(", "), (v) => onChange({ dates: v.split(",").map((s) => s.trim()).filter(Boolean) }), "text", { placeholder: "YYYY-MM-DD, YYYY-MM-DD" })}</>;
  else inputs = <>{field(t("booking_id"), x.booking_id, (v) => onChange({ booking_id: v }), "text", { placeholder: "surgery_id" })}{field(t("target_or"), x.target?.resource_id ?? "", (v) => onChange({ target: { ...x.target, domain: "OR", resource_id: v } }), "text", { placeholder: "OR ID" })}{field(t("target_start"), String(x.target?.start ?? "").slice(0, 16), (v) => onChange({ target: { ...x.target, domain: "OR", start: v.length === 16 ? v + ":00" : v } }), "datetime-local")}</>;
  return <div className="rounded-xl border bg-muted/20 p-3"><div className="mb-2 flex items-center gap-2"><b className="text-xs">{t("intervention_n", { n: index + 1 })}</b><select value={x.type} onChange={(e) => onType(e.target.value as InterventionType)} className="rounded-lg border bg-card px-2 py-1.5 text-xs">{TYPES.map((type) => <option key={type} value={type}>{t(`intervention_${type}`)}</option>)}</select><button onClick={onRemove} className="ms-auto grid size-8 place-items-center rounded-lg text-bad hover:bg-bad/10" aria-label={t("remove_intervention")}><Trash2 className="size-4" /></button></div><div className="flex flex-wrap gap-2">{inputs}</div></div>;
}

function ScenarioCore({ r }: { r: any }) {
  const { t, lang } = useApp();
  const core = r.core ?? {};
  return <Panel title={t("scenario_core")} sub={t("assumption_label")} prov="simulation">
    <div className="overflow-x-auto"><table className="w-full text-start text-xs"><thead><tr className="border-b text-muted-foreground"><th className="p-2">{t("department")}</th><th className="p-2">{t("baseline")}</th><th className="p-2">{t("scenario_demand")}</th><th className="p-2">{t("delta")}</th><th className="p-2">{t("shortfall")}</th><th className="p-2">{t("nurse_need")}</th><th className="p-2">{t("nurse_available")}</th></tr></thead><tbody>{UNITS.map((u) => { const d = core.bed_demand?.[u] ?? {}; const n = d.nurse_demand ?? {}; const delta = core.before_after_delta?.[u] ?? {}; return <tr key={u} className="border-b"><th className="p-2">{t("unit_" + u)}</th><td className="num p-2">{fmt(d.baseline, 1)}</td><td className="num p-2">{fmt(d.demand, 1)}</td><td className="num p-2">{fmt(delta.delta, 1)}</td><td className="num p-2 text-bad">{fmt(d.shortfall, 0)}</td><td className="num p-2">{fmt(n.required, 1)}</td><td className="num p-2">{fmt(n.available, 0)}</td></tr>; })}</tbody></table></div>
    <p className="mt-2 text-xs font-semibold text-warn">{t("assumption_label")}</p>
    {core.er_arrivals && <p className="mt-2 text-xs" dir="auto">{t("arrivals_transition", { before: fmt(core.er_arrivals.baseline_mean, 1), after: fmt(core.er_arrivals.scenario_mean, 1) })} · {t("assumption_label")}</p>}
    <div className="mt-2 text-xs text-muted-foreground">{[...Object.entries(core.doctor_demand ?? {}), ...Object.entries(core.resource_demand ?? {})].map(([u, d]: any) => <p key={`${u}-${d.status}`} dir="auto">{t(`unit_${u}`)}: {t(`status_${d.status}`)} — {scenarioMessage({ code: d.reason_code, params: d.reason_params }, t)}</p>)}</div>
    <div className="mt-2 space-y-1 text-xs">{UNITS.map((u) => { const d = core.bed_demand?.[u] ?? {}; const unit = t(`unit_${u}`); return <div key={u} dir="auto">
      {d.status === "abstain" && <p>{t("scenario_unit_reason_line", { unit, reason: scenarioMessage({ code: d.reason_code, params: d.reason_params }, t) })}</p>}
      {d.residual_message && <p className="font-semibold text-bad">{t("scenario_unit_reason_line", { unit, reason: scenarioMessage(d.residual_message, t) })}</p>}
      {d.why_nothing_moved && <p>{t("scenario_unit_why_line", { unit, label: t("why_nothing_moved"), reason: scenarioMessage(d.why_nothing_moved, t) })}</p>}
      {(d.what_would_help ?? []).map((x: any, i: number) => <p key={i}>{t("scenario_unit_help_line", { unit, label: t("what_would_help"), reason: scenarioMessage(x, t) })}</p>)}
    </div>; })}</div>
  </Panel>;
}

function Fact({ l, v }: { l: string; v: string }) { return <div className="surface p-3"><div className="num text-lg font-bold">{v}</div><div className="truncate text-[11px] text-muted-foreground">{l}</div></div>; }

function BeforeAfter({ unit, b, a, change }: { unit: string; b: any; a: any; change: number }) {
  const { t } = useApp();
  const max = Math.max(b.beds, a.beds, b.peak_demand_beds ?? 0, a.peak_demand_beds ?? 0, 1);
  const row = (label: string, s: any, tone: string) => <div><div className="mb-1 flex justify-between text-xs"><span className="text-muted-foreground">{label}</span><span className="num">{s.beds} {t("u_beds")}</span></div><div className="relative h-3 rounded-full bg-muted"><motion.div className="absolute inset-y-0 start-0 rounded-full" style={{ background: tone }} initial={{ width: 0 }} animate={{ width: `${(100 * s.beds) / max}%` }} transition={{ duration: 0.9 }} />{s.peak_demand_beds != null && <motion.div className="absolute inset-y-[-3px] w-0.5 bg-bad" initial={{ insetInlineStart: 0 }} animate={{ insetInlineStart: `${(100 * s.peak_demand_beds) / max}%` }} transition={{ duration: 0.9 }} />}</div></div>;
  return <div className="surface space-y-3 p-4"><div className="flex items-center justify-between"><b>{t("unit_" + unit)}</b>{change !== 0 && <Pill tone={change > 0 ? "good" : "warn"}><span className="num">{change > 0 ? "+" : ""}{change}</span></Pill>}</div>{row(t("before"), b, "var(--observed)")}{row(t("after"), a, "var(--agent)")}<div className="grid grid-cols-2 gap-2 text-xs"><div className="rounded-lg bg-muted/60 p-2"><div className="num font-bold">{b.peak_utilisation_pct == null ? "—" : fmt(b.peak_utilisation_pct) + "%"} → {a.peak_utilisation_pct == null ? "—" : fmt(a.peak_utilisation_pct) + "%"}</div><div className="text-muted-foreground">{t("utilisation")}</div></div><div className="rounded-lg bg-muted/60 p-2"><div className={cn("num font-bold", a.shortfall_beds ? "text-bad" : "")}>{a.shortfall_beds ?? "—"}</div><div className="text-muted-foreground">{t("shortfall_beds")}</div></div></div>{a.assumed_relief_beds != null && <div className="text-[11px] text-warn">{t("if_assumed", { r: a.assumed_relief_beds, n: a.shortfall_if_assumed_beds ?? "—" })}</div>}</div>;
}
