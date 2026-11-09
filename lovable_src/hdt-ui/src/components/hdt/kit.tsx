import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { useApp } from "@/lib/app-state";
import { cn } from "@/lib/utils";
import { fmt, fmtDay } from "@/lib/i18n";

export const fade = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] },
} as const;

export function PageHead({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <motion.div {...fade} className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground md:text-3xl">{title}</h1>
        {sub && <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{sub}</p>}
      </div>
      {right}
    </motion.div>
  );
}

const PROV_CLS = {
  observed: "bg-observed/10 text-observed",
  forecast: "bg-forecast/10 text-forecast",
  simulation: "bg-simulation/15 text-[color-mix(in_oklab,var(--simulation),black_30%)]",
  agent: "bg-agent/10 text-agent",
} as const;
export type Prov = keyof typeof PROV_CLS;

export function ProvChip({ kind }: { kind: Prov }) {
  const { t } = useApp();
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold", PROV_CLS[kind])}>
      <span className="size-1.5 rounded-full bg-current" />
      {t("prov_" + kind)}
    </span>
  );
}

const TONE = {
  good: "bg-good/12 text-good",
  warn: "bg-warn/15 text-[color-mix(in_oklab,var(--warn),black_35%)]",
  bad: "bg-bad/12 text-bad",
  info: "bg-muted text-muted-foreground",
  primary: "bg-primary-soft text-primary",
} as const;
export type Tone = keyof typeof TONE;
export function Pill({ tone = "info", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold", TONE[tone], className)}>
      {children}
    </span>
  );
}
export const sevTone = (s: string): Tone =>
  s === "critical" || s === "high" ? "bad" : s === "medium" ? "warn" : "info";

export function Panel({
  title,
  sub,
  prov,
  right,
  source,
  period,
  className,
  children,
  delay = 0,
}: {
  title?: string;
  sub?: string;
  prov?: Prov;
  right?: ReactNode;
  source?: string | string[];
  period?: { from: string; to: string };
  className?: string;
  children: ReactNode;
  delay?: number;
}) {
  const { t, lang } = useApp();
  return (
    <motion.section
      {...fade}
      transition={{ ...fade.transition, delay }}
      className={cn("surface flex flex-col p-5", className)}
    >
      {(title || prov || right) && (
        <header className="mb-4 flex items-start gap-3">
          <div className="min-w-0 flex-1">
            {title && <h3 className="text-[15px] font-bold text-foreground">{title}</h3>}
            {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
          </div>
          {prov && <ProvChip kind={prov} />}
          {right}
        </header>
      )}
      <div className="min-w-0 flex-1">{children}</div>
      {(source || period) && (
        <footer className="mt-4 flex flex-wrap gap-x-4 gap-y-1 border-t pt-3 text-[11px] text-muted-foreground">
          {source && (
            <span>
              {t("source")}: {[source].flat().join(", ")}
            </span>
          )}
          {period && (
            <span>
              {t("period")}: {fmtDay(lang, period.from)} – {fmtDay(lang, period.to)}
            </span>
          )}
        </footer>
      )}
    </motion.section>
  );
}

export function Stat({ label, value, unit, tone, d = 1 }: { label: string; value: number | null | undefined; unit?: string; tone?: "good" | "bad" | "warn"; d?: number }) {
  return (
    <div className="rounded-xl bg-muted/60 p-3">
      <div className={cn("num text-xl font-bold", tone === "good" && "text-good", tone === "bad" && "text-bad", tone === "warn" && "text-warn")}>
        {fmt(value, d)}
        {unit && <span className="ms-1 font-sans text-xs font-medium text-muted-foreground">{unit}</span>}
      </div>
      <div className="mt-0.5 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-xl bg-muted", className)} />;
}

export function PageSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-10 w-72" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <Skeleton className="h-80" />
    </div>
  );
}

export function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  const { t } = useApp();
  return (
    <div role="alert" className="surface flex flex-col items-center gap-3 p-10 text-center">
      <AlertTriangle className="size-8 text-bad" />
      <b>{t("error")}</b>
      <p className="max-w-md text-sm text-muted-foreground">{String((error as Error)?.message ?? error)}</p>
      {retry && (
        <button onClick={retry} className="inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm hover:bg-muted">
          <RefreshCw className="size-4" /> {t("retry")}
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="flex min-h-24 items-center justify-center rounded-xl bg-muted/50 p-6 text-center text-sm text-muted-foreground">{children}</div>;
}

export function Unavailable({ title, why }: { title: string; why: string }) {
  return (
    <div className="rounded-xl border border-dashed p-3">
      <b className="text-sm">{title}</b>
      <p className="mt-0.5 text-xs text-muted-foreground">{why}</p>
    </div>
  );
}

export function Bar({ pct, tone }: { pct: number; tone?: string }) {
  const c = tone ?? (pct >= 90 ? "var(--bad)" : pct >= 75 ? "var(--warn)" : "var(--primary)");
  return (
    <div className="h-2 overflow-hidden rounded-full bg-muted">
      <motion.div
        className="h-full rounded-full"
        style={{ background: c }}
        initial={{ width: 0 }}
        animate={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
      />
    </div>
  );
}

export function DataTable({ cols, rows }: { cols: { label: string; n?: boolean }[]; rows: ReactNode[][] }) {
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full min-w-max text-sm">
        <thead>
          <tr className="text-xs text-muted-foreground">
            {cols.map((c, i) => (
              <th key={i} className={cn("border-b px-2 py-2 text-start font-semibold", c.n && "text-end")}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="transition-colors hover:bg-muted/50">
              {r.map((cell, j) => (
                <td key={j} className={cn("border-b border-border/60 px-2 py-2", cols[j]?.n && "num text-end")}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
