#!/usr/bin/env python3
"""rallycut - schneidet Spielunterbrechungen aus Volleyball-Videos heraus.

Vorgehen (reine Heuristik, kein trainiertes KI-Modell):
  1. Bewegungsenergie pro Zeitfenster (Frame-Differenz, optional nur im Spielfeld-Ausschnitt)
  2. Audio-Aktivitaet pro Zeitfenster (Ballkontakte = Pegelspruenge, Publikum/Pfiffe = Pegel)
  3. Beides zu einem Aktivitaets-Score mischen, per Otsu-Schwelle in "Spiel" / "Pause" trennen
  4. Kurze Luecken schliessen, kurze Segmente verwerfen, Vor- und Nachlauf anhaengen
  5. Segmente als CSV ausgeben (von Hand editierbar) und mit ffmpeg zusammenschneiden

Aufruf:
  python3 rallycut.py auto   spiel.mp4 -o ausgabe/
  python3 rallycut.py analyze spiel.mp4 -o ausgabe/      # nur erkennen (segments.csv + timeline.png)
  python3 rallycut.py cut    spiel.mp4 ausgabe/segments.csv -o spiel_kurz.mp4
"""
import argparse
import csv
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage

BIN = 0.5  # Zeitaufloesung der Merkmale in Sekunden


# ----------------------------------------------------------------- Hilfsfunktionen
def ffmpeg_exe():
    """System-ffmpeg bevorzugen, sonst das mit der App gebuendelte (imageio-ffmpeg)."""
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        sys.exit("ffmpeg nicht gefunden. Bitte ffmpeg installieren oder 'pip install imageio-ffmpeg'.")


def probe(path):
    """Dauer und Audio-Vorhandensein ueber 'ffmpeg -i' (kein ffprobe noetig)."""
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        sys.exit(f"Datei nicht lesbar oder kein Video: {path}")
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    has_audio = bool(re.search(r"Stream #.*Audio", r.stderr))
    return duration, has_audio


def norm(x):
    """Robuste Normierung auf 0..1 ueber das 5.-95. Perzentil."""
    lo, hi = np.percentile(x, [5, 95])
    return np.clip((x - lo) / (hi - lo + 1e-9), 0.0, 1.0)


def fmt(t):
    t = max(0.0, t)
    return f"{int(t // 3600):d}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


# ----------------------------------------------------------------- Merkmale
def motion_features(path, duration, roi=None, sample_fps=4.0):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        sys.exit(f"Video konnte nicht geoeffnet werden: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps / sample_fps)))
    n_bins = int(np.ceil(duration / BIN))
    acc, cnt = np.zeros(n_bins), np.zeros(n_bins)
    W, H = 192, 108
    prev, i, last_pct = None, 0, -1
    total = max(1.0, duration * fps)
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            g = cv2.cvtColor(cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA),
                             cv2.COLOR_BGR2GRAY)
            g = cv2.GaussianBlur(g, (5, 5), 0)
            if roi:
                x0, y0, x1, y1 = roi
                g = g[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
            if prev is not None and prev.shape == g.shape:
                b = min(n_bins - 1, int(i / fps / BIN))
                acc[b] += float((cv2.absdiff(g, prev) > 20).mean())
                cnt[b] += 1
            prev = g
        i += 1
        pct = int(100 * i / total) // 10 * 10
        if pct != last_pct and pct <= 100:
            last_pct = pct
            print(f"  Bewegung: {pct} %", flush=True)
    cap.release()
    m = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
    idx = np.arange(n_bins)
    good = ~np.isnan(m)
    if good.sum() == 0:
        sys.exit("Keine Bewegung auswertbar (Video leer?).")
    return np.interp(idx, idx[good], m[good])


def audio_features(path, duration):
    p = subprocess.run(
        [ffmpeg_exe(), "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
         "-f", "s16le", "-"], capture_output=True)
    x = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    if x.size < 16000:
        return None, None
    hop = 800  # 50 ms
    n = x.size // hop
    fr = x[:n * hop].reshape(n, hop)
    e = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-5)
    onset = np.maximum(0.0, np.diff(e, prepend=e[0]))
    per = int(round(BIN / 0.05))
    nb = int(np.ceil(duration / BIN))
    rms, ons = np.zeros(nb), np.zeros(nb)
    for b in range(nb):
        s = e[b * per:(b + 1) * per]
        o = onset[b * per:(b + 1) * per]
        if s.size:
            rms[b], ons[b] = s.mean(), o.max()
    return rms, ons


