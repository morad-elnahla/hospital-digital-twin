import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getToken, setToken, type Mode } from "./api";
import { translate, type Lang } from "./i18n";

export type Meta = { first_day: string; last_day: string; default_as_of: string; units: string[]; synthetic: boolean };
export type User = { username: string; role: string; role_label: string; permissions: string[] };

type Ctx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (k: string, v?: Record<string, string | number>) => string;
  mode: Mode | null;
  asOf: string; // ISO hour, e.g. 2026-10-17T08:00:00
  setAsOf: (v: string) => void;
  meta: Meta | null;
  user: User | null;
  needsLogin: boolean;
  login: (u: string, p: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (perm: string) => boolean;
};

const AppCtx = createContext<Ctx | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [lang, setLangState] = useState<Lang>("ar");
  const [mode] = useState<Mode>("live");
  const [asOf, setAsOf] = useState("2026-10-17T08:00:00");
  const [hasToken, setHasToken] = useState(false);

  useEffect(() => {
    const l = localStorage.getItem("lang");
    if (l === "en" || l === "ar") setLangState(l);
    setHasToken(!!getToken());
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);

  const authed = mode === "live" && hasToken;
  const metaQ = useQuery({ queryKey: ["meta", mode, hasToken], queryFn: () => api<Meta>("/api/meta"), enabled: authed });
  const meQ = useQuery({ queryKey: ["me", mode, hasToken], queryFn: () => api<User>("/api/me"), enabled: authed, retry: false });

  useEffect(() => {
    if (metaQ.data) setAsOf(metaQ.data.default_as_of);
  }, [metaQ.data]);
  useEffect(() => {
    if (meQ.error) setHasToken(false);
  }, [meQ.error]);

  const setLang = useCallback((l: Lang) => {
    localStorage.setItem("lang", l);
    setLangState(l);
  }, []);
  const t = useCallback((k: string, v?: Record<string, string | number>) => translate(lang, k, v), [lang]);

  const login = useCallback(
    async (username: string, password: string) => {
      const r = await api<{ token: string; user: User }>("/api/login", { username, password });
      setToken(r.token);
      setHasToken(true);
      qc.invalidateQueries();
    },
    [qc],
  );
  const logout = useCallback(async () => {
    try {
      await api("/api/logout", {});
    } catch {
      /* already signed out */
    }
    setToken(null);
    setHasToken(false);
    qc.clear();
  }, [qc]);

  const user = meQ.data ?? null;
  const value = useMemo<Ctx>(
    () => ({
      lang,
      setLang,
      t,
      mode,
      asOf,
      setAsOf,
      meta: metaQ.data ?? null,
      user,
      needsLogin: mode === "live" && !hasToken,
      login,
      logout,
      can: (p) => !!user?.permissions.includes(p),
    }),
    [lang, setLang, t, mode, asOf, metaQ.data, user, hasToken, login, logout],
  );
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

export function useApp() {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside AppProvider");
  return c;
}

/** Query for an as_of-scoped endpoint of the backend. */
export function useHdt<T = any>(endpoint: string, opts: { scoped?: boolean; enabled?: boolean } = {}) {
  const { asOf, mode, needsLogin } = useApp();
  const scoped = opts.scoped ?? true;
  const path = scoped ? `/api/${endpoint}?as_of=${encodeURIComponent(asOf)}` : `/api/${endpoint}`;
  return useQuery<T>({
    queryKey: ["hdt", mode, path],
    queryFn: () => api<T>(path),
    enabled: !!mode && !needsLogin && (opts.enabled ?? true),
    placeholderData: (prev) => prev,
    staleTime: 60_000,
  });
}
