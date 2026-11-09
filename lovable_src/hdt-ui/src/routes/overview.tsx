import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, BarChart3, BedDouble, CheckCircle2, ChevronLeft, Cpu, Database, Server, Clock, HeartPulse, Scissors, Stethoscope, Timer, UserRound, Users } from "lucide-react";
import { useApp, useHdt } from "@/lib/app-state";
import { fmt, fmtDay } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Bar, DataTable, ErrorBox, PageHead, PageSkeleton, Panel, Pill, sevTone } from "@/components/hdt/kit";
import { Bars, ForecastChart, Spark, TrendChart, zip } from "@/components/hdt/charts";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import hero from "@/assets/hospital-hero.jpg";

export const Route = createFileRoute("/overview")({
  head: () => ({
    meta: [
      { title: "Overview · Hospital Digital Twin" },
      { name: "description", content: "Key hospital indicators, occupancy, ER flow and finance at the replay moment." },
      { property: "og:title", content: "Hospital operations overview" },
      { property: "og:description", content: "Beds, ER waiting, OR utilisation, overtime and revenue in one view." },
    ],
  }),
  component: Overview,
});

const ICON: Record<string, typeof BedDouble> = { beds: BedDouble, patients: UserRound, icu_er: HeartPulse, staff: Users, surgeries: Scissors, er_wait: Clock, or_util: Stethoscope, overtime: Timer };

