# Volleyball Tool

Desktop-App, die Volleyball-Spielvideos automatisch kürzt (Spielpausen werden herausgeschnitten) und Statistiken erstellt. Alles läuft lokal auf deinem Rechner, es wird nichts hochgeladen.

## Download

Fertige Programme findest du unter **Releases** (rechte Seite auf GitHub):

| System | Datei | Start |
|---|---|---|
| Windows | `VolleyballTool-Windows.zip` | entpacken, `VolleyballTool\VolleyballTool.exe` starten |
| macOS | `VolleyballTool-macOS.zip` | entpacken, `VolleyballTool.app` starten |
| Linux | `VolleyballTool-Linux.tar.gz` | entpacken, `VolleyballTool/VolleyballTool` starten |

Beim Start öffnet sich die Oberfläche im Browser. Zum Beenden den Button **Beenden** verwenden (oder den Tab schließen, die App beendet sich dann nach etwa 3 Minuten selbst).

Hinweise zu Sicherheitswarnungen: Die Programme sind nicht signiert. Windows zeigt evtl. „Der Computer wurde durch Windows geschützt“ (auf *Weitere Informationen* → *Trotzdem ausführen* klicken). Unter macOS beim ersten Start Rechtsklick auf die App → *Öffnen*.

## Benutzung

**Video kürzen**
1. Videodatei auswählen (Button *Durchsuchen* oder Pfad einfügen).
2. *Ballwechsel erkennen* klicken. Das dauert je nach Videolänge einige Minuten.
3. Timeline und Segmenttabelle prüfen, Zeiten bei Bedarf anpassen, Segmente entfernen oder hinzufügen.
4. *Video schneiden* klicken. Das Ergebnis liegt im Ordner `VolleyballTool/<Videoname>/` in deinem Benutzerordner (Button *Ordner öffnen*).

**Statistik**
- Ballwechsel-Statistik (Anzahl, Dauer, Spielzeitanteil) entsteht automatisch aus der letzten Erkennung.
- Spieler- und Teamwerte entstehen aus Aktionen, die du einträgst: Spalten `time,team,player,action,result`
  - `action`: `serve`, `receive`, `set`, `attack`, `block`, `dig`, `freeball`
  - `result`: `point` (Punkt für das Team), `error` (Fehler, Punkt für den Gegner), `ok` (weiter)
  - Pro Ballwechsel genau ein Ereignis mit `point` oder `error` eintragen.
- *Vorlage einfügen* zeigt ein Beispiel, *CSV laden* liest eine Datei ein.

## Wichtige Einstellungen

| Einstellung | Wirkung |
|---|---|
| Pausen bis (s) gelten als Spiel | kleiner = mehr Schnitte, größer = Ballwechsel werden zusammengefasst |
| Mindestlänge | kürzere Segmente werden verworfen |
| Vorlauf / Nachlauf | Sekunden vor und nach jedem Ballwechsel |
| Audio-Anteil | 0 = nur Bild, 1 = nur Ton |
| Spielfeld-Ausschnitt | begrenzt die Bildanalyse auf das Feld (hilft bei viel Hintergrundbewegung) |

## Grenzen

Das ist ein Prototyp mit klassischer Bild- und Audioverarbeitung, **kein** trainiertes KI-Modell.

- Die Ballwechsel-Erkennung ist eine Heuristik (Bewegung + Ton). Prüfe das Ergebnis immer in der Timeline. Schwierig sind wackelnde Kameras, sehr laute Hallen und Nebenfelder im Bild.
- Die App sieht den Ball nicht und erkennt keine einzelnen Aktionen. Spielerstatistiken kommen deshalb aus den eingetragenen Ereignissen.

## Auf GitHub veröffentlichen (einmalig)

1. Auf github.com ein neues Repository anlegen, z. B. `volleyball-tool` (leer, ohne README).
2. Diesen Ordner hochladen. Mit Git:
   ```
   git init
   git add .
   git commit -m "Erste Version"
   git branch -M main
   git remote add origin https://github.com/<dein-name>/volleyball-tool.git
   git push -u origin main
   ```
   Ohne Git: im neuen Repository *uploading an existing file* wählen und den **Inhalt** des Ordners per Drag and Drop hineinziehen (auch den versteckten Ordner `.github`, sonst läuft der Build nicht).
3. Release mit Downloads erzeugen:
   ```
   git tag v1.0.0
   git push origin v1.0.0
   ```
   Auf GitHub baut danach der Reiter **Actions** automatisch die Programme für Windows, macOS und Linux (ca. 10 bis 15 Minuten) und hängt sie an den neuen Eintrag unter **Releases**.
   Alternativ: *Actions* → *Build Desktop-App* → *Run workflow*. Dann liegen die Dateien als *Artifacts* am Lauf.

## Aus dem Quellcode starten (ohne Build)

Python 3.10+ und `pip install -r requirements.txt`, dann:

```
python3 app.py
```

Test: `python3 tests/test_app.py` (erzeugt ein Testvideo und spielt den ganzen Ablauf durch).

## Kommandozeile

Die Kernfunktionen laufen auch ohne Oberfläche:

```
python3 rallycut.py auto spiel.mp4 -o ausgabe/
python3 volleyball_stats.py report --segments ausgabe/segments.csv --events events.csv -o report/
```
