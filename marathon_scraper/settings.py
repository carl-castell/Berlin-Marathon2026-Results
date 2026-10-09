"""Scrapy settings for the marathon project.

All values apply to every spider. Individual values can be overridden on the
command line, e.g.:  scrapy crawl results_list -s HTTPCACHE_ENABLED=False
"""

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

BOT_NAME = "marathon_scraper"
SPIDER_MODULES = ["marathon_scraper.spiders"]
NEWSPIDER_MODULE = "marathon_scraper.spiders"

# Where the SQLite database is written (read by the pipeline).
SQLITE_PATH = str(PROJECT_DIR / "data" / "marathon.db")

# --- What our requests look like ---------------------------------------------
# The server (AWS load balancer) answers requests without a "real" browser
# user agent with 403 Forbidden. So we identify as a regular browser.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

# robots.txt is itself behind the 403 filter on this server and therefore
# unreadable. Normally you should keep ROBOTSTXT_OBEY = True!
ROBOTSTXT_OBEY = False

# --- Crawl politely ------------------------------------------------------------
# We don't want to put load on the server: few parallel requests, a small delay.
CONCURRENT_REQUESTS_PER_DOMAIN = 4
DOWNLOAD_DELAY = 0.25
# AutoThrottle measures response times and slows down automatically when the
# server gets slower. TARGET_CONCURRENCY = average number of parallel requests.
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.5
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 3.0

# --- Error handling --------------------------------------------------------------
# Three levels, from "briefly disrupted" to "we are being blocked":
#
# 1. Timeout: if the server doesn't answer within 30 s, the request counts as
#    failed (the default would be 180 s).
DOWNLOAD_TIMEOUT = 30
#
# 2. Retry (built-in RetryMiddleware): timeouts, connection errors and
#    500/502/504 are retried immediately up to 3 times. If it still fails,
#    Scrapy calls the spider's errback -> `failures` table.
RETRY_ENABLED = True
RETRY_TIMES = 3
#
# 3. Backoff (our BackoffMiddleware, middlewares.py): with 429/503/403 the
#    server is throttling us. The whole crawl then pauses with increasing wait
#    times (30 s, 60 s, 120 s, ... max. 10 min). After 6 pauses in a row with
#    no success in between, it shuts down cleanly (reason "blocked").
BACKOFF_HTTP_CODES = [429, 503, 403]
BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 600
BACKOFF_MAX_STRIKES = 6

DOWNLOADER_MIDDLEWARES = {
    # 560 > 550 (RetryMiddleware): sees the response first.
    "marathon_scraper.middlewares.BackoffMiddleware": 560,
}

# --- HTTP cache: the most useful trick while developing ------------------------
# Every response is stored under .scrapy/httpcache. When you change a selector
# and restart the spider, the page comes from the cache instead of the server
# -> fast and easy on the server. Clear the cache: rm -rf .scrapy/httpcache
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 0  # 0 = never expire
HTTPCACHE_DIR = "httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [403, 429, 500, 502, 503, 504]  # don't cache errors

# --- Item pipelines ----------------------------------------------------------------
# Every item a spider yields passes through these pipelines (lower number =
# earlier). Our only pipeline writes to SQLite.
ITEM_PIPELINES = {
    "marathon_scraper.pipelines.SQLitePipeline": 300,
}

# --- Logging + progress display ----------------------------------------------------
# The detailed log goes to a file. The console only shows the progress bar
# plus warnings/errors (see extensions.py).
# Everything in the console as usual: -s LOG_FILE= -s PROGRESS_ENABLED=False
LOG_LEVEL = "INFO"
LOG_FILE = str(PROJECT_DIR / "logs" / "scrapy.log")
(PROJECT_DIR / "logs").mkdir(exist_ok=True)
LOGSTATS_INTERVAL = 60  # writes "Crawled X pages ..." to the log every minute

PROGRESS_ENABLED = True
EXTENSIONS = {
    "marathon_scraper.extensions.ProgressExtension": 500,
}
FEED_EXPORT_ENCODING = "utf-8"