function Overview() {
  const { t, lang, mode } = useApp();
  const o = useHdt<any>("overview");
  const al = useHdt<any>("alerts");
  if (o.error) return <ErrorBox error={o.error} retry={() => o.refetch()} />;
  if (!o.data) return <PageSkeleton />;
  const d = o.data;
  const n = al.data?.needs_attention ?? 0;
  const top = al.data?.alerts?.[0];
  return (
    <div className="space-y-5">
      <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }} className="hero-band relative overflow-hidden rounded-3xl border">
        <img src={hero} alt="" width={1600} height={560} className="absolute inset-0 h-full w-full object-cover ltr:-scale-x-100 opacity-95" />
        <div className="hero-fade absolute inset-0" />
        <div className="relative flex min-h-44 flex-col justify-center gap-2 p-6 md:min-h-52 md:w-1/2 md:p-8">
          <h1 className="flex items-center gap-3 text-3xl font-extrabold tracking-tight md:text-4xl">
            <span className="bg-brand grid size-11 place-items-center rounded-2xl text-primary-foreground shadow-float"><BarChart3 className="size-5" /></span>
            {t("nav_overview")}
          </h1>
          <p className="text-sm text-muted-foreground md:text-base">{t("replay_note", { when: fmtDay(lang, d.as_of) })}</p>
          <span className={cn("mt-1 inline-flex w-fit items-center gap-2 rounded-full border bg-card/80 px-3 py-1 text-xs font-bold backdrop-blur", mode === "live" ? "text-good" : "text-muted-foreground")}>
            <span className={cn("size-2 rounded-full", mode === "live" ? "bg-good" : "bg-muted-foreground")} />
            {t("mode_live")}
          </span>
        </div>
      </motion.section>

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }} className={cn("flex flex-wrap items-center gap-4 rounded-2xl border p-4", n ? "border-bad/25 bg-bad/8" : "border-good/25 bg-good/8")}>
        <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl", n ? "bg-bad/15 text-bad" : "bg-good/15 text-good")}>
          {n ? <AlertTriangle className="size-5" /> : <CheckCircle2 className="size-5" />}
        </span>
        <div className="min-w-0 flex-1">
          <b>{n ? t("headline_n", { n }) : t("headline_ok")}</b>
          {top && <p className="truncate text-sm text-muted-foreground">{lang === "ar" ? top.title_ar || top.title : top.title}</p>}
        </div>
        <Link to="/alerts" className="inline-flex items-center gap-1 rounded-xl border bg-card px-3 py-1.5 text-sm font-semibold transition-colors hover:bg-muted">
          {t("open_alerts")} <ChevronLeft className="size-4 ltr:rotate-180" />
        </Link>
      </motion.div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:gap-4 xl:grid-cols-4">
        {d.cards.map((c: any, i: number) => {
          const I = ICON[c.key] ?? BedDouble;
          const up = (c.delta_pct ?? 0) >= 0;
          const col = c.tone === "bad" ? "var(--bad)" : c.tone === "good" ? "var(--good)" : `var(--chart-${(i % 5) + 1})`;
          return (
            <motion.div key={c.key} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.04, duration: 0.45 }} whileHover={{ y: -3 }} className="surface p-4 transition-shadow hover:shadow-float">
              <div className="flex items-start justify-between">
                <span className="grid size-10 place-items-center rounded-xl" style={{ background: `color-mix(in oklab, ${col} 12%, transparent)`, color: col }}><I className="size-5" /></span>
                {c.delta_pct != null && (
                  <span className={cn("num inline-flex items-center gap-0.5 text-xs font-bold", c.tone === "good" ? "text-good" : c.tone === "bad" ? "text-bad" : "text-muted-foreground")}>
                    {up ? <ArrowUpRight className="size-3.5" /> : <ArrowDownRight className="size-3.5" />}
                    {fmt(Math.abs(c.delta_pct))}%
                  </span>
                )}
              </div>
              <div className="mt-3 flex items-baseline gap-1.5">
                <span className="num text-3xl font-extrabold">{fmt(c.value)}</span>
                <span className="text-sm font-semibold text-muted-foreground">{t("u_" + c.unit)}</span>
              </div>
              <div className="text-xs text-muted-foreground">{t("kpi_" + c.key) !== c.key ? t("kpi_" + c.key) : c.label}</div>
              <div className="mt-2 -mx-1"><Spark values={c.spark} color={col} /></div>
            </motion.div>
          );
        })}
      </div>

      <div className="grid gap-4 xl:grid-cols-5">
        <Panel className="xl:col-span-3" title={t("arrivals_by_dept")} sub={t("latest_day", { d: fmtDay(lang, d.latest_day) })} prov="observed" source="daily_metrics">
          <DeptArea rows={d.departments.map((x: any) => ({ name: lang === "ar" ? x.name_ar : x.name, v: x.arrivals }))} />
        </Panel>
        <Panel className="xl:col-span-2" title={t("ops_status")} prov="observed">
          <OpsStatus />
        </Panel>
      </div>


      <div className="grid gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2" title={t("c_occ")} sub={t("occ_now", { used: d.inpatient.occupied_now, total: d.inpatient.beds_total, pct: fmt(d.inpatient.occupancy_now_pct) })} prov="observed" period={d.period} source="bed_stays">
          <TrendChart
            unit="%"
            data={zip(d.occupancy.dates, { icu: d.occupancy.icu_pct, ward: d.occupancy.ward_pct, er: d.occupancy.er_pct })}
            series={[
              { key: "icu", label: t("unit_ICU"), color: "var(--chart-3)", area: true },
              { key: "ward", label: t("unit_WARD"), color: "var(--chart-1)", area: true },
              { key: "er", label: t("unit_ER"), color: "var(--chart-5)" },
            ]}
          />
        </Panel>
        <Panel title={t("bed_use") !== "use" ? t("bed_use") : t("beds")} prov="observed" source="beds">
          <BedDonut used={d.bed_use.used} available={d.bed_use.available} closed={d.bed_use.closed} />
          <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
            <Perf l={t("tile_er_wait")} v={`${fmt(d.performance.er_wait_min)} ${t("u_min")}`} />
            <Perf l={t("lwbs", { v: fmt(d.performance.lwbs_pct) })} v={`${fmt(d.performance.lwbs_pct)}%`} />
            <Perf l={t("delay_rate")} v={`${fmt(d.performance.or_delay_pct)}%`} />
            <Perf l={t("cancel_rate")} v={`${fmt(d.performance.or_cancel_pct)}%`} />
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={t("c_er")} prov="observed" period={d.period} source="daily_metrics">
          <TrendChart
            data={zip(d.er.dates, { arrivals: d.er.arrivals, wait_avg: d.er.wait_avg, wait_p90: d.er.wait_p90 })}
            series={[
              { key: "arrivals", label: t("arrivals"), color: "var(--chart-1)", area: true },
              { key: "wait_avg", label: t("wait_avg"), color: "var(--chart-4)" },
              { key: "wait_p90", label: t("wait_p90"), color: "var(--chart-5)", dashed: true },
            ]}
          />
        </Panel>
        <Panel title={t("finance")} prov="observed" period={d.period} source="financial_daily">
          <Bars
            x="date"
            unit={t("egp")}
            data={zip(d.finance.dates, { revenue: d.finance.revenue_egp, risk: d.finance.risk_egp })}
            series={[
              { key: "revenue", label: t("revenue"), color: "var(--chart-1)" },
              { key: "risk", label: t("tile_risk"), color: "var(--chart-5)" },
            ]}
            height={240}
          />
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2" title={t("departments")} sub={t("latest_day", { d: fmtDay(lang, d.latest_day) })} prov="observed" source="daily_metrics">
          <DataTable
            cols={[{ label: t("department") }, { label: t("arrivals"), n: true }, { label: t("occupancy") }, { label: t("wait_avg"), n: true }, { label: t("overtime"), n: true }, { label: t("absences"), n: true }]}
            rows={d.departments.map((x: any) => [
              <span className="font-semibold">{lang === "ar" ? x.name_ar : x.name}</span>,
              fmt(x.arrivals, 0),
              x.occupancy_pct == null ? "—" : (
                <div className="flex min-w-28 items-center gap-2"><div className="flex-1"><Bar pct={x.occupancy_pct} /></div><span className="num text-xs">{fmt(x.occupancy_pct)}%</span></div>
              ),
              fmt(x.avg_wait_min),
              fmt(x.overtime_hours),
              fmt(x.absences, 0),
            ])}
          />
        </Panel>
        <Panel title={t("fc_icu_occ")} prov="forecast" source="forecast_results">
          <ForecastChart unit="%" height={220} data={d.forecast_occupancy.ICU} />
          <div className="mt-3 flex flex-wrap gap-2">
            {d.pressure.slice(0, 4).map((p: any) => (
              <Pill key={p.id} tone={sevTone(Math.abs(p.delta_pct ?? 0) > 25 ? "medium" : "info")}>
                {t("unit_" + p.type)} <span className="num">{p.delta_pct > 0 ? "+" : ""}{fmt(p.delta_pct)}%</span>
              </Pill>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function Perf({ l, v }: { l: string; v: string }) {
  return (
    <div className="rounded-xl bg-muted/60 p-2.5">
      <div className="num font-bold">{v}</div>
      <div className="truncate text-[11px] text-muted-foreground">{l}</div>
    </div>
  );
}

function BedDonut({ used, available, closed }: { used: number; available: number; closed: number }) {
  const { t } = useApp();
  const total = used + available + closed || 1;
  const r = 52;
  const C = 2 * Math.PI * r;
  const segs = [
    { v: used, c: "var(--primary)", l: t("occupied") },
    { v: available, c: "var(--good)", l: t("free") },
    { v: closed, c: "var(--muted-foreground)", l: t("closed") },
  ];
  let off = 0;
  return (
    <div className="flex items-center gap-5">
      <svg viewBox="0 0 140 140" className="size-36 -rotate-90">
        <circle cx="70" cy="70" r={r} fill="none" stroke="var(--muted)" strokeWidth="16" />
        {segs.map((s, i) => {
          const len = (s.v / total) * C;
          const el = (
            <motion.circle key={i} cx="70" cy="70" r={r} fill="none" stroke={s.c} strokeWidth="16" strokeLinecap="butt" strokeDasharray={`${len} ${C}`} initial={{ strokeDashoffset: C }} animate={{ strokeDashoffset: -off }} transition={{ duration: 1, ease: [0.22, 1, 0.36, 1], delay: i * 0.1 }} />
          );
          off += len;
          return el;
        })}
      </svg>
      <div className="space-y-2 text-sm">
        <div className="num text-3xl font-extrabold">{Math.round((100 * used) / total)}%</div>
        {segs.map((s) => (
          <div key={s.l} className="flex items-center gap-2 text-xs">
            <span className="size-2.5 rounded-full" style={{ background: s.c }} />
            <span className="text-muted-foreground">{s.l}</span>
            <b className="num">{s.v}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

function DeptArea({ rows }: { rows: { name: string; v: number }[] }) {
  const { lang } = useApp();
  const data = lang === "ar" ? [...rows].reverse() : rows;
  return (
    <div dir="ltr" className="h-64">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 10, right: 12, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="deptfill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="name" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} interval={0} />
          <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} orientation={lang === "ar" ? "right" : "left"} />
          <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid var(--border)", background: "var(--card)", fontSize: 12 }} formatter={(v: any) => [fmt(v, 0), ""]} />
          <Area type="monotone" dataKey="v" stroke="var(--primary)" strokeWidth={2.5} fill="url(#deptfill)" dot={{ r: 4, fill: "var(--card)", stroke: "var(--primary)", strokeWidth: 2 }} activeDot={{ r: 6 }} animationDuration={900} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function OpsStatus() {
  const { t, mode } = useApp();
  const st = useHdt<any>("status", { scoped: false });
  const ql = useHdt<any>("quality", { scoped: false });
  const checks: any[] = ql.data?.checks ?? [];
  const pass = checks.filter((c) => c.status === "pass").length;
  const pct = checks.length ? Math.round((pass / checks.length) * 100) : 0;
  const llmOn = !!st.data?.llm?.configured;
  const rows = [
    { I: Server, l: t("st_server"), ok: mode === "live", v: t(mode === "live" ? "st_ok" : "st_rec") },
    { I: Cpu, l: t("st_llm"), ok: llmOn, v: t(llmOn ? "st_ok" : "st_off") },
    { I: Database, l: t("st_data"), ok: true, v: t("checks_passed", { p: pass, n: checks.length }) },
  ];
  const r = 54, C = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center gap-5 sm:flex-row">
      <ul className="w-full flex-1 space-y-2">
        {rows.map(({ I, l, ok, v }) => (
          <li key={l} className="flex items-center gap-3 rounded-xl border bg-muted/40 px-3 py-2.5">
            <I className="size-4 shrink-0 text-muted-foreground" />
            <span className="flex-1 text-sm font-semibold">{l}</span>
            <span className={cn("rounded-full px-2.5 py-0.5 text-[11px] font-bold", ok ? "bg-good/12 text-good" : "bg-muted text-muted-foreground")}>{v}</span>
          </li>
        ))}
      </ul>
      <div className="relative size-36 shrink-0">
        <svg viewBox="0 0 140 140" className="size-full -rotate-90">
          <circle cx="70" cy="70" r={r} fill="none" stroke="var(--muted)" strokeWidth="12" />
          <motion.circle cx="70" cy="70" r={r} fill="none" stroke="var(--primary)" strokeWidth="12" strokeLinecap="round" strokeDasharray={C} initial={{ strokeDashoffset: C }} animate={{ strokeDashoffset: C * (1 - pct / 100) }} transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }} />
        </svg>
        <div className="absolute inset-0 grid place-content-center text-center">
          <span className="num text-3xl font-extrabold">{pct}%</span>
          <span className="text-[11px] text-muted-foreground">{t("readiness")}</span>
        </div>
      </div>
    </div>
  );
}
