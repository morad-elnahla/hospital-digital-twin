# Hospital Digital Twin UI — local development

This is the complete source of the React UI for the Python backend (`app.py`).
The backend is not part of this repo; the UI only calls its API (see `API_CONTRACT.md`).

## Requirements

- **Node.js 22** (tested with 22.23.4; see `.nvmrc`). npm 10+ ships with it.
- Optional: **bun 1.4+** (the repo also has `bun.lock`).
- Only for `scripts/package-app-py.sh`: bash, rsync, python3 and bun (on Windows use WSL or Git Bash).

## Install, run, test, build

```sh
npm install          # .npmrc sets legacy-peer-deps=true (needed by npm, otherwise it crashes)
npm run dev          # dev server on http://localhost:8080 (recorded snapshot data unless HDT_API_URL is set)
npm test             # vitest: 35 tests
npm run build        # production build
```

With bun instead: `bun install`, `bun run dev`, `bun run build`.

## Build outputs

There are two ways to ship the UI:

### A) Standalone web app (`npm run build`)

Written to **`dist/`**:

- `.output/public/` — built static assets and copied public files.
- `dist/server/` — server entry (SSR + the `/api/hdt/*` proxy). Default target is Cloudflare Workers
  (`dist/server/wrangler.json`). Preview with `npx vite preview`, deploy with `npx nitro deploy --prebuilt`.

This mode needs the server part, because the browser calls `/api/hdt/*` and the server forwards to `HDT_API_URL`.

### B) Served by app.py itself (what you use with `python app.py`)

```sh
bash scripts/package-app-py.sh ./out
```

Writes:

- `out/dashboard.html` → replaces `dashboard.html` next to `app.py`
- `out/static/hdtui/` → **replace** the whole `static/hdtui` folder (delete the old one first; never mix old and new chunks)

This build sets `HDT_PACKAGE=1 VITE_HASH_ROUTER=1 VITE_HDT_DIRECT=1`: asset URLs point to `/static/hdtui/`,
routing uses hash URLs (`/#/assistant`), fonts are bundled, inline scripts are moved to files (app.py's CSP),
and the UI calls app.py's `/api/...` directly. No Node server is needed at runtime.

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `HDT_API_URL` | server runtime (mode A only) | Base URL of the Python backend, e.g. `http://127.0.0.1:8000`. If unset, the UI runs on recorded snapshot data (read-only). |
| `VITE_HDT_DIRECT=1` | build time | Browser calls `/api/...` directly (same origin as app.py), no proxy, always live. |
| `VITE_HASH_ROUTER=1` | build time | Hash routing (`/#/page`), needed when the host only serves `/`. |
| `HDT_PACKAGE=1` | build time | Asset URLs under `/static/hdtui/`, no inlined fonts. Used only by the package script. |

No secrets or API keys are needed by the UI.

Dev against your running backend:

```sh
HDT_API_URL=http://127.0.0.1:8000 npm run dev            # macOS/Linux
$env:HDT_API_URL="http://127.0.0.1:8000"; npm run dev    # Windows PowerShell
```

## Where things are

- `src/routes/` — pages (`index.tsx` = 3D twin, `overview`, `alerts`, `capacity`, `staff`, `or`, `forecasts`,
  `agents`, `simulator`, `decisions`, `assistant`, `system`); `src/routes/api/hdt.$.ts` = backend proxy
- `src/components/twin/` — 3D scene (`scene.tsx`, three.js / react-three-fiber) and floor layout (`layout.ts`)
- `src/components/hdt/` — shell, charts, decision view, shared UI
- `src/lib/api.ts` — the only API client (live / snapshot switch)
- `src/lib/app-state.tsx` — auth, replay time (`as_of`), `useHdt()` data hook
- `src/lib/decision-ui.ts` — decision status / NO_ACTION helpers
- `src/lib/i18n-source.ts`, `src/lib/i18n.ts` — Arabic + English strings
- `src/styles.css` — Tailwind v4 theme tokens (no tailwind.config.js in Tailwind v4)
- `vite.config.ts` — uses `@lovable.dev/vite-tanstack-config` (public npm package that bundles the TanStack Start,
  React, Tailwind and Nitro plugins). It works outside Lovable; you can replace it with a plain TanStack Start config later.
