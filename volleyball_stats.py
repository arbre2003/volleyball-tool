#!/usr/bin/env python3
"""volleyball_stats - Statistik fuer Volleyballspiele.

Zwei Quellen:
  1. segments.csv aus rallycut.py  -> automatische Ballwechsel-Statistik (Anzahl, Dauer, Spielzeitanteil)
  2. events.csv (getaggte Aktionen) -> Spieler- und Teamstatistik (Angriff, Aufschlag, Block, Annahme ...)

Aufruf:
  python3 volleyball_stats.py template -o events.csv
  python3 volleyball_stats.py report --segments ausgabe/segments.csv --events events.csv -o report/
  python3 volleyball_stats.py report --segments ausgabe/segments.csv -o report/      # nur Ballwechsel

events.csv Spalten: time, team, player, action, result
  time    Sekunde im Originalvideo oder mm:ss bzw. h:mm:ss
  team    A oder B
  action  serve | receive | set | attack | block | dig | freeball
  result  point  (Punkt fuer das Team: Ass, Angriffspunkt, Blockpunkt)
          error  (Fehler: Aufschlag-/Angriffsfehler, geblockter Angriff, Annahmefehler ...)
          ok     (Aktion ohne direkten Punkt, Ballwechsel geht weiter)
  Pro Ballwechsel genau ein Ereignis mit point oder error taggen, sonst wird doppelt gezaehlt.
"""
import argparse
import csv
import html
import sys
from pathlib import Path

import pandas as pd

ACTIONS = ["serve", "receive", "set", "attack", "block", "dig", "freeball"]
RESULTS = {"point": "point", "ace": "point", "kill": "point", "stuff": "point",
           "error": "error", "blocked": "error", "fehler": "error", "punkt": "point",
           "ok": "ok", "": "ok", "continue": "ok", "in": "ok"}

TEMPLATE = """time,team,player,action,result
0:12,A,Anna,serve,ok
0:14,B,Berta,receive,ok
0:16,B,Clara,set,ok
0:17,B,Dora,attack,ok
0:18,A,Eva,dig,ok
0:20,A,Fiona,attack,point
1:05,B,Berta,serve,point
1:48,A,Anna,serve,ok
1:51,B,Dora,attack,error
"""


def parse_time(s):
    s = str(s).strip()
    if ":" in s:
        parts = [float(p) for p in s.split(":")]
        t = 0.0
        for p in parts:
            t = t * 60 + p
        return t
    return float(s)


def load_segments(path):
    df = pd.read_csv(path)
    return df[["rally", "start", "end", "duration"]].astype(float)


def load_events(path):
    df = pd.read_csv(path, dtype=str).fillna("")
    missing = {"time", "team", "player", "action", "result"} - set(df.columns)
    if missing:
        sys.exit(f"events.csv: Spalten fehlen: {', '.join(sorted(missing))}")
    df["t"] = df["time"].map(parse_time)
    df["team"] = df["team"].str.strip().str.upper()
    df["player"] = df["player"].str.strip()
    df["action"] = df["action"].str.strip().str.lower()
    df["res"] = df["result"].str.strip().str.lower().map(RESULTS)
    bad = df[~df["action"].isin(ACTIONS) | df["res"].isna()]
    if len(bad):
        sys.exit("events.csv: ungueltige Zeilen (action/result unbekannt):\n" + bad.to_string())
    return df.sort_values("t").reset_index(drop=True)


# ----------------------------------------------------------------- Rechnungen
def rally_stats(seg, video_length=None):
    d = seg["duration"]
    total = d.sum()
    length = video_length or float(seg["end"].max())
    return {
        "Ballwechsel": int(len(seg)),
        "Spielzeit gesamt (min)": round(total / 60, 1),
        "Anteil Spielzeit am Video (%)": round(100 * total / length, 1),
        "Dauer Mittel (s)": round(d.mean(), 1),
        "Dauer Median (s)": round(d.median(), 1),
        "Laengster Ballwechsel (s)": round(d.max(), 1),
        "Kuerzester Ballwechsel (s)": round(d.min(), 1),
    }


def duration_buckets(seg):
    bins = [0, 5, 10, 15, 20, 30, 1e9]
    labels = ["<5 s", "5-10 s", "10-15 s", "15-20 s", "20-30 s", ">30 s"]
    c = pd.cut(seg["duration"], bins=bins, labels=labels, right=False).value_counts().reindex(labels)
    return c.fillna(0).astype(int)


def player_stats(ev):
    rows = []
    for (team, player), g in ev.groupby(["team", "player"]):
        def n(action, res=None):
            m = g["action"] == action
            if res:
                m &= g["res"] == res
            return int(m.sum())
        att, kills, att_err = n("attack"), n("attack", "point"), n("attack", "error")
        serves, aces, serr = n("serve"), n("serve", "point"), n("serve", "error")
        rec, rec_err = n("receive"), n("receive", "error")
        blocks_pts = n("block", "point")
        rows.append({
            "Team": team, "Spieler": player,
            "Angriffe": att, "Kills": kills, "Angriffsfehler": att_err,
            "Angriffsquote %": round(100 * (kills - att_err) / att, 1) if att else None,
            "Aufschlaege": serves, "Asse": aces, "Aufschlagfehler": serr,
            "Annahmen": rec, "Annahmefehler": rec_err,
            "Blocks": n("block"), "Blockpunkte": blocks_pts,
            "Abwehr": n("dig"), "Zuspiele": n("set"),
            "Punkte": kills + aces + blocks_pts,
            "Fehler": int((g["res"] == "error").sum()),
        })
    return pd.DataFrame(rows).sort_values(["Team", "Punkte"], ascending=[True, False])


