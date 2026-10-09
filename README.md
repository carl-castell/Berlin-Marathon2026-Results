# Berlin Marathon 2026 – Scraping mit Scrapy, Analyse mit Polars + marimo

Die Ergebnisse von <https://berlin.r.mikatiming.com/2026/> werden mit Scrapy in
`data/marathon.db` (SQLite) gespeichert und in `notebooks/analyse.py` ausgewertet.

> Die Ergebnisliste ist urheberrechtlich geschützt und laut Seite nur für private
> Informationszwecke gedacht. Die Daten deshalb nur privat nutzen und nicht
> weiterveröffentlichen. Und rücksichtsvoll crawlen (siehe Settings).

**Dieses Repository enthält nur den Code, keine Daten.** `data/`, der HTTP-Cache
(`.scrapy/`) und die Logs sind per `.gitignore` ausgeschlossen. Die Datenbank
erzeugst du mit den beiden Spidern selbst neu (siehe unten).

## Schnellstart

```bash
uv sync                                       # Abhängigkeiten installieren

# Schritt 1: Ergebnislisten (~500 Seiten, ca. 5 Minuten)
uv run scrapy crawl results_list
uv run scrapy crawl results_list -a sex=W -a max_pages=2   # kleiner Test

# Schritt 2: Detailseiten + Splits (~50.000 Seiten, ca. 4–4,5 Stunden)
uv run scrapy crawl results_detail -a limit=20             # kleiner Test
caffeinate -i uv run scrapy crawl results_detail          # alles, was noch fehlt (caffeinate: Mac schläft nicht ein)

# Analyse
uv run marimo edit notebooks/analyse.py
```

Schritt 2 kann jederzeit mit **Ctrl-C** abgebrochen und neu gestartet werden. Der
Spider lädt nur Läufer, die noch keine Zeile in `details` haben.

### Reproduzieren und prüfen

Python-Version (`.python-version`) und alle Paketversionen (`uv.lock`) sind fest,
`uv sync` installiert also genau dieselbe Umgebung. Bei einem Lauf am 2026-10-09
kam heraus:

| Tabelle | Zeilen |
|---|---|
| `runners` | 50.084 (M 32.090 · W 17.941 · X 53) |
| `details` | 50.084 |
| `splits` | 500.840 (10 pro Läufer) |
| `failures` | 0 |

Die Ergebnisse sind laut Seite noch „inoffiziell“. Werden sie später korrigiert
(z.B. Disqualifikationen), können die Zahlen bei einem neuen Lauf leicht abweichen.

Vollständigkeit prüfen:

```bash
sqlite3 -header -column data/marathon.db "
select (select count(*) from runners) runners,
       (select count(*) from details) details,
       (select count(*) from runners r where not exists
          (select 1 from details d where d.idp = r.idp)) ohne_details,
       (select count(*) from splits) splits,
       (select count(*) from failures) failures;"
```

`ohne_details` und `failures` müssen 0 sein. Sonst `results_detail` einfach
nochmal starten, er holt nur die fehlenden Läufer.

Bekannte Eigenheiten der Daten:
- Bei ~1.100 Läufern fehlen einzelne Zwischenzeiten und die Halbmarathonzeiten
  (Chip an einer Matte nicht erfasst). Die Zielzeit haben alle.
- Gleichstand: Zwei Läufer mit gleicher Zeit teilen sich einen Platz, der
  nächste Platz wird übersprungen. Zusätzlich fehlen 13 Platznummern ganz in
  der Liste der Seite (vermutlich nachträglich entfernte Läufer).

Backup der Datenbank (konsistent, auch während sie geöffnet ist):

```bash
sqlite3 data/marathon.db ".backup data/marathon_backup_$(date +%F).db"
```

### Was du in der Konsole siehst

```
Details ━━━━━━━━╸            28% 13.912/50.084 ⏱ 0:54:10 ⏳ 2:21:30 4.3/s ✓
```

