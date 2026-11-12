#!/usr/bin/env python3
"""Volleyball Tool - Desktop-App.

Startet einen lokalen Server (nur 127.0.0.1) und oeffnet die Oberflaeche im Browser.
Alles laeuft auf deinem Rechner, es werden keine Videos hochgeladen.
"""
import argparse
import contextlib
import io
import json
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

# Im "windowed"-Modus (PyInstaller) gibt es teils kein stdout/stderr.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import rallycut  # noqa: E402
import volleyball_stats  # noqa: E402
from ui_html import INDEX_HTML  # noqa: E402

WORK = Path.home() / "VolleyballTool"
TOKEN = secrets.token_urlsafe(16)
DEFAULTS = dict(audio_weight=0.4, smooth=2.0, threshold=None, gap=6.0, min_len=3.0, pre=2.0, post=1.5, roi=None)

STATE = {"video": None, "outdir": None, "duration": None, "segs": [], "quit": False,
         "last_ping": time.time(), "seen_ping": False}
JOB = {"status": "idle", "log": "", "result": None, "error": None}
DIALOGS = queue.Queue()


# ----------------------------------------------------------------- Jobs
class LogWriter:
    def write(self, s):
        JOB["log"] += s
        JOB["log"] = JOB["log"][-20000:]
        return len(s)

    def flush(self):
        pass


def start_job(fn):
    if JOB["status"] == "running":
        return False
    JOB.update(status="running", log="", result=None, error=None)

    def target():
        try:
            with contextlib.redirect_stdout(LogWriter()):
                JOB["result"] = fn()
            JOB["status"] = "done"
        except SystemExit as e:
            JOB.update(status="error", error=str(e.code))
        except Exception:
            JOB.update(status="error", error=traceback.format_exc(limit=3))

    threading.Thread(target=target, daemon=True).start()
    return True


def parse_params(p):
    d = dict(DEFAULTS)
    for k in ("audio_weight", "smooth", "gap", "min_len", "pre", "post"):
        if p.get(k) not in (None, ""):
            d[k] = float(p[k])
    if p.get("threshold") not in (None, ""):
        d["threshold"] = float(p["threshold"])
    roi = (p.get("roi") or "").strip()
    if roi:
        if len([float(v) for v in roi.split(",")]) != 4:
            raise ValueError("Spielfeld-Ausschnitt braucht 4 Werte: x0,y0,x1,y1")
        d["roi"] = roi
    return SimpleNamespace(**d)


def do_analyze(video, params):
    outdir = WORK / Path(video).stem
    outdir.mkdir(parents=True, exist_ok=True)
    duration, mot, aud, score, thr, segs = rallycut.analyze(video, params)
    rallycut.write_segments(segs, outdir / "segments.csv")
    rallycut.draw_timeline(duration, mot, aud, score, thr, segs, outdir / "timeline.png")
    STATE.update(video=video, outdir=outdir, duration=duration, segs=[list(s) for s in segs])
    kept = sum(e - s for s, e in segs)
    print(f"{len(segs)} Ballwechsel erkannt, behalten: {kept / 60:.1f} von {duration / 60:.1f} min")
    return {"duration": duration, "kept": kept, "count": len(segs), "outdir": str(outdir)}


def do_cut():
    out = STATE["outdir"] / (Path(STATE["video"]).stem + "_kurz.mp4")
    rallycut.cut(STATE["video"], STATE["segs"], out)
    return {"output": str(out)}


def save_segments(segs):
    clean = []
    for s, e in segs:
        s, e = float(s), float(e)
        if e - s > 0.2:
            clean.append([max(0.0, s), e])
    clean.sort()
    STATE["segs"] = clean
    if STATE["outdir"]:
        rallycut.write_segments(clean, STATE["outdir"] / "segments.csv")


def reveal(path):
    path = str(path)
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# ----------------------------------------------------------------- Dateidialog (im Hauptthread)
class DialogReq:
    def __init__(self):
        self.done = threading.Event()
        self.result = None  # None = nicht verfuegbar

    def run(self):
        try:
            import tkinter
            from tkinter import filedialog
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            self.result = filedialog.askopenfilename(
                title="Volleyball-Video auswaehlen",
                filetypes=[("Videos", "*.mp4 *.mov *.mkv *.avi *.m4v *.mts"), ("Alle Dateien", "*.*")])
            root.destroy()
        except Exception:
            self.result = None
        self.done.set()


