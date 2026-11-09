import { createFileRoute, Link } from "@tanstack/react-router";
import { AnimatePresence, motion } from "framer-motion";
import { lazy, Suspense, useMemo, useState } from "react";
import { ArrowUpRight, BedDouble, Clock, Layers, Maximize2, RotateCcw, Stethoscope, UserRound, Users, X } from "lucide-react";
import { useApp, useHdt } from "@/lib/app-state";
import { fmt, fmtDay, fmtWhen } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { FLOORS, deptLoad, layoutTwin, type TwinMap } from "@/components/twin/layout";
import type { Selection } from "@/components/twin/scene";
import { Bar, ErrorBox, Pill, ProvChip, sevTone } from "@/components/hdt/kit";

const TwinScene = lazy(() => import("@/components/twin/scene"));

export const Route = createFileRoute("/")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "3D Hospital Digital Twin · التوأم الرقمي للمستشفى" },
      { name: "description", content: "Navigate every floor, department, room and bed of the hospital in 3D, driven by the operational data pack." },
      { property: "og:title", content: "3D Hospital Digital Twin" },
      { property: "og:description", content: "Interactive multi-floor 3D twin of hospital beds, operating rooms and departments." },
    ],
  }),
  component: TwinPage,
});

const PAGE_FOR: Record<string, string> = { ER: "/capacity", ICU: "/capacity", WARD: "/capacity", OR: "/or", CLINIC: "/overview", IMAGING: "/overview", LAB: "/overview" };

