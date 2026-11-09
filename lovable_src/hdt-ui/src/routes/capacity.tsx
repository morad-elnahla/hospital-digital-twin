import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { motion } from "framer-motion";
import { useApp, useHdt } from "@/lib/app-state";
import { fmt, fmtWhen } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Bar, ErrorBox, PageHead, PageSkeleton, Panel, Stat } from "@/components/hdt/kit";
import { Bars, ForecastChart, TrendChart } from "@/components/hdt/charts";

export const Route = createFileRoute("/capacity")({
  head: () => ({
    meta: [
      { title: "Beds, ICU and ER · Hospital Digital Twin" },
      { name: "description", content: "Bed occupancy, nurse coverage and ER patient flow with forecasts." },
      { property: "og:title", content: "Beds, ICU and ER capacity" },
      { property: "og:description", content: "Occupancy history, forecast bands and emergency department flow." },
    ],
  }),
  component: Capacity,
});

function Capacity() {
  const { t, lang, asOf } = useApp();
  const q = useHdt<any>("capacity");
  const [unit, setUnit] = useState("ICU");
  if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;
  if (!q.data) return <PageSkeleton />;
  const units = q.data.units as Record<string, any>;
  const u = units[unit];
  const hist = q.data.history_period;
  const histDates: string[] = [];
  const d0 = new Date(hist.from + "T00:00:00Z");
  for (let i = 0; i < u.occupancy_history_pct.length; i++) {
    const d = new Date(d0);
    d.setUTCDate(d.getUTCDate() + i);
    histDates.push(d.toISOString().slice(0, 10));
  }
  const fcRows = [
    ...histDates.map((date, i) => ({ date, observed: u.occupancy_history_pct[i] })),
    ...u.forecast_pct.map((f: any) => ({ date: f.date, predicted: f.predicted, lower: f.lower, upper: f.upper, actual: f.actual })),
  ];
  const er = units.ER.flow;
  return (
    <div className="space-y-5">
      <PageHead title={t("nav_capacity")} sub={t("capacity_sub")} />
      <div className="grid gap-3 md:grid-cols-3">
        {Object.entries(units).map(([k, v], i) => (
          <motion.button
            key={k}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            onClick={() => setUnit(k)}
            className={cn("surface p-4 text-start transition-all hover:shadow-float", unit === k && "ring-2 ring-primary")}
          >
            <div className="flex items-center justify-between">
              <b>{t("unit_" + k)}</b>
              <span className="text-[11px] text-muted-foreground">{t("at_moment", { when: fmtWhen(lang, asOf) })}</span>
            </div>
            <div className="num mt-2 text-3xl font-extrabold">
              {v.occupied_now}<span className="text-base text-muted-foreground">/{v.beds_total}</span>
            </div>
            <div className="mt-2"><Bar pct={v.occupancy_now_pct} /></div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Stat label={t("nurses_on_shift")} value={v.nurses_on_shift} d={0} />
              <Stat label={t("beds_per_nurse")} value={v.beds_occupied_per_nurse} />
            </div>
          </motion.button>
        ))}
      </div>

      <Panel title={t("occ_forecast", { u: t("unit_" + unit) })} sub={t("fc_sub")} prov="forecast" source={q.data.sources} period={hist}>
        <ForecastChart data={fcRows} unit="%" height={280} marker={asOf.slice(0, 10)} />
        <p className="mt-2 text-xs text-muted-foreground">
          {t("fc_method")} · {u.backtest?.days ? t("backtest_line", { w: fmt(u.backtest.wape, 2), m: fmt(u.backtest.mape, 2), n: u.backtest.days }) : ""}
        </p>
      </Panel>

      <h2 className="pt-2 text-lg font-extrabold">{t("er_flow")}</h2>
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={t("er_by_hour")} sub={t("er_by_hour_sub")} prov="observed" period={er.window} source="er_events">
          <Bars x="h" data={er.arrivals_by_hour.map((v: number, h: number) => ({ h: String(h).padStart(2, "0"), v }))} series={[{ key: "v", label: t("arrivals"), color: "var(--chart-1)" }]} />
        </Panel>
        <Panel title={t("er_wait")} prov="observed" period={hist} source="daily_metrics">
          <TrendChart
            unit={t("u_min")}
            data={histDates.map((date, i) => ({ date, avg: er.wait_avg_history[i], p90: er.wait_p90_history[i], q: er.queue_peak_history[i] }))}
            series={[
              { key: "avg", label: t("wait_avg"), color: "var(--chart-4)", area: true },
              { key: "p90", label: t("wait_p90"), color: "var(--chart-5)", dashed: true },
            ]}
          />
        </Panel>
        <Panel title={t("er_outcomes")} sub={t("lwbs", { v: fmt(er.left_without_being_seen_pct) })} prov="observed" source="visits">
          <div className="space-y-3">
            {Object.entries(er.dispositions as Record<string, number>).map(([k, v]) => (
              <div key={k}>
                <div className="mb-1 flex justify-between text-sm"><span>{t("disp_" + k)}</span><b className="num">{v}</b></div>
                <Bar pct={(100 * v) / er.visits_in_window} tone={k === "LEFT_WITHOUT_BEING_SEEN" ? "var(--bad)" : undefined} />
              </div>
            ))}
          </div>
        </Panel>
        <Panel title={t("er_acuity")} sub={t("acuity_note")} prov="observed" source="visits">
          <Bars x="k" data={Object.entries(er.acuity).map(([k, v]) => ({ k: `${t("acuity")} ${k}`, v }))} series={[{ key: "v", label: t("er_acuity"), color: "var(--chart-2)" }]} />
        </Panel>
      </div>
    </div>
  );
}
