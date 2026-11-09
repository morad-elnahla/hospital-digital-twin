import { Link, useHydrated, useLocation } from "@tanstack/react-router";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Activity,
  BedDouble,
  Bell,
  Bot,
  Box,
  Building2,
  ChevronLeft,
  ChevronRight,
  Database,
  FlaskConical,
  Gauge,
  Languages,
  LayoutGrid,
  LineChart,
  LogOut,
  Menu,
  MessageSquare,
  Pause,
  Play,
  Scale,
  Stethoscope,
  Users,
  X,
} from "lucide-react";
import { useApp } from "@/lib/app-state";
import { useHdt } from "@/lib/app-state";
import { fmtWhen } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const NAV = [
  { grp: "grp_command", items: [
    { to: "/", key: "nav_twin", icon: Box },
    { to: "/overview", key: "nav_overview", icon: LayoutGrid },
    { to: "/alerts", key: "nav_alerts", icon: Bell, badge: true },
  ]},
  { grp: "grp_hospital", items: [
    { to: "/capacity", key: "nav_capacity", icon: BedDouble },
    { to: "/staff", key: "nav_staff", icon: Users },
    { to: "/or", key: "nav_or", icon: Stethoscope },
    { to: "/forecasts", key: "nav_forecast", icon: LineChart },
  ]},
  { grp: "grp_intelligence", items: [
    { to: "/agents", key: "nav_agents", icon: Bot },
    { to: "/simulator", key: "nav_simulator", icon: FlaskConical },
    { to: "/decisions", key: "nav_decisions", icon: Scale },
    { to: "/assistant", key: "nav_assistant", icon: MessageSquare },
  ]},
  { grp: "grp_system", items: [{ to: "/system", key: "nav_system", icon: Database }] },
] as const;

