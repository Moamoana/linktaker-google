# ---------------- Config ----------------
# Defaults — most of these can be overridden from the command line.
# Every input and output lives under data/, which is where the .gitignore rules
# for generated files point too. Paths stay relative: the tool is run from the
# project directory, and the deploy scripts `cd` there first.

import os


def _env(nama, cast, default):
    """Nilai dari environment kalau diisi, kalau tidak default yang diberikan.

    Setelan yang paling sering disetel per mesin — jeda, batas waktu — dibuat
    bisa ditimpa dari environment supaya tidak ada yang perlu mengedit file
    ini. File ini di-track git: mengubahnya di satu mesin membuat `git pull`
    berikutnya di mesin itu ditolak dengan "local changes would be
    overwritten". deploy/linktaker.env yang menampung setelan per mesin, dan
    deploy/run-linktaker.sh yang meneruskannya ke sini.

    String kosong dihitung "tidak diisi": script shell meneruskan variabel yang
    belum diset sebagai string kosong, dan float("") hanya akan menggagalkan
    run yang sebenarnya baik-baik saja.
    """
    raw = os.environ.get(nama, "")
    if not str(raw).strip():
        return default
    try:
        return cast(raw)
    except ValueError:
        print(f"  {nama}={raw!r} bukan angka yang sah — memakai {default}")
        return default

DATA_DIR = "data"
URLS_FILE = "data/url.txt"
KEYWORDS_FILE = "data/keywords.txt"       # default for --input
OUT_FILE = "data/output.txt"              # default for --output
PROXIES_FILE = "data/proxies.txt"         # optional proxy list, used when --proxy is not given
AUTH_FILE = "data/auth.json"
NEWS_DOMAINS_FILE = "data/news_domains.txt"  # publisher allowlist, used by --news-filter

MAX_PAGES_PER_SEARCH = None          # None = crawl every page (default for --max-pages)
DEFAULT_SORT = "relevance"           # default for --sort ("relevance" or "latest")
DEFAULT_ENGINE = "google"            # default for --engine ("google" or "bing")
# Keep the output file to news stories. "smart" drops known non-news hosts and
# non-article URLs but still lets an unknown portal through; "strict" admits
# only NEWS_DOMAINS_FILE; "off" is the old behaviour. See news_filter.py.
NEWS_FILTER = "smart"                # default for --news-filter
# Which country's results to ask for — the default for --geo. An ISO country
# code ("my") or a country name ("malaysia"); None searches from wherever the
# browser appears to be, which is the old behaviour. See geo.py.
DEFAULT_GEO = None
# --mode default is "web" (the All tab) for every engine; "nws" searches the news
# tab instead, "both" crawls the two and merges the links.
WAIT_SEC = 20
PARALLEL_WORKERS = 5
CONSECUTIVE_EMPTY_PAGES = 2
RETRY_FAILED_PAGES = 3
USE_CLOUDFLARE_BYPASS = True
USE_JAVASCRIPT_RENDERING = True

# Fetch mode: "auto" (curl_cffi first, fallback playwright), "playwright" (playwright only), "curl" (curl_cffi only)
FETCH_MODE = "playwright"

# Google News RSS: try RSS feed before scraping (no CAPTCHA, but rate-limited decoding)
USE_GOOGLE_RSS = False
RSS_DECODE_DELAY = 2  # seconds between decoding RSS redirect URLs to avoid rate limits

# CAPTCHA wait timeout in seconds (how long to wait for user to solve CAPTCHA)
CAPTCHA_WAIT_TIMEOUT = _env("CAPTCHA_WAIT_TIMEOUT", int, 120)

# Batas waktu satu operasi halaman: goto, click, content, query_selector.
# Sebelumnya nilainya 0 — "tunggu selamanya" — dan itu bukan pilihan yang aman
# untuk run terjadwal. Satu halaman yang menggantung (Chromium berhenti
# menjawab, koneksi mati tanpa menutup) membuat seluruh crawl diam tanpa pesan
# apa pun sampai ada yang membunuhnya dari luar; sementara PM2 tetap melihat
# loop-nya "online" dan tidak ikut campur. Dengan batas ini halaman yang macet
# gagal cepat dan crawl lanjut ke keyword berikutnya.
#
# Pemanggil yang menyebut timeout-nya sendiri tidak terpengaruh: penantian
# CAPTCHA tetap CAPTCHA_WAIT_TIMEOUT, dan _wait_for_page_ready tetap 15 detik.
PAGE_TIMEOUT = _env("PAGE_TIMEOUT", int, 60)

