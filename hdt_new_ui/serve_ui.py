"""
Hospital Digital Twin - new UI launcher (standard library only).

Serves the new interface from ./ui and forwards every /api/hdt/<path> request,
unchanged, to the original backend (app.py) at /api/<path>.
app.py itself is NOT modified.

    1) python app.py                (backend, port 8000)
    2) python hdt_new_ui/serve_ui.py   (new UI, port 8080)
    3) open http://127.0.0.1:8080
"""
import argparse
import json
import mimetypes
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

UI = Path(__file__).resolve().parent / "ui"
BACKEND = "http://127.0.0.1:8000"
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, data, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _proxy(self, method, rest, query):
        if rest == "__mode":
            return self._send(200, json.dumps({"mode": "live"}).encode(), "application/json")
        url = f"{BACKEND}/api/{rest}" + (f"?{query}" if query else "")
        body = None
        if method == "POST":
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        req = urllib.request.Request(url, data=body, method=method)
        if self.headers.get("Authorization"):
            req.add_header("Authorization", self.headers["Authorization"])
        if method == "POST":
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return self._send(r.status, r.read(), r.headers.get("Content-Type", "application/json"))
        except urllib.error.HTTPError as e:
            return self._send(e.code, e.read(), e.headers.get("Content-Type", "application/json"))
        except urllib.error.URLError:
            msg = {"error": f"backend unreachable at {BACKEND} - is app.py running?"}
            return self._send(502, json.dumps(msg).encode(), "application/json")

    def _static(self, path):
        f = (UI / unquote(path).lstrip("/")).resolve()
        if UI not in f.parents and f != UI or not f.is_file():
            f = UI / "index.html"          # single-page app: every page loads index.html
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        self._send(200, f.read_bytes(), ctype)

    def _dispatch(self, method):
        u = urlparse(self.path)
        if u.path.startswith("/api/hdt/"):
            return self._proxy(method, u.path[len("/api/hdt/"):], u.query)
        if method != "GET":
            return self._send(404, b'{"error":"not found"}', "application/json")
        self._static(u.path)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--backend", default=BACKEND, help="address of app.py (default http://127.0.0.1:8000)")
    a = ap.parse_args()
    BACKEND = a.backend.rstrip("/")
    print(f"New UI: http://127.0.0.1:{a.port}   ->  backend {BACKEND}   (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
