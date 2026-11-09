import { createFileRoute } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { Stethoscope, UserRound } from "lucide-react";
import { useApp, useHdt } from "@/lib/app-state";
import { fmt } from "@/lib/i18n";
import { Bar, DataTable, ErrorBox, PageHead, PageSkeleton, Panel } from "@/components/hdt/kit";
import { Bars, TrendChart, zip } from "@/components/hdt/charts";

export const Route = createFileRoute("/staff")({
  head: () => ({
    meta: [
      { title: "Staff and nursing · Hospital Digital Twin" },
      { name: "description", content: "Who is on shift, workload distribution and overtime cost." },
      { property: "og:title", content: "Hospital staffing and nursing" },
      { property: "og:description", content: "Shift coverage, absences, workload and overtime by department." },
    ],
  }),
  component: Staff,
});

function Staff() {
  const { t } = useApp();
  const q = useHdt<any>("staff");
  if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;
  if (!q.data) return <PageSkeleton />;
  const s = q.data;
  const units = [...new Set((s.on_shift_now as any[]).map((x) => x.unit))];
  const get = (u: string, k: string) => s.on_shift_now.find((x: any) => x.unit === u && x.kind === k)?.count ?? 0;
  const otCost = (s.overtime_cost_egp.values as number[]).reduce((a, b) => a + b, 0);
  return (
    <div className="space-y-5">
      <PageHead title={t("nav_staff")} sub={t("staff_sub")} />
      <Panel title={t("on_shift")} prov="observed" source="staff_shifts">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {units.map((u, i) => (
            <motion.div key={u} initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.05 }} className="rounded-xl bg-muted/60 p-3">
              <b className="text-sm">{t("unit_" + u)}</b>
              <div className="mt-2 flex gap-4">
                <span className="flex items-center gap-1.5"><UserRound className="size-4 text-primary" /><b className="num text-lg">{get(u, "nurses")}</b><span className="text-[11px] text-muted-foreground">{t("nurses")}</span></span>
                <span className="flex items-center gap-1.5"><Stethoscope className="size-4 text-forecast" /><b className="num text-lg">{get(u, "doctors")}</b></span>
              </div>
              {s.observed_beds_per_nurse[u] != null && <div className="num mt-1 text-[11px] text-muted-foreground">{t("beds_per_nurse")}: {fmt(s.observed_beds_per_nurse[u])}</div>}
            </motion.div>
          ))}
        </div>
      </Panel>
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={t("shifts_day")} prov="observed" period={s.history_period} source="staff_shifts">
          <Bars x="date" stacked data={zip(s.shifts_per_day.dates, { shifts: s.shifts_per_day.values, absent: s.absent_shifts_per_day.values })} series={[{ key: "shifts", label: t("shifts"), color: "var(--chart-1)" }, { key: "absent", label: t("absent"), color: "var(--chart-5)" }]} />
        </Panel>
        <Panel title={t("overtime_title")} sub={t("overtime_cost", { v: fmt(otCost, 0) })} prov="observed" period={s.history_period} source="financial_daily">
          <TrendChart data={zip(s.overtime_hours.dates, { h: s.overtime_hours.values })} series={[{ key: "h", label: t("overtime_h"), color: "var(--chart-4)", area: true }]} unit={t("u_hours")} />
        </Panel>
        <Panel title={t("workload")} sub={t("workload_sub")} prov="observed" source="staff_assignments">
          <Bars x="b" data={s.workload_distribution.buckets.map((b: string, i: number) => ({ b: b + "%", v: s.workload_distribution.staff[i] }))} series={[{ key: "v", label: t("staff_count"), color: "var(--chart-2)" }]} />
        </Panel>
        <Panel title={t("workload_unit")} prov="observed" source="staff_assignments">
          <DataTable
            cols={[{ label: t("department") }, { label: t("mean_load") }, { label: t("staff_count"), n: true }, { label: "≥ 90%", n: true }]}
            rows={s.workload_by_unit.map((w: any) => [
              <b>{t("unit_" + w.unit)}</b>,
              <div className="flex min-w-32 items-center gap-2"><div className="flex-1"><Bar pct={w.mean_pct} /></div><span className="num text-xs">{fmt(w.mean_pct)}%</span></div>,
              w.staff,
              w.at_or_above_90_pct,
            ])}
          />
        </Panel>
      </div>
    </div>
  );
}
