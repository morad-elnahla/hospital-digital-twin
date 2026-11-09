import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Cpu, Database, FileText, Search, ShieldCheck, Table2, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useApp, useHdt } from "@/lib/app-state";
import { fmt } from "@/lib/i18n";
import { checkLabel, featureLabel } from "@/lib/system-ar";
import { cn } from "@/lib/utils";
import { ErrorBox, PageHead, PageSkeleton, Panel, Pill } from "@/components/hdt/kit";

export const Route = createFileRoute("/system")({
  head: () => ({
    meta: [
      { title: "Data and system · Hospital Digital Twin" },
      { name: "description", content: "Data quality checks, policies, knowledge sources and system status." },
      { property: "og:title", content: "Data quality and system status" },
      { property: "og:description", content: "Tables, quality checks, nurse-ratio policies and LLM status." },
    ],
  }),
  component: SystemPage,
});

function SystemPage() {
  const { t, can, mode, lang } = useApp();
  const qc = useQueryClient();
  const st = useHdt<any>("status", { scoped: false });
  const ql = useHdt<any>("quality", { scoped: false });
  const pol = useHdt<any>("policies", { scoped: false });
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const kn = useQuery({ queryKey: ["knowledge", mode, submitted], queryFn: () => api<any>("/api/knowledge?q=" + encodeURIComponent(submitted)), enabled: !!mode });
  if (st.error) return <ErrorBox error={st.error} retry={() => st.refetch()} />;
  if (!st.data || !ql.data) return <PageSkeleton />;
  const s = st.data;
  const q = ql.data;
  const failed = q.summary.fail ?? 0;
  const setPolicy = async (unit: string, value: string | null) => {
    try {
      await api("/api/policies", { unit, value });
      toast.success(t("policy_saved"));
      qc.invalidateQueries({ queryKey: ["hdt"] });
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  const tables = Object.entries(q.tables as Record<string, number>).sort((a, b) => b[1] - a[1]);
  const maxRows = Math.max(...tables.map(([, v]) => v), 1);

  return (
    <div className="space-y-5">
      <PageHead title={t("nav_system")} sub={t("system_sub")} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Summary I={CheckCircle2} tone="good" v={q.summary.pass} l={t("data_quality")} sub={t("quality_sub", { p: q.summary.pass, w: q.summary.warn, f: failed })} />
        <Summary I={AlertTriangle} tone="warn" v={q.summary.warn} l={t("st_data")} sub={`${fmt(q.days, 0)} · ${q.period.from} → ${q.period.to}`} />
        <Summary I={Table2} tone="primary" v={tables.length} l={t("tables")} sub={t("tables_sub", { d: q.days })} />
        <Summary I={Cpu} tone={s.llm.configured ? "good" : "info"} v={s.llm.configured ? "✓" : "—"} l={t("st_llm")} sub={t(s.llm.configured ? "llm_on_short" : "llm_off_short")} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2" title={t("data_quality")} sub={t("quality_sub", { p: q.summary.pass, w: q.summary.warn, f: failed })} prov="observed" period={q.period}>
          <ul className="space-y-2">
            {q.checks.map((c: any, i: number) => {
              const L = checkLabel(lang, c.name, c.detail);
              const ok = c.status === "pass";
              return (
                <motion.li key={c.name} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.025 }} className="flex items-start gap-3 rounded-xl border bg-muted/30 p-3">
                  <span className={cn("grid size-8 shrink-0 place-items-center rounded-lg", ok ? "bg-good/12 text-good" : c.status === "fail" ? "bg-bad/12 text-bad" : "bg-warn/15 text-warn")}>
                    {ok ? <CheckCircle2 className="size-4" /> : <AlertTriangle className="size-4" />}
                  </span>
                  <div className="min-w-0 flex-1 text-start">
                    <div className="text-sm font-semibold">{L.name}</div>
                    <div className="mt-0.5 text-xs leading-relaxed text-muted-foreground" dir="auto">{L.detail}</div>
                  </div>
                  <span className="num shrink-0 rounded-lg bg-card px-2 py-0.5 text-sm font-bold">{fmt(c.value, 0)}</span>
                </motion.li>
              );
            })}
          </ul>
        </Panel>

        <Panel title={t("tables")} sub={t("tables_sub", { d: q.days })} prov="observed">
          <div className="mb-2 flex justify-between px-1 text-[11px] font-semibold text-muted-foreground">
            <span>{t("sys_tables_col")}</span>
            <span>{t("sys_rows_col")}</span>
          </div>
          <ul className="space-y-1.5">
            {tables.map(([k, v]) => (
              <li key={k} className="rounded-lg px-1 py-1">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <bdi className="num truncate font-medium">{k}</bdi>
                  <span className="num font-bold">{fmt(v, 0)}</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                  <motion.div className="h-full rounded-full bg-primary/70" initial={{ width: 0 }} animate={{ width: `${Math.max(2, (v / maxRows) * 100)}%` }} transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }} />
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={t("nurse_policy")} sub={can("policy") ? t("max_patients") : t("manager_only")} prov="observed">
          <div className="space-y-2">
            {["ER", "ICU", "WARD"].map((u) => {
              const cur = pol.data?.nurse_ratio?.find((p: any) => p.unit === u);
              const approve = async () => {
                try { await api("/api/policies", { unit: u, approve: true }); toast.success(t("policy_approved")); qc.invalidateQueries({ queryKey: ["hdt"] }); }
                catch (e: any) { toast.error(e.message); }
              };
              return <PolicyRow key={u} unit={u} current={cur?.value ?? cur?.ratio ?? null} approved={cur?.approved !== false} source={cur?.source} disabled={!can("policy")} canApprove={u === "ER" && cur?.value != null && cur?.approved === false && can("policy")} onApprove={approve} onSave={(v) => setPolicy(u, v)} />;
            })}
          </div>
          <p className="mt-3 flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <ShieldCheck className="size-3.5" /> {t("sys_fingerprint")}: <bdi className="num">{pol.data?.fingerprint}</bdi>
          </p>
        </Panel>

        <Panel title={t("features")} sub={t("features_sub")} prov="agent" right={<Pill tone={s.llm.configured ? "good" : "info"}>{t(s.llm.configured ? "llm_on_short" : "llm_off_short")}</Pill>}>
          <div className="mb-3 grid grid-cols-2 gap-2 text-sm">
            <div className="rounded-xl bg-muted/60 p-3"><div className="text-[11px] text-muted-foreground">{t("sys_provider")}</div><bdi className="font-bold">{s.llm.provider}</bdi></div>
            <div className="rounded-xl bg-muted/60 p-3"><div className="text-[11px] text-muted-foreground">{t("sys_model")}</div><bdi className="num text-xs font-bold">{s.llm.model}</bdi></div>
          </div>
          <ul className="space-y-2">
            {s.features.map((f: any) => {
              const L = featureLabel(lang, f.name, f.note);
              return (
                <li key={f.name} className="flex items-start gap-2.5 rounded-xl border p-2.5">
                  <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", f.available ? "bg-good" : "bg-muted-foreground/40")} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                      {L.name}
                      <Pill tone={f.available ? "good" : "info"}>{f.available ? t("available") : t("st_off")}</Pill>
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground" dir="auto">{L.note}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </Panel>
      </div>

      <Panel title={t("nav_sources")} prov="observed">
        <form onSubmit={(e) => { e.preventDefault(); setSubmitted(query); }} className="mb-4 flex gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("search_ph")} dir="auto" className="w-full rounded-xl border bg-card py-2.5 ps-9 pe-3 text-sm" />
          </div>
          <button className="bg-brand rounded-xl px-4 text-sm font-bold text-primary-foreground">{t("sys_search_go")}</button>
        </form>
        {kn.error && <ErrorBox error={kn.error} />}
        {kn.data && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2">
              <h4 className="flex items-center gap-1.5 text-xs font-bold text-muted-foreground"><FileText className="size-3.5" />{t("sys_passages")}</h4>
              {!kn.data.passages?.length && !kn.data.pack_policies?.length && <p className="text-xs text-muted-foreground">{t("sys_no_results")}</p>}
              {kn.data.passages?.map((p: any, i: number) => (
                <div key={i} className="rounded-xl border p-3 text-xs" dir="auto"><b>{p.title ?? p.source}</b><p className="mt-1 leading-relaxed text-muted-foreground">{p.text}</p></div>
              ))}
              {kn.data.pack_policies?.map((p: any) => (
                <div key={p.id} className="rounded-xl bg-muted/60 p-3 text-xs" dir="auto"><b>{p.id}</b> · {p.source}<p className="mt-1 leading-relaxed text-muted-foreground">{p.text}</p></div>
              ))}
            </div>
            <div className="space-y-2">
              <h4 className="flex items-center gap-1.5 text-xs font-bold text-muted-foreground"><Database className="size-3.5" />{t("sys_sources")}</h4>
              {kn.data.sources?.map((s: any) => (
                <div key={s.id} className="rounded-xl border p-3 text-xs">
                  <div className="flex items-start justify-between gap-2"><b dir="auto">{s.title}</b><Pill>{s.status}</Pill></div>
                  <p className="mt-1 text-muted-foreground" dir="auto">{s.version} · {s.country}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}

function Summary({ I, v, l, sub, tone }: { I: typeof Cpu; v: number | string; l: string; sub: string; tone: "good" | "warn" | "primary" | "info" }) {
  const cls = { good: "bg-good/12 text-good", warn: "bg-warn/15 text-warn", primary: "bg-primary-soft text-primary", info: "bg-muted text-muted-foreground" }[tone];
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="surface flex items-center gap-3 p-4">
      <span className={cn("grid size-11 shrink-0 place-items-center rounded-xl", cls)}><I className="size-5" /></span>
      <div className="min-w-0">
        <div className="num text-2xl font-extrabold">{v}</div>
        <div className="truncate text-xs font-semibold">{l}</div>
        <div className="truncate text-[11px] text-muted-foreground">{sub}</div>
      </div>
    </motion.div>
  );
}

function PolicyRow({ unit, current, approved, source, disabled, canApprove, onApprove, onSave }: { unit: string; current: string | number | null; approved: boolean; source?: string; disabled: boolean; canApprove: boolean; onApprove: () => void; onSave: (v: string | null) => void }) {
  const { t } = useApp();
  const [v, setV] = useState(current == null ? "" : String(current));
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl bg-muted/60 p-2.5">
      <b className="min-w-24 text-sm">{t("unit_" + unit)}</b>
      <span className="text-[11px] text-muted-foreground">{t("current")}: <b className="num text-foreground">{current ?? t("not_set")}</b></span>
      {unit === "ER" && <Pill tone={approved ? "good" : "warn"}>{approved ? t("policy_approved_status") : t("draft_unapproved")}</Pill>}
      {source && <span className="basis-full text-[11px] text-muted-foreground">{source}</span>}
      <div className="ms-auto flex items-center gap-2">
        <input value={v} onChange={(e) => setV(e.target.value)} placeholder={t("sys_ratio_ph")} inputMode="decimal" className="num w-28 rounded-lg border bg-card px-2 py-1 text-center text-sm" disabled={disabled} />
        <button disabled={disabled || !v} onClick={() => onSave(v)} className="rounded-lg bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground disabled:opacity-40">{t("save")}</button>
        {canApprove && <button disabled={disabled} onClick={onApprove} className="rounded-lg border border-good/40 px-3 py-1 text-xs font-semibold text-good disabled:opacity-40">{t("approve_policy")}</button>}
        {current != null && (
          <button disabled={disabled} onClick={() => onSave(null)} aria-label={t("remove")} className="grid size-7 place-items-center rounded-lg text-bad hover:bg-bad/10 disabled:opacity-40"><X className="size-4" /></button>
        )}
      </div>
    </div>
  );
}