# Run the browser without a visible window. Chromium fixes this at launch and
# Playwright cannot flip it on a live browser, so a run that needs a window for
# one CAPTCHA gets it by relaunching — see ON_CAPTCHA and browser.py.
HEADLESS = True

# What to do when a headless run hits a challenge page:
#   "headed" — close the headless browser, reopen the same profile with a
#              window at the same result page, wait for a human, then go back
#              to headless and resume where it left off.
#   "skip"   — give up on that page and move on. The only useful setting for an
#              unattended run (cron, systemd timer): nobody is there to solve it,
#              so waiting CAPTCHA_WAIT_TIMEOUT per page just burns the schedule.
ON_CAPTCHA = "headed"

# ---------------- CAPTCHA avoidance ----------------
# The settings below exist for one reason: getting challenged less often. None
# of them defeat a CAPTCHA — they keep a run from looking like the thing that
# earns one.

# Reuse one Chromium profile directory across runs so cookies, the consent
# choice, and Google's own "this browser has been fine so far" state carry over.
# Without it every run arrives cookie-less, which is the strongest single reason
# a fresh run gets challenged on its very first search. Pass --fresh-profile to
# start over if the profile itself ever gets flagged.
PERSIST_PROFILE = True
BROWSER_PROFILE_DIR = ".browser_profile"

# The fingerprint is generated once and pinned beside the profile. A stored
# cookie jar that shows up under a different user agent and screen size every
# run is stranger than either signal on its own, so the two stay in sync.
FINGERPRINT_FILE = ".fingerprint.json"

# Jitter between result pages within one keyword. Previously "Next" was clicked
# the instant the page finished loading — ten pages in fifteen seconds, which no
# human produces.
PAGE_DELAY_MIN = _env("PAGE_DELAY_MIN", float, 4)
PAGE_DELAY_MAX = _env("PAGE_DELAY_MAX", float, 8)

# Jeda antar-keyword — antara satu URL pencarian dan berikutnya, bukan antar
# halaman di dalam satu keyword. Dengan keyword yang banyak, ini yang paling
# menentukan seberapa cepat sebuah run terlihat seperti scraper.
URL_DELAY_MIN = _env("URL_DELAY_MIN", float, 1)
URL_DELAY_MAX = _env("URL_DELAY_MAX", float, 5)

# Pause after a solved CAPTCHA before touching the next page. Resuming at full
# speed right after a challenge tends to earn the next one immediately.
CAPTCHA_COOLDOWN_MIN = _env("CAPTCHA_COOLDOWN_MIN", float, 8.0)
CAPTCHA_COOLDOWN_MAX = _env("CAPTCHA_COOLDOWN_MAX", float, 10.0)

# Social media domains to exclude
SOCIAL_MEDIA_DOMAINS = {
    "facebook.com", "fb.com",
    "twitter.com", "x.com",
    "instagram.com",
    "tiktok.com",
    "youtube.com", "youtu.be",
    "linkedin.com",
    "reddit.com",
    "snapchat.com",
    "pinterest.com",
    "tumblr.com",
    "telegram.org", "t.me",
    "whatsapp.com",
    "discord.com",
    "twitch.tv",
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "medium.com",
    "dev.to",
    "quora.com",
    "stackoverflow.com",
    "behance.net",
    "dribbble.com",
    "vimeo.com",
    "wechat.com",
    "viber.com",
    "signal.org",
    "mastodon.social",
    "threads.net",
    "bluesky.social",
    "lemmy.ml",
    "kik.com",
    "omegle.com",
    "slack.com",
    "myspace.com",
    "nextdoor.com",
    "flipboard.com",
    "substack.com",
    "patreon.com",
    "kickstarter.com",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


# ---------------- Pengiriman hasil (submit_batch) ----------------
# Dipakai `linktaker.submit`, yang mengirim hasil crawl ke endpoint pengumpul.
# Semuanya bisa ditimpa lewat environment variable dengan nama yang sama —
# lihat linktaker/submit/settings.py dan deploy/linktaker.env.example.
SUBMIT_URL = "http://103.191.17.47:8001/submit_batch/"
SUBMIT_BATCH_SIZE = 100      # batas server: batch di atas 100 URL ditolak 400
SUBMIT_RETRIES = 3           # percobaan per batch sebelum link masuk antrean
SUBMIT_TIMEOUT = 30          # detik per POST
SUBMIT_STATE_DIR = "data/state"
SUBMIT_KEEP_DAYS = 30        # umur ingatan "sudah pernah dikirim"
SUBMIT_QUEUE_MAX = 20000     # batas antrean saat endpoint mati berhari-hari
