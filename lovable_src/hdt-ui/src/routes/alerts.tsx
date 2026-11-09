import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { AlertOctagon, AlertTriangle, ArrowUpRight, Eye, Info } from "lucide-react";
import { useApp, useHdt } from "@/lib/app-state";
import { cn } from "@/lib/utils";
import { Empty, ErrorBox, PageHead, PageSkeleton, Pill, sevTone } from "@/components/hdt/kit";

export const Route = createFileRoute("/alerts")({
  head: () => ({
    meta: [
      { title: "Alerts · Hospital Digital Twin" },
      { name: "description", content: "Ranked operational alerts with their evidence and source." },
      { property: "og:title", content: "Hospital alerts" },
      { property: "og:description", content: "Every capacity, data and system alert ranked by severity." },
    ],
  }),
  component: Alerts,
});

const PAGE: Record<string, string> = { agents: "/simulator", decisions: "/decisions", system: "/system", staff: "/staff", simulator: "/simulator" };
const SEV_ICON = { critical: AlertOctagon, high: AlertTriangle, medium: Eye, info: Info } as Record<string, typeof Info>;

function Alerts() {
  const { t, lang } = useApp();
  const q = useHdt<any>("alerts");
  if (q.error) return <ErrorBox error={q.error} retry={() => q.refetch()} />;
  if (!q.data) return <PageSkeleton />;
  const list = q.data.alerts as any[];
  return (
    <div>
      <PageHead title={t("nav_alerts")} sub={t("alerts_sub")} right={<Pill tone={q.data.needs_attention ? "bad" : "good"}>{t("n_items", { n: list.length })}</Pill>} />
      {list.length === 0 && <Empty>{t("nothing_urgent")}</Empty>}
      <div className="space-y-3">
        {list.map((a, i) => {
          const I = SEV_ICON[a.severity] ?? Info;
          return (
            <motion.div key={a.id} initial={{ opacity: 0, x: lang === "ar" ? 12 : -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }} className="surface flex gap-4 p-4">
              <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl", sevTone(a.severity) === "bad" ? "bg-bad/10 text-bad" : sevTone(a.severity) === "warn" ? "bg-warn/15 text-warn" : "bg-muted text-muted-foreground")}>
                <I className="size-5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Pill tone={sevTone(a.severity)}>{t("sev_" + a.severity)}</Pill>
                  <Pill>{t("src_" + a.source)}</Pill>
                </div>
                <h3 className="mt-1.5 font-bold">{lang === "ar" ? a.title_ar || a.title : a.title}</h3>
                <p className="mt-0.5 text-sm text-muted-foreground">{lang === "ar" ? a.detail_ar || a.detail : a.detail}</p>
              </div>
              <Link to={PAGE[a.page] ?? "/system"} className="self-center rounded-lg border p-2 hover:bg-muted" aria-label={t("open_page")}>
                <ArrowUpRight className="size-4 rtl:-scale-x-100" />
              </Link>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