function TwinPage() {
  const { t, lang, asOf } = useApp();
  const twin = useHdt<TwinMap>("twin");
  const alerts = useHdt<{ alerts: any[]; needs_attention: number }>("alerts");
  const layout = useMemo(() => layoutTwin(twin.data), [twin.data]);
  const [sel, setSel] = useState<Selection>({ floor: null, dept: null, room: null, bed: null });
  const [exploded, setExploded] = useState(false);
  const [resetKey, setResetKey] = useState(0);

  const onSelect = (s: Partial<Selection>) =>
    setSel((p) => {
      const n = { ...p, ...s };
      if (n.dept) n.floor = layout.find((d) => d.dept.id === n.dept)?.floor ?? n.floor;
      return n;
    });

  const dept = layout.find((d) => d.dept.id === sel.dept);
  const room = dept?.rooms.find((r) => r.key === sel.room);
  const bed = room?.beds.find((b) => b.id === sel.bed);
  const name = (d: { name: string; name_ar: string }) => (lang === "ar" ? d.name_ar : d.name);

  const totals = useMemo(() => {
    const ds = twin.data?.departments ?? [];
    const beds = ds.reduce((a, d) => a + (d.beds_total ?? 0), 0);
    const occ = ds.reduce((a, d) => a + (d.occupied ?? 0), 0);
    const staff = ds.reduce((a, d) => a + (d.nurses ?? 0) + (d.doctors ?? 0), 0);
    return { beds, occ, staff };
  }, [twin.data]);

  if (twin.error) return <ErrorBox error={twin.error} retry={() => twin.refetch()} />;

  return (
    <div className="-m-4 md:-m-6 lg:-m-8">
      <div className="bg-hero relative h-[calc(100svh-57px)] min-h-[560px] overflow-hidden">
        {layout.length > 0 ? (
          <Suspense fallback={<SceneLoading />}>
            <TwinScene layout={layout} sel={sel} onSelect={onSelect} exploded={exploded} lang={lang} labels={{ occupied: t("occupied"), free: t("free"), beds: t("beds") }} resetKey={resetKey} />
          </Suspense>
        ) : (
          <SceneLoading />
        )}

        {/* top-left: title & totals */}
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="pointer-events-none absolute inset-x-3 top-3 flex flex-wrap items-start gap-2 md:inset-x-5 md:top-5">
          <div className="glass pointer-events-auto rounded-2xl px-4 py-3">
            <div className="flex items-center gap-2">
              <ProvChip kind="observed" />
              <span className="text-[11px] text-muted-foreground">{fmtWhen(lang, asOf)}</span>
            </div>
            <h1 className="mt-1 text-lg font-extrabold md:text-xl">{t("nav_twin")}</h1>
            <div className="mt-2 flex gap-4 text-xs">
              <Kpi icon={BedDouble} v={`${totals.occ}/${totals.beds}`} l={t("beds_occupied")} />
              <Kpi icon={Users} v={String(totals.staff)} l={t("on_shift")} />
              <Link to="/alerts" className="pointer-events-auto">
                <Kpi icon={Clock} v={String(alerts.data?.needs_attention ?? "—")} l={t("nav_alerts")} tone={alerts.data?.needs_attention ? "bad" : undefined} />
              </Link>
            </div>
          </div>
        </motion.div>

        {/* floor selector */}
        <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 }} className="glass absolute end-3 top-1/2 flex -translate-y-1/2 flex-col gap-1 rounded-2xl p-1.5 md:end-5">
          <span className="px-1 pb-1 text-center text-[10px] font-bold text-muted-foreground uppercase"><Layers className="mx-auto size-4" /></span>
          {[...FLOORS].reverse().map((f) => (
            <button
              key={f}
              onClick={() => setSel({ floor: sel.floor === f ? null : f, dept: null, room: null, bed: null })}
              title={t("floor_" + f)}
              className={cn("num relative grid size-10 place-items-center rounded-xl text-sm font-bold transition-colors", sel.floor === f ? "text-primary-foreground" : "hover:bg-muted")}
            >
              {sel.floor === f && <motion.span layoutId="floor-pill" className="bg-brand absolute inset-0 rounded-xl" />}
              <span className="relative">{t("floor_short_" + f)}</span>
            </button>
          ))}
          <div className="my-1 h-px bg-border" />
          <IconBtn label={t("explode")} active={exploded} onClick={() => setExploded((e) => !e)}><Maximize2 className="size-4" /></IconBtn>
          <IconBtn label={t("reset_view")} onClick={() => { setSel({ floor: null, dept: null, room: null, bed: null }); setExploded(false); setResetKey((k) => k + 1); }}><RotateCcw className="size-4" /></IconBtn>
        </motion.div>

        {/* bottom: floor directory */}
        <div className="absolute inset-x-3 bottom-3 md:inset-x-5 md:bottom-5 md:end-auto md:max-w-[min(860px,calc(100%-460px))]">
          <div className="glass flex gap-2 overflow-x-auto rounded-2xl p-2">
            {layout
              .filter((d) => sel.floor == null || d.floor === sel.floor)
              .map((d) => {
                const load = deptLoad(d.dept);
                return (
                  <button
                    key={d.dept.id}
                    onClick={() => onSelect({ dept: d.dept.id, room: null, bed: null })}
                    className={cn("min-w-40 shrink-0 rounded-xl px-3 py-2 text-start transition-all hover:bg-muted", sel.dept === d.dept.id && "bg-primary-soft ring-1 ring-primary/40")}
                  >
                    <div className="flex items-center justify-between gap-2 text-[10px] font-semibold text-muted-foreground">
                      {t("floor_short_" + d.floor)} · {t("unit_" + d.dept.type)}
                    </div>
                    <div className="truncate text-sm font-bold">{name(d.dept)}</div>
                    {load != null ? (
                      <div className="mt-1.5 flex items-center gap-2">
                        <div className="flex-1"><Bar pct={load * 100} /></div>
                        <span className="num text-[11px]">{Math.round(load * 100)}%</span>
                      </div>
                    ) : (
                      <div className="num mt-1 text-[11px] text-muted-foreground">{fmt(d.dept.arrivals, 0)} {t("arrivals")} · {fmt(d.dept.avg_wait_min, 0)} {t("u_min")}</div>
                    )}
                  </button>
                );
              })}
          </div>
        </div>

        {/* detail panel */}
        <AnimatePresence>
          {dept && (
            <motion.aside
              key="panel"
              initial={{ opacity: 0, x: lang === "ar" ? -24 : 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: lang === "ar" ? -24 : 24 }}
              transition={{ type: "spring", damping: 28, stiffness: 260 }}
              className="glass absolute z-50 inset-x-3 bottom-24 max-h-[55%] overflow-y-auto rounded-2xl p-5 md:inset-x-auto md:end-20 md:top-5 md:bottom-5 md:max-h-none md:w-[380px]"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[11px] font-semibold text-muted-foreground">{t("floor_" + dept.floor)}</div>
                  <h2 className="text-lg font-extrabold">{name(dept.dept)}</h2>
                  <div className="text-[11px] text-muted-foreground">{t("latest_day", { d: fmtDay(lang, dept.dept.day) })}</div>
                </div>
                <button onClick={() => setSel((s) => ({ ...s, dept: null, room: null, bed: null }))} className="rounded-lg p-1.5 hover:bg-muted" aria-label={t("close")}><X className="size-4" /></button>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2">
                {dept.dept.beds_total ? <Mini l={t("beds_occupied")} v={`${dept.dept.occupied}/${dept.dept.beds_total}`} /> : null}
                {dept.dept.nurses != null && <Mini l={t("nurses")} v={fmt(dept.dept.nurses, 0)} />}
                {dept.dept.doctors != null && <Mini l={t("doctors")} v={fmt(dept.dept.doctors, 0)} />}
                {dept.dept.arrivals != null && <Mini l={t("arrivals")} v={fmt(dept.dept.arrivals, 0)} />}
                {dept.dept.avg_wait_min != null && dept.dept.avg_wait_min > 0 && <Mini l={t("avg_wait")} v={`${fmt(dept.dept.avg_wait_min, 0)} ${t("u_min")}`} />}
                {dept.dept.beds_total && dept.dept.nurses ? <Mini l={t("beds_per_nurse")} v={fmt((dept.dept.occupied ?? 0) / dept.dept.nurses, 1)} /> : null}
              </div>

              <AnimatePresence mode="wait">
                {bed ? (
                  <motion.div key={bed.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-4 rounded-xl border bg-card p-4">
                    <div className="flex items-center gap-3">
                      <div className={cn("grid size-10 place-items-center rounded-xl", bed.occupied ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>
                        {bed.occupied ? <UserRound className="size-5" /> : <BedDouble className="size-5" />}
                      </div>
                      <div>
                        <div className="num text-sm font-bold">{bed.id}</div>
                        <div className="text-xs text-muted-foreground">{room?.name}</div>
                      </div>
                      <Pill tone={bed.occupied ? "primary" : "good"} className="ms-auto">{t(bed.occupied ? "occupied" : "free")}</Pill>
                    </div>
                    <p className="mt-2 text-[11px] text-muted-foreground">{t("source")}: beds, bed_stays · {fmtWhen(lang, asOf)}</p>
                  </motion.div>
                ) : null}
              </AnimatePresence>

              <h3 className="mt-5 mb-2 text-xs font-bold text-muted-foreground">{t("rooms")}</h3>
              <ul className="space-y-1.5">
                {dept.rooms.map((r) => {
                  const occ = r.beds.filter((b) => b.occupied).length;
                  const util = r.or ? (100 * r.or.booked_min_on_day) / r.or.capacity_min : null;
                  return (
                    <li key={r.key}>
                      <button onClick={() => onSelect({ room: r.key, bed: null })} className={cn("w-full rounded-xl border px-3 py-2 text-start transition-colors hover:bg-muted", sel.room === r.key && "border-primary bg-primary-soft")}>
                        <div className="flex items-center justify-between text-sm font-semibold">
                          <span className="truncate">{r.name}</span>
                          {r.beds.length > 0 && <span className="num text-xs">{occ}/{r.beds.length}</span>}
                          {util != null && <span className="num text-xs">{Math.round(util)}%</span>}
                        </div>
                        {r.beds.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {r.beds.map((b) => (
                              <span
                                key={b.id}
                                role="button"
                                tabIndex={0}
                                onClick={(e) => { e.stopPropagation(); onSelect({ room: r.key, bed: b.id }); }}
                                title={b.id}
                                className={cn("size-3.5 rounded-[4px] transition-transform hover:scale-125", b.occupied ? "bg-primary" : "bg-good/30", sel.bed === b.id && "ring-2 ring-foreground ring-offset-1")}
                              />
                            ))}
                          </div>
                        )}
                        {r.or && (
                          <div className="mt-1.5">
                            <Bar pct={util ?? 0} />
                            <div className="num mt-1 text-[11px] text-muted-foreground">{fmt(r.or.booked_min_on_day, 0)} / {fmt(r.or.capacity_min, 0)} {t("u_min")}</div>
                          </div>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>

              {alerts.data?.alerts?.filter((a) => JSON.stringify(a.evidence ?? {}).includes(dept.dept.type)).slice(0, 3).map((a) => (
                <div key={a.id} className="mt-3 rounded-xl border border-bad/20 bg-bad/5 p-3 text-xs">
                  <Pill tone={sevTone(a.severity)}>{t("sev_" + a.severity)}</Pill>
                  <p className="mt-1 font-semibold">{lang === "ar" ? a.title_ar || a.title : a.title}</p>
                </div>
              ))}

              <Link to={PAGE_FOR[dept.dept.type] ?? "/overview"} className="bg-brand mt-5 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm font-bold text-primary-foreground transition-transform hover:scale-[1.01]">
                {dept.dept.type === "OR" ? <Stethoscope className="size-4" /> : <BedDouble className="size-4" />}
                {t("view_details")} <ArrowUpRight className="size-4 rtl:-scale-x-100" />
              </Link>
              <p className="mt-3 text-[10px] leading-relaxed text-muted-foreground">{t("layout_note")}</p>
            </motion.aside>
          )}
        </AnimatePresence>

        {!dept && (
          <div className="pointer-events-none absolute start-1/2 top-24 hidden -translate-x-1/2 rtl:translate-x-1/2 md:block">
            <div className="glass rounded-full px-4 py-1.5 text-xs text-muted-foreground">{sel.floor != null ? t("floor_" + sel.floor) : t("select_hint")}</div>
          </div>
        )}

        {/* legend */}
        <div className="glass absolute end-3 bottom-3 hidden gap-3 rounded-xl px-3 py-2 text-[11px] md:end-5 md:bottom-5 lg:flex">
          <Leg c="bg-primary" l={t("occupied")} />
          <Leg c="bg-card border" l={t("free")} />
          <Leg c="bg-good" l="< 75%" />
          <Leg c="bg-warn" l="75–90%" />
          <Leg c="bg-bad" l="≥ 90%" />
        </div>
      </div>
    </div>
  );
}

function SceneLoading() {
  const { t } = useApp();
  return (
    <div className="absolute inset-0 grid place-items-center">
      <div className="flex flex-col items-center gap-3 text-sm text-muted-foreground">
        <div className="size-10 animate-spin rounded-full border-2 border-primary/20 border-t-primary" />
        {t("loading")}
      </div>
    </div>
  );
}
function Kpi({ icon: I, v, l, tone }: { icon: typeof BedDouble; v: string; l: string; tone?: "bad" }) {
  return (
    <div className="flex items-center gap-2">
      <I className={cn("size-4", tone === "bad" ? "text-bad" : "text-primary")} />
      <div>
        <div className="num font-bold">{v}</div>
        <div className="text-[10px] text-muted-foreground">{l}</div>
      </div>
    </div>
  );
}
function Mini({ l, v }: { l: string; v: string }) {
  return (
    <div className="rounded-xl bg-muted/70 px-3 py-2">
      <div className="num text-base font-bold">{v}</div>
      <div className="text-[11px] text-muted-foreground">{l}</div>
    </div>
  );
}
function IconBtn({ children, label, onClick, active }: { children: React.ReactNode; label: string; onClick: () => void; active?: boolean }) {
  return (
    <button onClick={onClick} title={label} aria-label={label} className={cn("grid size-10 place-items-center rounded-xl transition-colors hover:bg-muted", active && "bg-primary-soft text-primary")}>
      {children}
    </button>
  );
}
function Leg({ c, l }: { c: string; l: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn("size-2.5 rounded-sm", c)} />
      {l}
    </span>
  );
}