Das sind: Fortschritt in %, erledigt/gesamt, ⏱ bisherige Dauer, ⏳ geschätzte
Restzeit (aus der Rate der letzten Minute) und Seiten pro Sekunde. Ganz rechts
steht der Status: ✓, Anzahl Fehler, wie oft gebremst wurde, oder
„⏸ Pause wegen Rate-Limit, noch 42 s“. Warnungen erscheinen über dem Balken. Am
Ende kommt eine Zusammenfassung. Das ausführliche Log steht in `logs/scrapy.log`
(`tail -f logs/scrapy.log` in einem zweiten Terminal).

### Was passiert bei Problemen?

| Problem | Reaktion |
|---|---|
| Server antwortet nicht (30 s) / Verbindungsfehler / 500, 502, 504 | bis zu 3 Retries, danach Eintrag in Tabelle `failures` |
| **429 / 503 / 403** (Rate-Limit, Blockade) | ganzer Crawl pausiert 30 s → 60 s → 120 s … (max. 10 min, `Retry-After` wird beachtet), Request wird danach neu eingeplant, es geht nichts verloren |
| 6 Pausen in Folge ohne Erfolg | sauberes Ende mit „vom Server blockiert“, später einfach neu starten |
| Ctrl-C (einmal) | laufende Requests werden fertig, DB wird gespeichert, Ende |
| Ctrl-C (zweimal) | sofortiger Abbruch (bereits committete Daten bleiben) |
| falscher Geschlechter-Filter | Abbruch mit Fehlermeldung (die Seite würde sonst still die Männer liefern) |

Fehlgeschlagene Seiten: `sqlite3 data/marathon.db 'select * from failures'`.
Der Detail-Spider holt sie beim nächsten Start automatisch nach.

Einstellungen dazu stehen in `settings.py` (`BACKOFF_*`, `RETRY_*`, `DOWNLOAD_TIMEOUT`).

## Projektstruktur

```
scrapy.cfg                      Markiert das Scrapy-Projekt
marathon_scraper/
  settings.py                   User-Agent, Drosselung, Cache, Pipeline
  site.py                       URLs/Parameter der Seite + kleine Parse-Helfer
  items.py                      Datenstrukturen: RunnerItem, DetailItem, SplitItem
  pipelines.py                  Schreibt Items per UPSERT in SQLite
  middlewares.py                Backoff bei Rate-Limiting (429/503/403)
  extensions.py                 Fortschrittsbalken + Zusammenfassung (rich)
  spiders/base.py               Basisklasse: Fortschritt zählen, errback
  spiders/results_list.py       Schritt 1: Listen (100 pro Seite, M/W/X)
  spiders/results_detail.py     Schritt 2: Detailseiten
notebooks/analyse.py            marimo-Notebook
data/marathon.db                Ergebnis (Tabellen runners, details, splits, failures)
logs/scrapy.log                 ausführliches Log
```

**Datenmodell:** `runners` (1 Zeile pro Läufer, Schlüssel `idp`; `sex` = M/W/X,
X = divers; Name getrennt in `last_name`, `first_name`, `nation`) → `details`
(1:1) und `splits` (1:n, *long format*: eine Zeile pro Läufer und Messpunkt).

---

## Lern-Notizen: Web-Scraping

### 1. Welche Ansätze gibt es?

| Ansatz | Wann? | Werkzeuge |
|---|---|---|
| **Verstecktes JSON-API finden** | Immer zuerst prüfen. Browser-DevTools → Netzwerk → Fetch/XHR. Lädt die Seite ihre Daten als JSON nach, kann man das API direkt abfragen. Das ist am saubersten. | `httpx`/`requests` |
| **HTML direkt laden + parsen** | Die Daten stehen schon im HTML, das der Server schickt (Rechtsklick → *Seitenquelltext anzeigen* zeigt sie). | `requests` + `BeautifulSoup`/`lxml`, oder **Scrapy** |
| **Browser fernsteuern** | Die Daten entstehen erst durch JavaScript, oder man muss sich einloggen, klicken oder scrollen. Langsam und ressourcenhungrig. | Playwright, Selenium, `scrapy-playwright` |
| **Fertige Exporte** | Manche Seiten bieten CSV/PDF-Downloads an. | – |

