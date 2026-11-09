import { createFileRoute } from "@tanstack/react-router";
import { AlertTriangle } from "lucide-react";
import { useApp, useHdt } from "@/lib/app-state";
import { fmt } from "@/lib/i18n";
import { ErrorBox, PageHead, PageSkeleton, Panel } from "@/components/hdt/kit";
import { ForecastChart } from "@/components/hdt/charts";

export const Route = createFileRoute("/forecasts")({
  head: () => ({
    meta: [
      { title: "Forecasts · Hospital Digital Twin" },
      { name: "description", content: "Baseline forecasts for ER, ICU, ward and OR checked against what happened." },
      { property: "og:title", content: "Hospital demand forecasts" },
      { property: "og:description", content: "Five baseline forecasts with uncertainty bands and backtests." },
    ],
  }),
  component: Forecasts,
});

const KEY: Record<string, string> = { er_arrivals: "fc_er_arrivals", avg_er_wait_minutes: "fc_er_wait", icu_occupancy: "fc_icu_occ", ward_occupancy: "fc_ward_occ", or_utilization: "fc_or_util" };

function Forecasts() {
  const { t, asOf } = useApp();
  const q = useHdt<any>("forecasts");
  if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;
  if (!q.data) return <PageSkeleton />;
  return (
    <div className="space-y-5">
      <PageHead title={t("nav_forecast")} sub={t("forecast_sub")} />
      <div className="flex items-start gap-3 rounded-xl border border-warn/30 bg-warn/10 p-3 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" /> {t("fc_warning")}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        {q.data.series.map((s: any, i: number) => {
          const rows = [
            ...s.history.dates.map((date: string, j: number) => ({ date, observed: s.history.values[j] })),
            ...s.forecast.map((f: any) => ({ date: f.date, predicted: f.predicted, lower: f.lower, upper: f.upper, actual: f.actual })),
          ];
          return (
            <Panel key={s.key} delay={i * 0.05} title={KEY[s.key] ? t(KEY[s.key]) : s.title} sub={t("u_" + s.unit)} prov="forecast" source={s.table}>
              <ForecastChart data={rows} unit={t("u_" + s.unit)} marker={asOf.slice(0, 10)} />
              <p className="mt-2 text-xs text-muted-foreground">
                {s.backtest?.days ? t("backtest_line", { w: fmt(s.backtest.wape, 2), m: fmt(s.backtest.mape, 2), n: s.backtest.days }) : t("backtest_days", { n: 0 })}
              </p>
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
