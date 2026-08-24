# ---------------- Config ----------------
# Defaults — most of these can be overridden from the command line.
URLS_FILE = "url.txt"
KEYWORDS_FILE = "keywords.txt"       # default for --input
OUT_FILE = "output.txt"              # default for --output
PROXIES_FILE = "proxies.txt"         # optional proxy list, used when --proxy is not given
AUTH_FILE = "auth.json"
NEWS_DOMAINS_FILE = "news_domains.txt"  # publisher allowlist, used by --news-filter

MAX_PAGES_PER_SEARCH = None          # None = crawl every page (default for --max-pages)
DEFAULT_SORT = "relevance"           # default for --sort ("relevance" or "latest")
DEFAULT_ENGINE = "google"            # default for --engine ("google" or "bing")
# Keep the output file to news stories. "smart" drops known non-news hosts and
# non-article URLs but still lets an unknown portal through; "strict" admits
# only NEWS_DOMAINS_FILE; "off" is the old behaviour. See news_filter.py.
NEWS_FILTER = "smart"                # default for --news-filter
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
CAPTCHA_WAIT_TIMEOUT = 120

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