Für diese Seite trifft der zweite Ansatz zu: Das HTML enthält alle Daten, es gibt
kein JSON-API und JavaScript ist nicht nötig.

**requests + BeautifulSoup oder Scrapy?** Für 1 bis 10 Seiten ist ein kleines
Skript mit requests einfacher. Ab ein paar hundert Seiten zahlt sich Scrapy aus.
Es bringt mit: parallele Requests, Drosselung, Retries, Cache, Duplikatfilter,
Pipelines und Logging/Statistiken.

### 2. Vorgehen bei einer neuen Seite

1. **Im Browser erkunden:** Welche URL-Parameter ändern sich beim Blättern oder
   Filtern? Hier: `num_results=100`, `search[sex]=W`, `page=N`. Funktioniert die
   URL auch direkt, also ohne Formular und Cookies? Hier ja.
2. **Mit curl/Scrapy testen:** Bekommt man dasselbe HTML wie im Browser? Hier
   kam zuerst **403 Forbidden**. Der Server verlangt einen Browser-User-Agent
   (siehe `settings.py`).
3. **Selektoren in der `scrapy shell` entwickeln** (siehe unten).
4. **Klein anfangen** (`max_pages=2`, `limit=20`), Daten prüfen, dann alles laden.

### 3. Scrapy-Konzepte (mit Fundstelle im Code)

- **Spider** (`spiders/*.py`): Klasse mit `name`, Einstieg `async def start()`
  (seit Scrapy 2.13, früher `start_requests()`), und **Callbacks** wie `parse()`.
- **Request → Response → Callback:** Ein Callback bekommt die Antwort und
  liefert mit `yield` beliebig viele **Items** (Daten) *und/oder* neue
  **Requests**. So entsteht der Crawl. Siehe `ResultsListSpider.parse`: Es gibt
  100 Items aus und auf Seite 1 zusätzlich Requests für alle weiteren Seiten.
- **`cb_kwargs`:** Damit gibt man Kontext an den Callback weiter (hier `sex`, `page`, `idp`).
- **Selektoren:**
  - CSS: `response.css("h4.type-fullname a::text").get()`
  - `::text` liefert Text, `::attr(href)` ein Attribut (oder `.attrib["href"]`)
  - `.get()` liefert den ersten Treffer, `.getall()` alle
  - XPath kann mehr als CSS, z.B. „Text, aber nicht aus dem Label-div“:
    `.//text()[not(ancestor::div[contains(@class,'list-label')])]`
  - Am besten an **stabilen Klassen** festmachen, nicht an Positionen. Die
    Detailseite hat z.B. `td.f-place_all` mit Feldnamen, die nicht von der Sprache abhängen.
- **Items** (`items.py`): Dataclasses mit festen Feldern.
- **Item-Pipelines** (`pipelines.py`): verarbeiten jedes Item, hier mit
  Speichern in SQLite. Lebenszyklus: `open_spider` → `process_item` → `close_spider`.
- **Settings** (`settings.py`), überschreibbar mit `-s NAME=WERT`.
- **Spider-Argumente:** `-a key=value` kommt im `__init__` als String an.
- **Duplikatfilter:** Scrapy lädt dieselbe URL pro Lauf nur einmal (`dont_filter=True` schaltet das ab).

### 4. Höflich und robust crawlen

- `DOWNLOAD_DELAY`, `CONCURRENT_REQUESTS_PER_DOMAIN`, `AUTOTHROTTLE_*`: so bleibt die Last gering.
- `RETRY_TIMES`: wiederholt Requests bei Timeouts und 5xx-Fehlern.
- **`HTTPCACHE_ENABLED`**: Jede Antwort landet in `.scrapy/httpcache/`. Ändert man
  einen Selektor und startet neu, kommt alles aus dem Cache: sekundenschnell und
  ohne den Server zu belasten. Für frische Daten `rm -rf .scrapy/httpcache` oder
  `-s HTTPCACHE_ENABLED=False`.
