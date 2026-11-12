"""Weboberflaeche der App als eingebettetes HTML (Platzhalter __TOKEN__ wird beim Ausliefern ersetzt)."""

INDEX_HTML = r"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Volleyball Tool</title>
<style>
:root{--bg:#f5f6f8;--card:#fff;--ink:#1b2430;--mute:#5d6b7c;--line:#dde2e8;--acc:#1f6feb;--acc2:#e8f0fe;--ok:#1a7f37;--bad:#b42318}
@media (prefers-color-scheme:dark){:root{--bg:#12171d;--card:#1b222b;--ink:#e6ebf1;--mute:#97a3b3;--line:#2c3643;--acc:#5b9bff;--acc2:#1d2a3f;--ok:#4cc26b;--bad:#ff7b72}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{display:flex;align-items:center;gap:1rem;padding:.8rem 1.2rem;background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
header h1{font-size:1.1rem;margin:0}
nav{display:flex;gap:.4rem;margin-left:auto}
button{font:inherit;cursor:pointer;border:1px solid var(--line);background:var(--card);color:var(--ink);padding:.45rem .9rem;border-radius:8px}
button:hover{border-color:var(--acc)}
button.on{background:var(--acc2);border-color:var(--acc);color:var(--acc)}
button.primary{background:var(--acc);border-color:var(--acc);color:#fff}
button:disabled{opacity:.5;cursor:default}
main{max-width:980px;margin:1.2rem auto;padding:0 1rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1rem 1.2rem;margin-bottom:1rem}
.card h2{font-size:1rem;margin:0 0 .6rem}
label{display:block;font-size:.85rem;color:var(--mute);margin:.5rem 0 .2rem}
input,textarea{font:inherit;width:100%;padding:.45rem .6rem;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
textarea{font-family:ui-monospace,Consolas,monospace;font-size:.85rem;min-height:190px}
.row{display:flex;gap:.5rem;align-items:center}.row input{flex:1}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:.4rem .8rem}
details{margin:.6rem 0}summary{cursor:pointer;color:var(--acc)}
.hint{font-size:.8rem;color:var(--mute);margin:.2rem 0 0}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:.6rem;max-height:210px;overflow:auto;font-size:.8rem;white-space:pre-wrap;margin:.5rem 0 0}
img.tl{width:100%;border:1px solid var(--line);border-radius:8px;background:#fff}
table{width:100%;border-collapse:collapse;margin:.6rem 0}
th,td{padding:.25rem .4rem;border-bottom:1px solid var(--line);text-align:left}
td input{width:90px;padding:.2rem .4rem}
.sum{font-size:1.05rem;margin:.2rem 0 .6rem}
.msg{margin-top:.6rem;font-weight:600}.msg.ok{color:var(--ok)}.msg.bad{color:var(--bad);white-space:pre-wrap}
iframe{width:100%;height:640px;border:1px solid var(--line);border-radius:8px;background:#fff}
.right{margin-left:auto}
</style>
</head>
<body>
<header>
  <h1>🏐 Volleyball Tool</h1>
  <nav>
    <button class="on" data-tab="cut">Video kürzen</button>
    <button data-tab="stats">Statistik</button>
    <button id="quit">Beenden</button>
  </nav>
</header>
<main>
<section id="tab-cut">
  <div class="card">
    <h2>1. Video wählen und Ballwechsel erkennen</h2>
    <label for="video">Videodatei</label>
    <div class="row"><input id="video" placeholder="Pfad zur Videodatei, z. B. C:\Videos\spiel.mp4"><button id="browse">Durchsuchen …</button></div>
    <details>
      <summary>Einstellungen (optional)</summary>
      <div class="grid">
        <div><label for="p_gap">Pausen bis (s) gelten als Spiel</label><input id="p_gap" type="number" step="0.5" value="6"></div>
        <div><label for="p_min_len">Mindestlänge Ballwechsel (s)</label><input id="p_min_len" type="number" step="0.5" value="3"></div>
        <div><label for="p_pre">Vorlauf (s)</label><input id="p_pre" type="number" step="0.5" value="2"></div>
        <div><label for="p_post">Nachlauf (s)</label><input id="p_post" type="number" step="0.5" value="1.5"></div>
        <div><label for="p_audio_weight">Audio-Anteil (0 bis 1)</label><input id="p_audio_weight" type="number" step="0.1" min="0" max="1" value="0.4"></div>
        <div><label for="p_threshold">Feste Schwelle (leer = automatisch)</label><input id="p_threshold" type="number" step="0.01" min="0" max="1"></div>
      </div>
      <label for="p_roi">Spielfeld-Ausschnitt (x0,y0,x1,y1 als Bruchteile, leer = ganzes Bild)</label>
      <input id="p_roi" placeholder="z. B. 0.1,0.25,0.9,1">
      <p class="hint">Ein Ausschnitt hilft, wenn im Hintergrund viel Bewegung ist (Zuschauer, Nebenfelder).</p>
    </details>
    <button id="analyze" class="primary">Ballwechsel erkennen</button>
    <div id="msg-cut" class="msg"></div>
  </div>

  <div class="card" id="result" hidden>
    <h2>2. Ergebnis prüfen und schneiden</h2>
    <div class="sum" id="summary"></div>
    <img class="tl" id="timeline" alt="Timeline">
    <p class="hint">Orange = Bewegung, blau = Audio, schwarz = Score, rot = Schwelle, grün = erkanntes Spiel.</p>
    <table>
      <thead><tr><th>#</th><th>Start (s)</th><th>Ende (s)</th><th>Dauer</th><th></th></tr></thead>
      <tbody id="segs"></tbody>
    </table>
    <div class="row">
      <button id="addseg">+ Segment</button>
      <button id="cut" class="primary right">Video schneiden</button>
    </div>
    <div id="msg-out" class="msg"></div>
    <button id="reveal" hidden>Ordner öffnen</button>
  </div>

  <div class="card"><h2>Protokoll</h2><pre id="log">Noch nichts gelaufen.</pre></div>
</section>

<section id="tab-stats" hidden>
  <div class="card">
    <h2>Statistik</h2>
    <p class="hint">Ballwechsel-Statistik kommt automatisch aus der letzten Erkennung. Für Spieler- und Teamwerte trägst du Aktionen ein
    (Spalten: <code>time,team,player,action,result</code>) oder lädst eine CSV-Datei.</p>
    <textarea id="events" placeholder="time,team,player,action,result&#10;0:22,A,Fiona,attack,point"></textarea>
    <div class="row" style="margin-top:.6rem">
      <button id="tpl">Vorlage einfügen</button>
      <button id="loadcsv">CSV laden …</button><input type="file" id="csvfile" accept=".csv,text/csv" hidden>
      <button id="report" class="primary right">Report erstellen</button>
    </div>
    <div id="msg-stats" class="msg"></div>
    <pre id="statlog" hidden></pre>
  </div>
  <div class="card" id="reportcard" hidden>
    <h2>Report</h2>
    <iframe id="reportframe"></iframe>
    <div class="row" style="margin-top:.6rem"><button id="revealreport">Report-Ordner öffnen</button></div>
  </div>
</section>
</main>

<script>
const T = "__TOKEN__";
const $ = s => document.querySelector(s);
const TEMPLATE = `time,team,player,action,result
0:12,A,Anna,serve,ok
0:14,B,Berta,receive,ok
0:16,B,Clara,set,ok
0:17,B,Dora,attack,ok
0:18,A,Eva,dig,ok
0:20,A,Fiona,attack,point
1:05,B,Berta,serve,point
1:48,A,Anna,serve,ok
1:51,B,Dora,attack,error
`;
let segs = [];
let timer = null;

async function api(path, body) {
  const opts = body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  const r = await fetch(path + (path.includes("?") ? "&" : "?") + "t=" + T, opts);
  let j = {};
  try { j = await r.json(); } catch (e) { j = {error: "Ungültige Antwort der App"}; }
  if (!r.ok) throw new Error(j.error || ("Fehler " + r.status));
  return j;
}
function say(id, text, cls) { const e = $(id); e.textContent = text || ""; e.className = "msg " + (cls || ""); }
function fmt(t) {
  const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = (t % 60).toFixed(1);
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + s.padStart(4, "0");
}

// Tabs
document.querySelectorAll("nav [data-tab]").forEach(b => b.onclick = () => {
  document.querySelectorAll("nav [data-tab]").forEach(x => x.classList.toggle("on", x === b));
  $("#tab-cut").hidden = b.dataset.tab !== "cut";
  $("#tab-stats").hidden = b.dataset.tab !== "stats";
});

// Lebenszeichen, damit sich die App nach Schließen des Tabs beendet
setInterval(() => api("/api/ping").catch(() => {}), 5000);
api("/api/ping").catch(() => {});

$("#quit").onclick = async () => {
  try { await api("/api/quit", {}); } catch (e) {}
  document.body.innerHTML = "<p style='padding:2rem;font:16px system-ui'>Volleyball Tool wurde beendet. Du kannst dieses Fenster schließen.</p>";
};

$("#browse").onclick = async () => {
  try {
    const j = await api("/api/browse", {});
    if (j.available) { if (j.path) $("#video").value = j.path; }
    else say("#msg-cut", "Dateidialog nicht verfügbar. Bitte den Pfad der Videodatei einfügen.", "bad");
  } catch (e) { say("#msg-cut", e.message, "bad"); }
};

function params() {
  const g = id => $(id).value.trim();
  return {gap: g("#p_gap"), min_len: g("#p_min_len"), pre: g("#p_pre"), post: g("#p_post"),
          audio_weight: g("#p_audio_weight"), threshold: g("#p_threshold"), roi: g("#p_roi")};
}

function poll(onDone) {
  clearInterval(timer);
  timer = setInterval(async () => {
    try {
      const j = await api("/api/job");
      const log = $("#log"); log.textContent = j.log || "…"; log.scrollTop = log.scrollHeight;
      if (j.status !== "running") {
        clearInterval(timer);
        $("#analyze").disabled = false; $("#cut").disabled = false;
        if (j.status === "error") onDone(null, j.error); else onDone(j.result);
      }
    } catch (e) { clearInterval(timer); say("#msg-cut", e.message, "bad"); }
  }, 700);
}

$("#analyze").onclick = async () => {
  say("#msg-cut", "");
  $("#analyze").disabled = true;
  try {
    await api("/api/analyze", {video: $("#video").value, params: params()});
  } catch (e) { $("#analyze").disabled = false; return say("#msg-cut", e.message, "bad"); }
  poll(async (res, err) => {
    if (err) return say("#msg-cut", err, "bad");
    const s = await api("/api/segments");
    segs = s.segments;
    $("#summary").textContent = res.count + " Ballwechsel erkannt, behalten: " + (res.kept / 60).toFixed(1) +
      " von " + (res.duration / 60).toFixed(1) + " min (" + Math.round(100 * res.kept / res.duration) + " %)";
    $("#timeline").src = "/timeline.png?t=" + T + "&r=" + Date.now();
    $("#result").hidden = false;
    $("#reveal").hidden = true; say("#msg-out", "");
    renderSegs();
    say("#msg-cut", "Fertig. Bitte unten prüfen und bei Bedarf Zeiten anpassen.", "ok");
  });
};

function renderSegs() {
  $("#segs").innerHTML = segs.map((s, i) =>
    `<tr><td>${i + 1}</td><td><input type="number" step="0.5" min="0" value="${s[0].toFixed(1)}" data-i="${i}" data-k="0"></td>` +
    `<td><input type="number" step="0.5" min="0" value="${s[1].toFixed(1)}" data-i="${i}" data-k="1"></td>` +
    `<td>${fmt(Math.max(0, s[1] - s[0]))}</td><td><button data-del="${i}">Entfernen</button></td></tr>`).join("");
  document.querySelectorAll("#segs input").forEach(inp => inp.onchange = () => {
    segs[+inp.dataset.i][+inp.dataset.k] = parseFloat(inp.value) || 0; renderSegs();
  });
  document.querySelectorAll("#segs [data-del]").forEach(b => b.onclick = () => { segs.splice(+b.dataset.del, 1); renderSegs(); });
}

$("#addseg").onclick = () => {
  const last = segs.length ? segs[segs.length - 1][1] : 0;
  segs.push([last + 5, last + 15]); renderSegs();
};

$("#cut").onclick = async () => {
  say("#msg-out", "");
  $("#cut").disabled = true;
  try { await api("/api/cut", {segments: segs}); }
  catch (e) { $("#cut").disabled = false; return say("#msg-out", e.message, "bad"); }
  poll((res, err) => {
    if (err) return say("#msg-out", err, "bad");
    say("#msg-out", "Gespeichert: " + res.output, "ok");
    $("#reveal").hidden = false;
  });
};
$("#reveal").onclick = () => api("/api/reveal", {}).catch(e => say("#msg-out", e.message, "bad"));

// Statistik
$("#tpl").onclick = () => { $("#events").value = TEMPLATE; };
$("#loadcsv").onclick = () => $("#csvfile").click();
$("#csvfile").onchange = e => {
  const f = e.target.files[0]; if (!f) return;
  const r = new FileReader(); r.onload = () => { $("#events").value = r.result; }; r.readAsText(f);
};
$("#report").onclick = async () => {
  say("#msg-stats", ""); $("#statlog").hidden = true;
  try {
    const j = await api("/api/stats", {events: $("#events").value});
    $("#statlog").textContent = j.console; $("#statlog").hidden = false;
    $("#reportframe").src = "/report?t=" + T + "&r=" + Date.now();
    $("#reportcard").hidden = false;
    say("#msg-stats", "Report erstellt.", "ok");
  } catch (e) { say("#msg-stats", e.message, "bad"); }
};
$("#revealreport").onclick = () => api("/api/reveal", {target: "report"}).catch(e => say("#msg-stats", e.message, "bad"));
</script>
</body>
</html>
"""
