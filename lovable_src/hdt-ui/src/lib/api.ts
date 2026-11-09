/** Live-only API client for the Python Hospital Digital Twin backend. */
export type Mode = "live";

/** Packaged app.py builds call /api directly; hosted builds pass through /api/hdt/*. */
const DIRECT = import.meta.env.VITE_HDT_DIRECT === "1";
let token: string | null = typeof window !== "undefined" ? sessionStorage.getItem("hdt_token") : null;

export const setToken = (t: string | null) => {
  token = t;
  if (t) sessionStorage.setItem("hdt_token", t);
  else sessionStorage.removeItem("hdt_token");
};
export const getToken = () => token;

export class AuthRequiredError extends Error {}

export async function api<T = any>(path: string, body?: Record<string, unknown>): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = "Bearer " + token;
  const opts: RequestInit = { headers };
  if (body !== undefined) {
    opts.method = "POST";
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(DIRECT ? path : "/api/hdt" + path.replace(/^\/api/, ""), opts);
  let data: any = {};
  try { data = await res.json(); } catch { /* non-JSON response */ }
  if (res.status === 401 && path !== "/api/login") {
    setToken(null);
    throw new AuthRequiredError(data.error || "sign in required");
  }
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data as T;
}