# ----------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _authed(self):
        return parse_qs(urlparse(self.path).query).get("t", [""])[0] == TOKEN

    def do_GET(self):
        if not self._ok():
            return self._send(403, {"error": "Host nicht erlaubt"})
        path = urlparse(self.path).path
        if path == "/":
            return self._send(200, INDEX_HTML.replace("__TOKEN__", TOKEN), "text/html; charset=utf-8")
        if not self._authed():
            return self._send(403, {"error": "Kein Zugriff"})
        if path == "/api/ping":
            STATE.update(last_ping=time.time(), seen_ping=True)
            return self._send(200, {"ok": True})
        if path == "/api/job":
            return self._send(200, JOB)
        if path == "/api/segments":
            return self._send(200, {"segments": STATE["segs"], "duration": STATE["duration"]})
        if path == "/timeline.png":
            f = STATE["outdir"] and STATE["outdir"] / "timeline.png"
            if f and f.exists():
                return self._send(200, f.read_bytes(), "image/png")
            return self._send(404, {"error": "Keine Timeline"})
        if path == "/report":
            f = STATE["outdir"] and STATE["outdir"] / "report" / "report.html"
            if f and f.exists():
                return self._send(200, f.read_bytes(), "text/html; charset=utf-8")
            return self._send(404, "Noch kein Report.", "text/plain; charset=utf-8")
        return self._send(404, {"error": "Nicht gefunden"})

    def do_POST(self):
        if not self._ok() or not self._authed():
            return self._send(403, {"error": "Kein Zugriff"})
        path = urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "Ungueltige Anfrage"})
        try:
            self._post(path, body)
        except (ValueError, KeyError) as e:
            self._send(400, {"error": f"Ungueltige Eingabe: {e}"})
        except SystemExit as e:
            self._send(400, {"error": str(e.code)})
        except Exception:
            self._send(500, {"error": traceback.format_exc(limit=3)})

    def _post(self, path, body):
        if path == "/api/analyze":
            video = (body.get("video") or "").strip().strip('"')
            if not Path(video).is_file():
                return self._send(400, {"error": "Videodatei nicht gefunden. Bitte Pfad pruefen."})
            params = parse_params(body.get("params") or {})
            ok = start_job(lambda: do_analyze(video, params))
            return self._send(200 if ok else 409, {"started": ok})
        if path == "/api/segments":
            save_segments(body["segments"])
            return self._send(200, {"segments": STATE["segs"]})
        if path == "/api/cut":
            if not STATE["video"] or not STATE["segs"]:
                return self._send(400, {"error": "Zuerst Ballwechsel erkennen."})
            save_segments(body.get("segments", STATE["segs"]))
            ok = start_job(do_cut)
            return self._send(200 if ok else 409, {"started": ok})
        if path == "/api/stats":
            if JOB["status"] == "running":
                return self._send(409, {"error": "Es laeuft gerade ein anderer Vorgang."})
            outdir = STATE["outdir"] or (WORK / "statistik")
            outdir.mkdir(parents=True, exist_ok=True)
            text = (body.get("events") or "").strip()
            seg_file = outdir / "segments.csv"
            ev_file = None
            if text:
                ev_file = outdir / "events.csv"
                ev_file.write_text(text + "\n", encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                volleyball_stats.generate_report(seg_file if seg_file.exists() else None, ev_file,
                                                 outdir / "report", STATE["duration"])
            return self._send(200, {"console": buf.getvalue(), "outdir": str(outdir / "report")})
        if path == "/api/browse":
            req = DialogReq()
            DIALOGS.put(req)
            req.done.wait(300)
            return self._send(200, {"available": req.result is not None, "path": req.result or ""})
        if path == "/api/reveal":
            target = body.get("target")
            folder = STATE["outdir"] or WORK
            folder.mkdir(parents=True, exist_ok=True)
            reveal(folder if target != "report" else (folder / "report" if (folder / "report").exists() else folder))
            return self._send(200, {"ok": True})
        if path == "/api/quit":
            STATE["quit"] = True
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "Nicht gefunden"})


def main():
    ap = argparse.ArgumentParser(description="Volleyball Tool - Desktop-App")
    ap.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch oeffnen")
    ap.add_argument("--port", type=int, default=0)
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(url, flush=True)
    if not a.no_browser:
        webbrowser.open(url)

    # Hauptthread: Dateidialoge (tkinter braucht den Hauptthread) und automatisches Beenden,
    # wenn der Browser-Tab laenger als 3 Minuten nicht mehr antwortet.
    while not STATE["quit"]:
        try:
            DIALOGS.get(timeout=0.5).run()
        except queue.Empty:
            pass
        if STATE["seen_ping"] and JOB["status"] != "running" and time.time() - STATE["last_ping"] > 180:
            break
    srv.shutdown()


if __name__ == "__main__":
    main()
