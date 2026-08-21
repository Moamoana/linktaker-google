# pip install curl_cffi beautifulsoup4 cloudscraper playwright-stealth browserforge feedparser
# Also run: playwright install chromium
"""Optional dependency imports and availability flags.

curl_cffi and beautifulsoup4 are hard requirements (imported directly where
used). Everything below is optional — the tool degrades gracefully without it.
"""

try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    cloudscraper = None
    CLOUDSCRAPER_AVAILABLE = False
    print("cloudscraper not installed. Install with: pip install cloudscraper")

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    feedparser = None
    FEEDPARSER_AVAILABLE = False
    print("feedparser not installed. Install with: pip install feedparser")

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False
    print("playwright not installed. Install with: pip install playwright && playwright install chromium")

try:
    from playwright_stealth import stealth_sync
    STEALTH_AVAILABLE = True
except ImportError:
    stealth_sync = None
    STEALTH_AVAILABLE = False
    print("playwright-stealth not installed. Install with: pip install playwright-stealth")

try:
    from browserforge.fingerprints import FingerprintGenerator
    from browserforge.headers import HeaderGenerator
    BROWSERFORGE_AVAILABLE = True
except ImportError:
    FingerprintGenerator = None
    HeaderGenerator = None
    BROWSERFORGE_AVAILABLE = False
    print("browserforge not installed. Install with: pip install browserforge")
