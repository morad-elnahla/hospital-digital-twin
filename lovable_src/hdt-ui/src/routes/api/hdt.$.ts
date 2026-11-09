import { createFileRoute } from "@tanstack/react-router";

/**
 * Transparent pass-through to the original Python backend (app.py). The backend keeps doing its own
 * authentication (Bearer token from /api/login), so this proxy adds nothing and checks nothing itself.
 * Set HDT_API_URL (e.g. https://hdt.example.org) to enable the hosted pass-through.
 */
async function handle({ request, params }: { request: Request; params: { _splat?: string } }) {
  const base = process.env.HDT_API_URL?.replace(/\/$/, "");
  const splat = params._splat ?? "";
  if (!base) return Response.json({ error: "backend not configured" }, { status: 503 });
  const url = new URL(request.url);
  const target = `${base}/api/${splat}${url.search}`;
  const headers = new Headers();
  const auth = request.headers.get("authorization");
  if (auth) headers.set("Authorization", auth);
  if (request.method === "POST") headers.set("Content-Type", "application/json");
  try {
    const res = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "POST" ? await request.text() : undefined,
    });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return Response.json({ error: "backend unreachable" }, { status: 502 });
  }
}

export const Route = createFileRoute("/api/hdt/$")({
  server: {
    handlers: {
      GET: handle,
      POST: handle,
    },
  },
});