- Pausieren/Fortsetzen geht allgemein mit `-s JOBDIR=jobs/detail`: Scrapy speichert dann
  die Warteschlange auf der Platte. Hier braucht man es nicht, weil der
  Detail-Spider selbst in der DB nachsieht, was fehlt.

### 5. `scrapy shell`: Selektoren interaktiv ausprobieren

```bash
uv run scrapy shell 'https://berlin.r.mikatiming.com/2026/?pid=list&event=BML_HCH3C0OH37C&num_results=100&search%5Bsex%5D=W&page=1'
```
```python
>>> rows = response.css("li.list-group-item.row:not(.list-group-header)")
>>> len(rows)                                   # 100
>>> rows[0].css("h4.type-fullname a::text").get()
'Assefa, Tigst (ETH)'
>>> view(response)                              # Antwort im Browser öffnen
>>> fetch("<andere URL>")                       # neue Seite laden
```

Wichtig: Die Shell verwendet die Projekt-Settings (User-Agent, Cache) nur, wenn
man sie im Projektordner startet.

### 6. Kleiner Trick der Seite: `data-silver`

Die Blätter-Links haben kein `href`, sondern `data-silver="63,112,97,103,101,..."`.
Das sind ASCII-Codes (`63` = `?`, `112` = `p`, …), aus denen JavaScript den Link
baut. `site.decode_silver()` dekodiert sie. Wir lesen daraus nur die höchste
Seitenzahl und erzeugen die URLs selbst.

Noch eine Falle: Der Geschlechter-Filter ist auf der Seite ein Freitextfeld.
`M`, `W` und `X` (divers) funktionieren. Jeder andere Wert (z.B. `D`) wird
**stillschweigend ignoriert**, und die Seite zeigt dann die Männer. Gefunden
habe ich `X` durch Ausprobieren. Der Spider prüft deshalb `<div data-sex="…">`
auf jeder Seite. Lehre: Immer prüfen, ob ein Filter wirklich greift!

### 7. Scrapy erweitern: Middleware, Extension, Signale

- **Downloader-Middleware** (`middlewares.py`) sitzt zwischen Engine und
  Downloader und sieht jeden Request und jede Response. Sie kann Antworten
  verändern oder Requests neu einplanen (`return request`). Die Reihenfolge
  steuert die Zahl in `DOWNLOADER_MIDDLEWARES`.
- **Extension** (`extensions.py`) reagiert auf **Signale** wie `spider_opened`
  oder `spider_closed`, hier für die Fortschrittsanzeige.
- **Stats** (`crawler.stats`): ein gemeinsames Zähler-Dictionary. Die Spider
  zählen `progress/done`, die Extension liest es. Alle Stats stehen am Ende im Log.
- **errback**: Gegenstück zum Callback für Requests, die endgültig scheitern.

### 8. Warum SQLite und nicht CSV?

- Mehrere Tabellen mit Schlüsseln, verknüpfbar per SQL-JOIN.
- **UPSERT** (`INSERT … ON CONFLICT DO UPDATE`): Wiederholte Läufe erzeugen keine Duplikate.
- Fortsetzen nach Abbruch: einfach per SQL abfragen, was fehlt.
- Polars liest es direkt: `pl.read_database("SELECT …", sqlite3.connect(db))`.
- Für schnelle Exporte gibt es trotzdem die Scrapy-Feeds:
  `uv run scrapy crawl results_list -O runners.csv` (oder `.jsonl`/`.parquet` über Polars).

Zeiten stehen bewusst als Text in der DB, so wie sie auf der Seite erscheinen.
Umgewandelt wird erst in Polars. So geht beim Scrapen nichts verloren, und
Umrechnungsfehler lassen sich beheben, ohne neu zu scrapen.
