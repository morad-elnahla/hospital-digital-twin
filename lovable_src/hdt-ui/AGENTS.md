<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## Hospital Digital Twin
- The original Python backend (app.py, from the uploaded project) is the source of truth; this app is only its UI. Never re-implement its logic in TypeScript.
- `src/lib/api.ts` is live-only: it calls backend paths unchanged via the `/api/hdt/*` pass-through (`HDT_API_URL` server env) or directly in the app.py package. Never add snapshot fallback data.
- 3D floor placement is schematic (`src/components/twin/layout.ts`) because the data has no building geometry; keep it a pure module covered by `src/test/twin-layout.test.ts`.
- UI copy: original strings live verbatim in `src/lib/i18n-source.ts`; redesign-only strings go in `src/lib/i18n.ts`.
- Packaged build for app.py: `node scripts/package_app_py.mjs ../../ui` (Node 22; Node 24 is also supported by the verified build here). It emits `ui/dashboard.html` and `ui/assets/`, with SPA fallback handled by app.py.
- Packaged app.py build: the Node script sets `HDT_PACKAGE=1`, `VITE_HASH_ROUTER=1` and `VITE_HDT_DIRECT=1`. Do not hand-edit generated UI assets; backend-driven UI changes go into `src`, then repackage.
