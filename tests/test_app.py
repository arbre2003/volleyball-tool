#!/usr/bin/env python3
"""Ende-zu-Ende-Test: startet die App ohne Browser und spielt den Ablauf ueber die HTTP-API durch.

Aufruf (im Projektordner):  python3 tests/test_app.py
"""
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp())
video = tmp / "test.mp4"
subprocess.run([sys.executable, str(ROOT / "tests" / "make_testvideo.py"), str(video)], check=True)

proc = subprocess.Popen([sys.executable, str(ROOT / "app.py"), "--no-browser"], cwd=ROOT,
                        stdout=subprocess.PIPE, text=True, env={**__import__("os").environ, "HOME": str(tmp), "USERPROFILE": str(tmp)})
base = proc.stdout.readline().strip()
try:
    token = re.search(r'const T = "([^"]+)"', urllib.request.urlopen(base).read().decode()).group(1)

    def call(path, body=None):
        req = urllib.request.Request(f"{base.rstrip('/')}{path}{'&' if '?' in path else '?'}t={token}",
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"} if body is not None else {})
        try:
            return json.loads(urllib.request.urlopen(req).read())
        except urllib.error.HTTPError as e:
            return {"http_error": e.code, **json.loads(e.read())}

    def wait():
        for _ in range(300):
            j = call("/api/job")
            if j["status"] != "running":
                return j
            time.sleep(0.5)
        raise SystemExit("Timeout")

    # ohne Token kein Zugriff
    try:
        urllib.request.urlopen(base + "api/job")
        raise SystemExit("FEHLER: Zugriff ohne Token war moeglich")
    except urllib.error.HTTPError as e:
        assert e.code == 403

    assert call("/api/analyze", {"video": "/nicht/vorhanden.mp4"})["http_error"] == 400
    assert call("/api/analyze", {"video": str(video), "params": {"gap": "3"}})["started"]
    j = wait()
    assert j["status"] == "done", j
    print("Analyse:", j["result"]["count"], "Ballwechsel")
    assert j["result"]["count"] == 4, j

    segs = call("/api/segments")["segments"]
    assert call("/api/cut", {"segments": segs[:2]})["started"]
    j = wait()
    assert j["status"] == "done", j
    out = Path(j["result"]["output"])
    assert out.exists() and out.stat().st_size > 1000
    print("Schnitt:", out.name, f"{out.stat().st_size // 1024} KB")

    events = "time,team,player,action,result\n0:12,A,Anna,serve,ok\n0:22,A,Fiona,attack,point\n"
    r = call("/api/stats", {"events": events})
    assert "console" in r, r
    html = urllib.request.urlopen(f"{base.rstrip('/')}/report?t={token}").read().decode()
    assert "Fiona" in html and "Ballwechsel" in html
    bad = call("/api/stats", {"events": "time,team,player,action,result\n0:12,A,Anna,smash,ok\n"})
    assert bad["http_error"] == 400
    print("Statistik: OK")
    call("/api/quit", {})
    print("ALLE TESTS BESTANDEN")
finally:
    time.sleep(1)
    proc.terminate()
