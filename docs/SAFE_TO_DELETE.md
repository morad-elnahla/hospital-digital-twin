# Safe to delete after review

These legacy paths are no longer imported by application code or served by `app.py`; the server serves only `ui/dashboard.html` and `/ui/*` assets. The legacy `/static/*` handler has been removed. `tests/dom_smoke.js` reads the current `ui/dashboard.html`, not the root legacy HTML. No path below was deleted.

- `hdt_new_ui/`
- `static/app.js`
- `static/app.css`
- `static/charts.js`
- `static/i18n.js`
- `static/hdtui/`
- `dashboard.html` (root)