def team_stats(ev):
    pts = {"A": 0, "B": 0}
    by_cause = {"A": {"Aufschlag": 0, "Angriff": 0, "Block": 0, "Gegnerfehler": 0},
                "B": {"Aufschlag": 0, "Angriff": 0, "Block": 0, "Gegnerfehler": 0}}
    for _, r in ev.iterrows():
        if r["team"] not in pts or r["res"] == "ok":
            continue
        other = "B" if r["team"] == "A" else "A"
        if r["res"] == "point":
            pts[r["team"]] += 1
            key = {"serve": "Aufschlag", "attack": "Angriff", "block": "Block"}.get(r["action"], "Angriff")
            by_cause[r["team"]][key] += 1
        else:
            pts[other] += 1
            by_cause[other]["Gegnerfehler"] += 1
    return pts, by_cause


def check_rallies(ev, seg):
    """Warnt, wenn ein Ballwechsel mehrere punktgebende Ereignisse hat."""
    warns = []
    for _, r in seg.iterrows():
        m = ev[(ev["t"] >= r["start"]) & (ev["t"] <= r["end"]) & (ev["res"] != "ok")]
        if len(m) > 1:
            warns.append(f"Ballwechsel {int(r['rally'])}: {len(m)} punktgebende Ereignisse")
    return warns


# ----------------------------------------------------------------- HTML
CSS = """body{font-family:system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}
table{border-collapse:collapse;margin:.5rem 0 1.5rem}td,th{border:1px solid #ccc;padding:.3rem .6rem;text-align:right}
th{background:#f0f0f0}td:first-child,th:first-child{text-align:left}.score{font-size:2.4rem;font-weight:700}
.bar{background:#4a7;height:14px;display:inline-block}.warn{color:#a40}h2{margin-top:2rem}"""


def kv_table(d):
    return "<table>" + "".join(f"<tr><td>{html.escape(str(k))}</td><td>{v}</td></tr>" for k, v in d.items()) + "</table>"


def build_html(rs, buckets, pts, causes, pl, warns, has_events):
    h = [f"<!doctype html><meta charset=utf-8><title>Volleyball-Statistik</title><style>{CSS}</style>",
         "<h1>Volleyball-Statistik</h1>"]
    if rs:
        h.append("<h2>Ballwechsel (automatisch aus dem Video)</h2>" + kv_table(rs))
        mx = max(int(buckets.max()), 1)
        h.append("<table><tr><th>Dauer</th><th>Anzahl</th><th></th></tr>" + "".join(
            f"<tr><td>{k}</td><td>{v}</td><td style='text-align:left'><span class=bar style='width:{200 * v / mx:.0f}px'></span></td></tr>"
            for k, v in buckets.items()) + "</table>")
    if has_events:
        h.append(f"<h2>Spielstand (aus getaggten Ereignissen)</h2><p class=score>A {pts['A']} : {pts['B']} B</p>")
        h.append("<h3>Punkte nach Art</h3><table><tr><th>Team</th>" + "".join(f"<th>{k}</th>" for k in causes["A"]) + "</tr>" +
                 "".join(f"<tr><td>{t}</td>" + "".join(f"<td>{v}</td>" for v in causes[t].values()) + "</tr>" for t in ("A", "B")) + "</table>")
        h.append("<h2>Spielerstatistik</h2>" + pl.to_html(index=False, na_rep="-", border=0))
        h.append("<p>Angriffsquote = (Kills - Fehler) / Angriffe</p>")
    for w in warns:
        h.append(f"<p class=warn>Hinweis: {html.escape(w)}</p>")
    return "\n".join(h)


# ----------------------------------------------------------------- CLI
def generate_report(segments, events, outdir, video_length=None):
    """Erzeugt report.html und spielerstatistik.csv; gibt den Pfad zum Report zurueck."""
    if not segments and not events:
        sys.exit("Mindestens Segmente oder Ereignisse angeben.")
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    rs = buckets = None
    seg = load_segments(segments) if segments else None
    if seg is not None and len(seg):
        rs, buckets = rally_stats(seg, video_length), duration_buckets(seg)
        print("Ballwechsel:")
        for k, v in rs.items():
            print(f"  {k}: {v}")
    pts = causes = pl = None
    warns = []
    if events:
        ev = load_events(events)
        pts, causes = team_stats(ev)
        pl = player_stats(ev)
        pl.to_csv(out / "spielerstatistik.csv", index=False)
        print(f"\nSpielstand: A {pts['A']} : {pts['B']} B")
        print(pl.to_string(index=False))
        if seg is not None:
            warns = check_rallies(ev, seg)
            for w in warns:
                print("Hinweis:", w)
    (out / "report.html").write_text(build_html(rs, buckets, pts, causes, pl, warns, bool(events)), encoding="utf-8")
    print(f"\n-> {out / 'report.html'}")

    return out / "report.html"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("template")
    t.add_argument("-o", "--out", default="events.csv")
    r = sub.add_parser("report")
    r.add_argument("--segments")
    r.add_argument("--events")
    r.add_argument("--video-length", type=float, help="Videolaenge in s (sonst Ende des letzten Segments)")
    r.add_argument("-o", "--outdir", default="report")
    a = ap.parse_args()

    if a.cmd == "template":
        Path(a.out).write_text(TEMPLATE, encoding="utf-8")
        print(f"Vorlage geschrieben: {a.out}")
        return
    if not a.segments and not a.events:
        sys.exit("Mindestens --segments oder --events angeben.")

    generate_report(a.segments, a.events, a.outdir, a.video_length)

if __name__ == "__main__":
    main()