# ----------------------------------------------------------------- Segmentierung
def merge(segs, gap):
    out = []
    for s, e in sorted(segs):
        if out and s - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def segment(score, thr, duration, gap, min_len, pre, post):
    lab, _ = ndimage.label(score > thr)
    raw = [(sl[0].start * BIN, sl[0].stop * BIN) for sl in ndimage.find_objects(lab)]
    segs = merge(raw, gap)
    segs = [s for s in segs if s[1] - s[0] >= min_len]
    segs = [[max(0.0, s - pre), min(duration, e + post)] for s, e in segs]
    return merge(segs, 0.0)


def analyze(video, a):
    duration, has_audio = probe(video)
    print(f"Video: {duration / 60:.1f} min, Audio: {'ja' if has_audio else 'nein'}")
    roi = tuple(float(v) for v in a.roi.split(",")) if a.roi else None
    print("Analysiere Bewegung ...")
    mot = motion_features(video, duration, roi)
    aud = None
    rms = ons = None
    if has_audio and a.audio_weight > 0:
        print("Analysiere Audio ...")
        rms, ons = audio_features(video, duration)
    mot_n = norm(mot)
    if rms is not None:
        aud = norm(0.6 * norm(ons) + 0.4 * norm(rms))
        score = (1 - a.audio_weight) * mot_n + a.audio_weight * aud
    else:
        score = mot_n
    k = max(1, int(round(a.smooth / BIN)))
    score = ndimage.uniform_filter1d(score, size=k)
    if a.threshold is not None:
        thr = a.threshold
    else:
        t, _ = cv2.threshold((np.clip(score, 0, 1) * 255).astype(np.uint8).reshape(1, -1),
                             0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thr = float(t) / 255.0
    segs = segment(score, thr, duration, a.gap, a.min_len, a.pre, a.post)
    return duration, mot_n, aud, score, thr, segs


# ----------------------------------------------------------------- Ausgabe
def write_segments(segs, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rally", "start", "end", "duration", "start_ts"])
        for i, (s, e) in enumerate(segs, 1):
            w.writerow([i, f"{s:.2f}", f"{e:.2f}", f"{e - s:.2f}", fmt(s)])


def read_segments(path):
    segs = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            segs.append([float(row["start"]), float(row["end"])])
    return segs


def draw_timeline(duration, mot, aud, score, thr, segs, path):
    W, H = 1600, 300
    img = np.full((H, W, 3), 255, np.uint8)
    x_of = lambda t: int(t / duration * (W - 1))
    for s, e in segs:
        cv2.rectangle(img, (x_of(s), 20), (x_of(e), H - 30), (215, 240, 215), -1)
    def line(vals, color, base, height):
        pts = [(int(i / len(vals) * (W - 1)), int(base - v * height)) for i, v in enumerate(vals)]
        cv2.polylines(img, [np.array(pts, np.int32)], False, color, 1, cv2.LINE_AA)
    line(mot, (230, 150, 60), H - 35, 220)
    if aud is not None:
        line(aud, (60, 90, 220), H - 35, 220)
    line(score, (0, 0, 0), H - 35, 220)
    y = int(H - 35 - thr * 220)
    cv2.line(img, (0, y), (W, y), (0, 0, 200), 1)
    step = 60 if duration < 1800 else 300
    for t in range(0, int(duration), step):
        cv2.line(img, (x_of(t), H - 30), (x_of(t), H - 24), (0, 0, 0), 1)
        cv2.putText(img, f"{t // 60}m", (x_of(t) + 2, H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    cv2.putText(img, "orange=Bewegung  blau=Audio  schwarz=Score  rot=Schwelle  gruen=erkanntes Spiel",
                (8, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    cv2.imwrite(str(path), img)


def cut(video, segs, out, crf=20):
    if not segs:
        sys.exit("Keine Segmente zum Schneiden.")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        lst = tmp / "list.txt"
        with open(lst, "w") as lf:
            for i, (s, e) in enumerate(segs):
                part = tmp / f"part_{i:04d}.mp4"
                print(f"  Schnitt {i + 1}/{len(segs)}: {fmt(s)} - {fmt(e)}")
                subprocess.run(
                    [ffmpeg_exe(), "-v", "error", "-y", "-ss", f"{s:.3f}", "-i", str(video),
                     "-t", f"{e - s:.3f}", "-map", "0:v:0", "-map", "0:a:0?",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
                     "-c:a", "aac", "-b:a", "160k", "-avoid_negative_ts", "make_zero", str(part)],
                    check=True)
                lf.write(f"file '{part}'\n")
        subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(lst), "-c", "copy", str(out)], check=True)
    print(f"Fertig: {out}")


# ----------------------------------------------------------------- CLI
def add_detect_args(p):
    p.add_argument("--audio-weight", type=float, default=0.4, help="Anteil Audio am Score (0 = nur Bild)")
    p.add_argument("--smooth", type=float, default=2.0, help="Glaettung in Sekunden")
    p.add_argument("--threshold", type=float, default=None, help="feste Schwelle 0..1 (sonst automatisch)")
    p.add_argument("--gap", type=float, default=6.0, help="Luecken bis x Sekunden gelten noch als Ballwechsel")
    p.add_argument("--min-len", type=float, default=3.0, help="kuerzere Segmente werden verworfen")
    p.add_argument("--pre", type=float, default=2.0, help="Vorlauf vor dem Ballwechsel (Aufschlag) in s")
    p.add_argument("--post", type=float, default=1.5, help="Nachlauf in s")
    p.add_argument("--roi", default=None, help="Spielfeld-Ausschnitt als Bruchteile x0,y0,x1,y1, z.B. 0.1,0.2,0.9,1")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("analyze", "auto"):
        p = sub.add_parser(name)
        p.add_argument("video")
        p.add_argument("-o", "--outdir", default="rallycut_out")
        add_detect_args(p)
        if name == "auto":
            p.add_argument("--crf", type=int, default=20)
    c = sub.add_parser("cut")
    c.add_argument("video")
    c.add_argument("segments")
    c.add_argument("-o", "--out", default="spiel_kurz.mp4")
    c.add_argument("--crf", type=int, default=20)
    a = ap.parse_args()

    if a.cmd == "cut":
        cut(a.video, read_segments(a.segments), a.out, a.crf)
        return

    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    duration, mot, aud, score, thr, segs = analyze(a.video, a)
    write_segments(segs, out / "segments.csv")
    draw_timeline(duration, mot, aud, score, thr, segs, out / "timeline.png")
    kept = sum(e - s for s, e in segs)
    print(f"{len(segs)} Ballwechsel erkannt, behalten: {kept / 60:.1f} von {duration / 60:.1f} min "
          f"({100 * kept / duration:.0f} %), Schwelle {thr:.2f}")
    print(f"-> {out / 'segments.csv'} (editierbar), {out / 'timeline.png'} (zur Kontrolle)")
    if a.cmd == "auto":
        cut(a.video, segs, out / (Path(a.video).stem + "_kurz.mp4"), a.crf)


if __name__ == "__main__":
    main()
