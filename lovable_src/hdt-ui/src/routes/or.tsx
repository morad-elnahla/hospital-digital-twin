import { createFileRoute } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { useApp, useHdt } from "@/lib/app-state";
import { fmt, fmtDay } from "@/lib/i18n";
import { Bar, DataTable, Empty, ErrorBox, PageHead, PageSkeleton, Panel, Stat } from "@/components/hdt/kit";
import { TrendChart, zip } from "@/components/hdt/charts";

export const Route = createFileRoute("/or")({
  head: () => ({
    meta: [
      { title: "Operating rooms · Hospital Digital Twin" },
      { name: "description", content: "Operating room utilisation, delays, cancellations and booked load." },
      { property: "og:title", content: "Operating rooms" },
      { property: "og:description", content: "Room-by-room planned use and upcoming surgical load." },
    ],
  }),
  component: OR,
});

const ST_COLOR: Record<string, string> = { COMPLETED: "var(--good)", SCHEDULED: "var(--observed)", DELAYED: "var(--warn)", CANCELLED: "var(--bad)" };

function OR() {
  const { t, lang } = useApp();
  const q = useHdt<any>("or");
  if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;
  if (!q.data) return <PageSkeleton />;
  const o = q.data;
  const total = Object.values(o.status_counts as Record<string, number>).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="space-y-5">
      <PageHead title={t("nav_or")} sub={t("or_sub")} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={t("surgeries_window")} value={o.surgeries_in_window} d={0} />
        <Stat label={t("delay_rate")} value={o.delay_rate_pct} unit="%" tone="warn" />
        <Stat label={t("cancel_rate")} value={o.cancel_rate_pct} unit="%" tone="bad" />
        <Stat label={t("cancelled_margin")} value={o.cancelled_expected_margin_egp} unit={t("egp")} d={0} />
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2" title={t("or_rooms")} sub={t("or_rooms_sub")} prov="observed" source={o.sources}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {o.by_room.map((r: any, i: number) => (
              <motion.div key={r.or_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="rounded-xl border p-3">
                <div className="flex items-center justify-between"><b className="text-sm">{r.name}</b><span className="text-[10px] font-semibold text-muted-foreground">{r.specialty}</span></div>
                <div className="num my-2 text-2xl font-extrabold">{fmt(r.planned_utilisation_pct)}%</div>
                <Bar pct={r.planned_utilisation_pct} />
              </motion.div>
            ))}
          </div>
        </Panel>
        <Panel title={t("or_status")} prov="observed" period={o.history_period}>
          <div className="flex h-4 overflow-hidden rounded-full">
            {Object.entries(o.status_counts as Record<string, number>).map(([k, v]) => (
              <motion.div key={k} initial={{ width: 0 }} animate={{ width: `${(100 * v) / total}%` }} transition={{ duration: 0.9 }} style={{ background: ST_COLOR[k] }} />
            ))}
          </div>
          <div className="mt-4 space-y-2">
            {Object.entries(o.status_counts as Record<string, number>).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2 text-sm">
                <span className="size-2.5 rounded-full" style={{ background: ST_COLOR[k] }} />
                <span className="flex-1">{t("st_" + k)}</span>
                <b className="num">{v}</b>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={t("or_util")} prov="observed" period={o.history_period}>
          <TrendChart unit="%" data={zip(o.dates, { u: o.utilisation_history_pct })} series={[{ key: "u", label: t("or_util"), color: "var(--chart-3)", area: true }]} />
        </Panel>
        <Panel title={t("or_upcoming")} sub={t("or_upcoming_sub")} prov="observed">
          {o.upcoming?.dates?.length ? (
            <DataTable
              cols={[{ label: t("date") }, { label: t("booked_load") }, { label: t("bookings"), n: true }, { label: t("movable"), n: true }]}
              rows={o.upcoming.dates.map((d: string, i: number) => [
                fmtDay(lang, d),
                <div className="flex min-w-32 items-center gap-2"><div className="flex-1"><Bar pct={o.upcoming.load_pct[i]} /></div><span className="num text-xs">{fmt(o.upcoming.load_pct[i])}%</span></div>,
                o.upcoming.bookings[i],
                o.upcoming.movable_elective[i],
              ])}
            />
          ) : (
            <Empty>{t("no_upcoming")}</Empty>
          )}
        </Panel>
      </div>
    </div>
  );
}