function Brand() {
  const { t } = useApp();
  return (
    <div className="flex items-center gap-3 px-2">
      <div className="bg-brand grid size-10 place-items-center rounded-xl text-primary-foreground shadow-float">
        <Building2 className="size-5" />
      </div>
      <div className="leading-tight">
        <div className="text-sm font-extrabold text-sidebar-accent-foreground">{t("brand")}</div>
        <div className="text-[11px] text-sidebar-foreground/70">{t("brand_sub")}</div>
      </div>
    </div>
  );
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useApp();
  const loc = useLocation();
  const alerts = useHdt<{ needs_attention?: number }>("alerts");
  const n = alerts.data?.needs_attention ?? 0;
  return (
    <nav className="space-y-5">
      {NAV.map((g) => (
        <div key={g.grp}>
          <div className="mb-1.5 px-3 text-[10px] font-bold tracking-[0.14em] text-sidebar-foreground/50 uppercase">{t(g.grp)}</div>
          <ul className="space-y-0.5">
            {g.items.map((it) => {
              const active = it.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(it.to);
              const Icon = it.icon;
              return (
                <li key={it.to}>
                  <Link
                    to={it.to}
                    onClick={onNavigate}
                    className={cn(
                      "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors",
                      active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                    )}
                  >
                    {active && <motion.span layoutId="nav-active" className="absolute inset-y-1.5 start-0 w-[3px] rounded-full bg-sidebar-primary" />}
                    <Icon className={cn("size-4 shrink-0", active && "text-sidebar-primary")} />
                    <span className="flex-1 truncate">{t(it.key)}</span>
                    {"badge" in it && n > 0 && <span className="num rounded-full bg-bad px-1.5 text-[10px] font-bold text-destructive-foreground">{n}</span>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Sidebar() {
  const { t, user, logout, mode } = useApp();
  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col gap-6 overflow-y-auto bg-sidebar p-4 lg:flex">
      <Brand />
      <NavList />
      <div className="mt-auto space-y-2 rounded-xl bg-sidebar-accent/50 p-3 text-xs text-sidebar-foreground">
        <div className="flex items-center gap-2">
          <span className={cn("relative grid size-2 place-items-center")}>
            <span className={cn("absolute size-2 rounded-full pulse-ring", mode === "live" ? "bg-good" : "bg-warn")} />
            <span className={cn("size-2 rounded-full", mode === "live" ? "bg-good" : "bg-warn")} />
          </span>
          <b className="text-sidebar-accent-foreground">{t("mode_live")}</b>
        </div>
        {user && mode === "live" && (
          <div className="flex items-center justify-between border-t border-sidebar-border pt-2">
            <span>
              {user.username} · {user.role_label}
            </span>
            <button onClick={logout} aria-label={t("sign_out")} className="rounded p-1 hover:bg-sidebar-accent">
              <LogOut className="size-3.5" />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}

function MobileNav() {
  const [open, setOpen] = useState(false);
  const { t } = useApp();
  return (
    <>
      <button onClick={() => setOpen(true)} className="rounded-lg p-2 hover:bg-muted lg:hidden" aria-label="menu">
        <Menu className="size-5" />
      </button>
      <AnimatePresence>
        {open && (
          <>
            <motion.div className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-sm lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setOpen(false)} />
            <motion.aside
              className="fixed inset-y-0 start-0 z-50 flex w-72 flex-col gap-6 overflow-y-auto bg-sidebar p-4 lg:hidden"
              initial={{ x: "var(--off)" }}
              animate={{ x: 0 }}
              exit={{ x: "var(--off)" }}
              style={{ ["--off" as string]: "calc(-100% * var(--dirsign, 1))" }}
              transition={{ type: "spring", damping: 30, stiffness: 300 }}
            >
              <div className="flex items-center justify-between">
                <Brand />
                <button onClick={() => setOpen(false)} className="rounded p-1 text-sidebar-foreground" aria-label={t("close")}>
                  <X className="size-5" />
                </button>
              </div>
              <NavList onNavigate={() => setOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}

/** Replay-moment scrubber across the data pack's 90 days. */
export function Timeline({ compact }: { compact?: boolean }) {
  const { meta, asOf, setAsOf, lang, t } = useApp();
  const [playing, setPlaying] = useState(false);
  const days = useMemo(() => {
    if (!meta) return [] as string[];
    const out: string[] = [];
    const d = new Date(meta.first_day + "T00:00:00Z");
    const end = new Date(meta.last_day + "T00:00:00Z");
    while (d <= end) {
      out.push(d.toISOString().slice(0, 10));
      d.setUTCDate(d.getUTCDate() + 1);
    }
    return out;
  }, [meta]);
  const idx = Math.max(0, days.indexOf(asOf.slice(0, 10)));
  const hour = asOf.slice(11, 13) || "08";
  const ref = useRef(idx);
  ref.current = idx;
  useEffect(() => {
    if (!playing || !days.length) return;
    const id = setInterval(() => {
      const next = ref.current + 1;
      if (next >= days.length) return setPlaying(false);
      setAsOf(`${days[next]}T${hour}:00:00`);
    }, 1100);
    return () => clearInterval(id);
  }, [playing, days, hour, setAsOf]);
  if (!days.length) return <div className="h-9 w-64 animate-pulse rounded-lg bg-muted" />;
  const step = (n: number) => setAsOf(`${days[Math.min(days.length - 1, Math.max(0, idx + n))]}T${hour}:00:00`);
  const Prev = lang === "ar" ? ChevronRight : ChevronLeft;
  const Next = lang === "ar" ? ChevronLeft : ChevronRight;
  return (
    <div className={cn("flex items-center gap-2", compact ? "w-full" : "min-w-0 flex-1")}>
      <button onClick={() => step(-1)} className="rounded-md p-1.5 hover:bg-muted" aria-label="previous day">
        <Prev className="size-4" />
      </button>
      <button
        onClick={() => setPlaying((p) => !p)}
        className="bg-brand grid size-8 shrink-0 place-items-center rounded-full text-primary-foreground shadow-float transition-transform hover:scale-105"
        aria-label={t(playing ? "pause" : "play")}
      >
        {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5 translate-x-px" />}
      </button>
      <button onClick={() => step(1)} className="rounded-md p-1.5 hover:bg-muted" aria-label="next day">
        <Next className="size-4" />
      </button>
      <input
        type="range"
        dir="ltr"
        min={0}
        max={days.length - 1}
        value={idx}
        onChange={(e) => setAsOf(`${days[+e.target.value]}T${hour}:00:00`)}
        className="h-1.5 min-w-24 flex-1 cursor-pointer accent-[var(--primary)]"
        aria-label={t("replay")}
      />
      <select
        value={hour}
        onChange={(e) => setAsOf(`${asOf.slice(0, 10)}T${e.target.value}:00:00`)}
        className="num rounded-md border bg-card px-1.5 py-1 text-xs"
        aria-label="hour"
      >
        {Array.from({ length: 24 }, (_, h) => String(h).padStart(2, "0")).map((h) => (
          <option key={h}>{h}</option>
        ))}
      </select>
      <div className="hidden min-w-28 text-xs whitespace-nowrap text-muted-foreground sm:block">
        <div className="font-semibold text-foreground">{fmtWhen(lang, asOf)}</div>
      </div>
    </div>
  );
}

function Topbar() {
  const { t, lang, setLang } = useApp();
  return (
    <header className="glass sticky top-0 z-40 flex items-center gap-3 border-x-0 border-t-0 px-4 py-2.5 shadow-none md:px-6">
      <MobileNav />
      <div className="hidden items-center gap-2 text-xs font-semibold text-muted-foreground md:flex">
        <Activity className="size-4 text-primary" />
        {t("replay")}
      </div>
      <Timeline />
      <button
        onClick={() => setLang(lang === "ar" ? "en" : "ar")}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border bg-card px-2.5 py-1.5 text-xs font-semibold hover:bg-muted"
      >
        <Languages className="size-3.5" /> {t("language")}
      </button>
    </header>
  );
}

function Login() {
  const { t, login, lang, setLang } = useApp();
  const [u, setU] = useState("manager");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="bg-hero grid min-h-screen place-items-center p-4">
      <motion.form
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setErr("");
          try {
            await login(u, p);
          } catch (x) {
            setErr((x as Error).message);
          } finally {
            setBusy(false);
          }
        }}
        className="surface w-full max-w-sm space-y-4 p-7"
      >
        <div className="flex items-center justify-between">
          <div className="bg-brand grid size-11 place-items-center rounded-xl text-primary-foreground"><Gauge className="size-5" /></div>
          <button type="button" onClick={() => setLang(lang === "ar" ? "en" : "ar")} className="text-xs font-semibold text-primary">{t("language")}</button>
        </div>
        <div>
          <h1 className="text-xl font-extrabold">{t("login_title")}</h1>
          <p className="mt-1 text-xs text-muted-foreground">{t("login_hint")}</p>
        </div>
        <label className="block text-sm font-medium">
          {t("username")}
          <input value={u} onChange={(e) => setU(e.target.value)} className="mt-1 w-full rounded-lg border bg-card px-3 py-2" autoComplete="username" />
        </label>
        <label className="block text-sm font-medium">
          {t("password")}
          <input type="password" value={p} onChange={(e) => setP(e.target.value)} className="mt-1 w-full rounded-lg border bg-card px-3 py-2" autoComplete="current-password" />
        </label>
        {err && <p role="alert" className="text-sm text-bad">{err}</p>}
        <button disabled={busy} className="bg-brand w-full rounded-lg py-2.5 text-sm font-bold text-primary-foreground transition-opacity disabled:opacity-60">{t("sign_in")}</button>
      </motion.form>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { needsLogin, lang } = useApp();
  const loc = useLocation();
  const hydrated = useHydrated();
  if (!hydrated) return <div className="grid min-h-screen place-items-center"><span className="size-8 animate-spin rounded-full border-2 border-primary border-t-transparent" /></div>;
  if (needsLogin) return <Login />;
  return (
    <div className="flex min-h-screen" style={{ ["--dirsign" as string]: lang === "ar" ? -1 : 1 }}>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <motion.main
          key={loc.pathname}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="min-w-0 flex-1 p-4 md:p-6 lg:p-8"
        >
          {children}
        </motion.main>
      </div>
    </div>
  );
}
