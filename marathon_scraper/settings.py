"""Scrapy-Einstellungen für das Marathon-Projekt.

Alle Werte hier gelten für jeden Spider. Einzelne Werte lassen sich beim
Aufruf überschreiben, z.B.:  scrapy crawl results_list -s HTTPCACHE_ENABLED=False
"""

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

BOT_NAME = "marathon_scraper"
SPIDER_MODULES = ["marathon_scraper.spiders"]
NEWSPIDER_MODULE = "marathon_scraper.spiders"

# Wohin die SQLite-Datenbank geschrieben wird (wird von der Pipeline gelesen).
SQLITE_PATH = str(PROJECT_DIR / "data" / "marathon.db")

# --- Wie sieht unser Request aus? ------------------------------------------
# Der Server (AWS Load Balancer) antwortet auf Anfragen ohne "echten" Browser-
# User-Agent mit 403 Forbidden. Darum geben wir uns als normaler Browser aus.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

# robots.txt ist auf diesem Server selbst hinter dem 403-Filter und daher nicht
# lesbar. Normalerweise sollte man ROBOTSTXT_OBEY = True lassen!
ROBOTSTXT_OBEY = False

# --- Höflich crawlen ---------------------------------------------------------
# Wir wollen den Server nicht belasten: wenige parallele Requests, kleine Pause.
CONCURRENT_REQUESTS_PER_DOMAIN = 4
DOWNLOAD_DELAY = 0.25
# AutoThrottle misst die Antwortzeiten und bremst automatisch, wenn der Server
# langsamer wird. TARGET_CONCURRENCY = durchschnittlich gleichzeitige Requests.
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.5
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 3.0

# --- Fehlerbehandlung ---------------------------------------------------------
# Drei Ebenen, von "kurz gestört" bis "wir werden blockiert":
#
# 1. Timeout: Antwortet der Server 30 s lang nicht, gilt der Request als
#    gescheitert (Standard wären 180 s).
DOWNLOAD_TIMEOUT = 30
#
# 2. Retry (eingebaute RetryMiddleware): Timeouts, Verbindungsfehler und
#    500/502/504 werden bis zu 3-mal sofort wiederholt. Klappt es dann immer
#    noch nicht, ruft Scrapy den errback des Spiders auf -> Tabelle `failures`.
RETRY_ENABLED = True
RETRY_TIMES = 3
#
# 3. Backoff (unsere BackoffMiddleware, middlewares.py): Bei 429/503/403 bremst
#    der Server uns aus. Dann pausiert der ganze Crawl mit wachsender Wartezeit
#    (30 s, 60 s, 120 s, ... max. 10 min). Nach 6 Pausen in Folge ohne
#    Erfolg dazwischen wird sauber beendet (Grund "blocked").
BACKOFF_HTTP_CODES = [429, 503, 403]
BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 600
BACKOFF_MAX_STRIKES = 6

DOWNLOADER_MIDDLEWARES = {
    # 560 > 550 (RetryMiddleware): sieht die Antwort zuerst.
    "marathon_scraper.middlewares.BackoffMiddleware": 560,
}

# --- HTTP-Cache: der wichtigste Trick beim Entwickeln -----------------------
# Jede Antwort wird unter .scrapy/httpcache gespeichert. Wenn du einen Selektor
# änderst und den Spider neu startest, kommt die Seite aus dem Cache statt vom
# Server -> schnell und schont den Server. Cache löschen: rm -rf .scrapy/httpcache
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 0  # 0 = nie ablaufen
HTTPCACHE_DIR = "httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [403, 429, 500, 502, 503, 504]  # Fehler nicht cachen

# --- Item-Pipelines ----------------------------------------------------------
# Jedes Item, das ein Spider mit `yield` zurückgibt, läuft durch diese Pipelines
# (kleinere Zahl = früher). Unsere einzige Pipeline schreibt in SQLite.
ITEM_PIPELINES = {
    "marathon_scraper.pipelines.SQLitePipeline": 300,
}

# --- Logging + Fortschrittsanzeige ---------------------------------------------
# Das ausführliche Log geht in eine Datei. In der Konsole stehen nur der
# Fortschrittsbalken plus Warnungen/Fehler (siehe extensions.py).
# Alles wie gewohnt in der Konsole: -s LOG_FILE= -s PROGRESS_ENABLED=False
LOG_LEVEL = "INFO"
LOG_FILE = str(PROJECT_DIR / "logs" / "scrapy.log")
(PROJECT_DIR / "logs").mkdir(exist_ok=True)
LOGSTATS_INTERVAL = 60  # schreibt jede Minute "Crawled X pages ..." ins Log

PROGRESS_ENABLED = True
EXTENSIONS = {
    "marathon_scraper.extensions.ProgressExtension": 500,
}
FEED_EXPORT_ENCODING = "utf-8"
