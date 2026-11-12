#!/usr/bin/env python3
"""Erzeugt ein synthetisches Testvideo (120 s) mit bekannten Ballwechseln."""
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.io import wavfile

RALLIES = [(10, 25), (40, 58), (75, 95), (100, 112)]
FPS, W, H, DUR = 10, 320, 180, 120

out = Path(sys.argv[1] if len(sys.argv) > 1 else "testvideo.mp4")
tmp_v, tmp_a = out.with_suffix(".v.mp4"), out.with_suffix(".wav")
rng = np.random.default_rng(1)
in_rally = lambda t: any(s <= t <= e for s, e in RALLIES)

vw = cv2.VideoWriter(str(tmp_v), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
players = rng.uniform([20, 40], [W - 20, H - 20], size=(6, 2))
for i in range(FPS * DUR):
    t = i / FPS
    f = np.full((H, W, 3), (90, 140, 90), np.uint8)
    cv2.line(f, (W // 2, 30), (W // 2, H - 10), (255, 255, 255), 2)
    if in_rally(t):      # alle Spieler hektisch
        players += rng.normal(0, 9, players.shape)
        n = 6
    else:                # nur einer schlendert langsam
        players[0] += rng.normal(0, 1.0, 2)
        n = 1
    players = np.clip(players, [10, 20], [W - 10, H - 10])
    for k in range(n):
        cv2.circle(f, tuple(players[k].astype(int)), 9, (30 + 30 * k, 60, 200 - 20 * k), -1)
    vw.write(f)
vw.release()

sr = 16000
audio = rng.normal(0, 0.004, sr * DUR)  # leises Grundrauschen
for s, e in RALLIES:
    for t in np.arange(s + 0.5, e, 1.1):  # Ballkontakte
        i0 = int(t * sr)
        n = int(0.06 * sr)
        audio[i0:i0 + n] += 0.5 * np.exp(-np.arange(n) / (0.015 * sr)) * np.sin(2 * np.pi * 300 * np.arange(n) / sr)
    i0 = int(e * sr)  # Pfiff am Ende
    n = int(0.8 * sr)
    audio[i0:i0 + n] += 0.3 * np.sin(2 * np.pi * 3000 * np.arange(n) / sr)
wavfile.write(str(tmp_a), sr, (np.clip(audio, -1, 1) * 32767).astype(np.int16))

subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp_v), "-i", str(tmp_a),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)], check=True)
tmp_v.unlink()
tmp_a.unlink()
print(f"Testvideo: {out}  | echte Ballwechsel: {RALLIES}")
