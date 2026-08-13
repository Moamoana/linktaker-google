# pip install curl_cffi beautifulsoup4 cloudscraper playwright-stealth browserforge feedparser
# Also run: playwright install chromium
import curl_cffi.requests as requests
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess, sys, os
import codecs
if hasattr(sys.stdout, "buffer") and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
import time
import random
from bs4 import BeautifulSoup
import json
import base64
import re

try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False
    print("⚠️  cloudscraper not installed. Install with: pip install cloudscraper")

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False
    print("⚠️  feedparser not installed. Install with: pip install feedparser")

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️  playwright not installed. Install with: pip install playwright && playwright install chromium")

try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    print("⚠️  playwright-stealth not installed. Install with: pip install playwright-stealth")

try:
    from browserforge.fingerprints import FingerprintGenerator
    from browserforge.headers import HeaderGenerator
    BROWSERFORGE_AVAILABLE = True
except ImportError:
    BROWSERFORGE_AVAILABLE = False
    print("⚠️  browserforge not installed. Install with: pip install browserforge")

# ---------------- Config ----------------
URLS_FILE = "url.txt"
OUT_FILE = "output.txt"
PROXIES_FILE = "proxies.txt"
AUTH_FILE = "auth.json"
RUN_BATCH = False

MAX_PAGES_PER_SEARCH = 30
# Berhenti jika X halaman berurutan tidak menemukan link baru
CONSECUTIVE_EMPTY_PAGES = 3
WAIT_SEC = 5
PARALLEL_WORKERS = 5
USE_PROXY = False
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

# ----------------------------------------


class BrowserManager:
    """Persistent browser manager — one browser instance reused across all pages."""

    def __init__(self, proxy=None):
        self._playwright = None
        self._browser = None
        self._context = None
        self._proxy = proxy
        self._fingerprint = None

    def _generate_fingerprint(self):
        """Generate a realistic desktop-only browser fingerprint using browserforge."""
        if not BROWSERFORGE_AVAILABLE:
            return None

        MOBILE_INDICATORS = ('Mobile', 'Android', 'iPhone', 'iPad', 'iPod')
        MIN_DESKTOP_WIDTH = 1024
        MAX_ATTEMPTS = 5

        for attempt in range(MAX_ATTEMPTS):
            try:
                fg = FingerprintGenerator(
                    browser='chrome',
                    os=('windows', 'macos', 'linux'),
                )
                fp = fg.generate()

                # Reject mobile user agents
                if hasattr(fp, 'navigator') and fp.navigator:
                    ua = getattr(fp.navigator, 'userAgent', '') or ''
                    if any(m in ua for m in MOBILE_INDICATORS):
                        print(f"  ⚠️  Attempt {attempt+1}: got mobile UA, retrying...")
                        continue

                # Reject small viewports (mobile screens)
                if hasattr(fp, 'screen') and fp.screen:
                    w = getattr(fp.screen, 'width', 0) or 0
                    if int(w) < MIN_DESKTOP_WIDTH:
                        print(f"  ⚠️  Attempt {attempt+1}: got small viewport ({w}px), retrying...")
                        continue

                return fp
            except Exception as e:
                print(f"  ⚠️  browserforge fingerprint generation failed: {e}")
                return None

        print(f"  ⚠️  Could not generate desktop fingerprint after {MAX_ATTEMPTS} attempts, using defaults")
        return None

    def start(self):
        """Launch browser with stealth and fingerprint."""
        if not PLAYWRIGHT_AVAILABLE:
            print("  ⚠️  Playwright not installed.")
            return False

        self._playwright = sync_playwright().start()

        launch_args = {
            "headless": False,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
            ],
        }
        if self._proxy and USE_PROXY:
            launch_args["proxy"] = {"server": self._proxy}

        self._browser = self._playwright.chromium.launch(**launch_args)

        # Build context options with browserforge fingerprint
        context_opts = {}
        self._fingerprint = self._generate_fingerprint()
        if self._fingerprint:
            fp = self._fingerprint
            if hasattr(fp, 'navigator') and fp.navigator:
                nav = fp.navigator
                if hasattr(nav, 'userAgent') and nav.userAgent:
                    context_opts["user_agent"] = nav.userAgent
                if hasattr(nav, 'language') and nav.language:
                    context_opts["locale"] = nav.language
            if hasattr(fp, 'screen') and fp.screen:
                screen = fp.screen
                w = getattr(screen, 'width', 1920)
                h = getattr(screen, 'height', 1080)
                if w and h and int(w) >= 1024:
                    context_opts["viewport"] = {"width": int(w), "height": int(h)}
                else:
                    context_opts["viewport"] = {"width": 1366, "height": 768}
            print(f"  ✅ browserforge fingerprint applied")
        else:
            context_opts["user_agent"] = random.choice(USER_AGENTS)
            context_opts["viewport"] = {"width": 1366, "height": 768}

        context_opts["java_script_enabled"] = True

        self._context = self._browser.new_context(**context_opts)
        return True

    def _is_captcha_page(self, page):
        """Check if the current page is a Google CAPTCHA / sorry page."""
        url = page.url
        if '/sorry/' in url or 'google.com/sorry' in url:
            return True
        captcha_selectors = [
            '#captcha-form',
            '#recaptcha',
            'iframe[src*="recaptcha"]',
            'form[action*="sorry"]',
            '#g-recaptcha',
            'div.g-recaptcha',
        ]
        for sel in captcha_selectors:
            if page.query_selector(sel):
                return True
        return False

    def _wait_for_page_ready(self, page, initial_timeout_ms: int = 15000) -> bool:
        """
        Wait for either search results OR a CAPTCHA page to appear after navigation.
        If CAPTCHA, hand off to _wait_for_results so user can solve it.
        Returns True if results are eventually visible, False otherwise.
        """
        try:
            page.wait_for_selector(
                "#search, #rso, div.g, #captcha-form, #recaptcha, form[action*='sorry'], #g-recaptcha",
                timeout=initial_timeout_ms,
            )
        except Exception:
            # Selector never appeared — may still be a sorry page with different markup.
            if self._is_captcha_page(page):
                pass  # fall through to _wait_for_results CAPTCHA handler
            else:
                return False
        return self._wait_for_results(page)

    def _wait_for_results(self, page):
        """Wait for search results. Distinguishes CAPTCHA from end-of-results."""
        results = page.query_selector_all("div.g, div.SoaBEf, div.yuRUbf, div.MjjYud")
        if results:
            return True

        # No results found — check if it's actually a CAPTCHA
        if self._is_captcha_page(page):
            print(f"  🔓 CAPTCHA detected! Solve it in the browser window... (waiting up to {CAPTCHA_WAIT_TIMEOUT}s)")
            try:
                page.wait_for_selector(
                    "div.g, div.SoaBEf, div.yuRUbf, div.MjjYud",
                    timeout=CAPTCHA_WAIT_TIMEOUT * 1000
                )
                print(f"  ✅ Search results detected after CAPTCHA solve!")
                return True
            except:
                print(f"  ⏳ Timeout waiting for CAPTCHA solve")
                return False

        # Not a CAPTCHA — just no results (end of results or empty page)
        print(f"  ℹ️  No results on this page (end of results)")
        return False

    def fetch(self, url: str) -> str:
        """Fetch a single page using the persistent browser."""
        if not self._context:
            if not self.start():
                return None

        page = self._context.new_page()
        if STEALTH_AVAILABLE:
            Stealth().apply_stealth_sync(page)

        try:
            page.set_default_timeout(0)
            page.goto(url, wait_until="domcontentloaded")
            self._wait_for_page_ready(page)
            content = page.content()
            page.close()
            return content
        except Exception as e:
            print(f"  ⚠️  Playwright fetch failed: {e}")
            try:
                page.close()
            except:
                pass
            return None

    def browse_and_paginate(self, start_url: str, max_pages: int, consecutive_empty_limit: int):
        """
        Open one tab, navigate to start_url, extract links, then click
        the "Next" button (#pnnext) to paginate — no new tabs or page reloads.
        Returns all collected links.
        """
        if not self._context:
            if not self.start():
                return set()

        page = self._context.new_page()
        if STEALTH_AVAILABLE:
            Stealth().apply_stealth_sync(page)

        all_links = set()
        consecutive_empty = 0

        try:
            page.set_default_timeout(0)
            page.goto(start_url, wait_until="domcontentloaded")
            if not self._wait_for_page_ready(page):
                print(f"  ⚠️  Could not load results for {start_url}")
                return all_links

            for page_idx in range(max_pages):

                # Extract links from current page
                html = page.content()
                page_links = extract_google_links(html)
                new = page_links - all_links
                all_links |= page_links

                if new:
                    consecutive_empty = 0
                    print(f"  page {page_idx+1}: +{len(new)} new ({len(all_links)} total)")
                else:
                    consecutive_empty += 1
                    print(f"  page {page_idx+1}: No new links ({consecutive_empty}/{consecutive_empty_limit})")
                    if consecutive_empty >= consecutive_empty_limit:
                        print(f"  Stopping: {consecutive_empty_limit} consecutive empty pages")
                        break

                # Click "Next" button to go to next page
                next_btn = page.query_selector("#pnnext")
                if not next_btn:
                    print(f"  No 'Next' button found — last page reached")
                    break

                print(f"  Clicking next...")
                next_btn.click()
                page.wait_for_load_state("domcontentloaded")
                if not self._wait_for_page_ready(page):
                    print(f"  ⚠️  Next page failed to load — stopping pagination")
                    break

        except Exception as e:
            print(f"  ⚠️  Playwright pagination failed: {e}")
        finally:
            try:
                page.close()
            except:
                pass

        return all_links

    def close(self):
        """Shutdown browser."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except:
            pass
        self._context = None
        self._browser = None
        self._playwright = None


def read_urls(path):
    """Read search URLs from file."""
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]


def read_proxies(path):
    """Read proxies from file."""
    if not os.path.exists(path):
        print(f"⚠️  {path} not found. Proceeding without proxy rotation.")
        return []

    proxies = [ln.strip() for ln in open(path, "r", encoding="utf-8")
               if ln.strip() and not ln.strip().startswith("#")]
    print(f"✅ Loaded {len(proxies)} proxy/proxies")
    return proxies


def read_auth():
    """Read authentication credentials from JSON file."""
    if not os.path.exists(AUTH_FILE):
        return None

    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            auth = json.load(f)
        print(f"✅ Loaded authentication for user: {auth.get('username')}")
        return auth
    except Exception as e:
        print(f"⚠️  Error reading {AUTH_FILE}: {e}")
        return None


def strip_amp(url: str) -> str:
    """Remove AMP artifacts from a URL."""
    try:
        p = urlparse(url)

        # Strip amp. subdomain (e.g. amp.example.com -> example.com)
        netloc = p.netloc
        if netloc.startswith("amp."):
            netloc = netloc[4:]

        # Strip /amp/, /amp from path
        path = re.sub(r'/amp(/|$)', '/', p.path)
        # Remove trailing slash added by cleanup (but keep root /)
        if path != '/' and path.endswith('/'):
            path = path.rstrip('/')

        # Remove amp-related query params
        qs = parse_qs(p.query, keep_blank_values=True)
        qs.pop('amp', None)
        qs.pop('amp_js_v', None)
        qs.pop('usqp', None)
        qs.pop('outputType', None)
        new_query = urlencode(
            {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in qs.items()},
            doseq=True,
        )

        return urlunparse((p.scheme, netloc, path, p.params, new_query, p.fragment))
    except:
        return url


def is_social_media(url: str) -> bool:
    """Check if URL belongs to a social media platform."""
    try:
        p = urlparse(url)
        netloc = p.netloc.lower()

        if netloc.startswith("www."):
            netloc = netloc[4:]
        if netloc in SOCIAL_MEDIA_DOMAINS:
            return True
        for domain in SOCIAL_MEDIA_DOMAINS:
            if netloc.endswith("." + domain) or netloc == domain:
                return True

        return False
    except:
        return False


def is_valid_result_url(href: str) -> bool:
    """Validate if URL is a real search result and not social media."""
    if not href:
        return False

    if "/url?q=" in href:
        try:
            qs = parse_qs(urlparse(href).query)
            if "q" in qs:
                href = qs["q"][0]
        except:
            return False

    if is_social_media(href):
        return False

    p = urlparse(href)
    if p.scheme not in ("http", "https"):
        return False
    if not p.netloc:
        return False

    bad = ("google.com", "google.co.", "gstatic.com", "googleusercontent.com")
    if any(b in p.netloc for b in bad):
        return False

    return True


def build_paginated_url(base_url: str, page_index: int) -> str:
    """Build Google search URL with pagination."""
    start = page_index * 10
    p = urlparse(base_url)
    q = parse_qs(p.query, keep_blank_values=True)
    q["start"] = [str(start)]
    new_query = urlencode({k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in q.items()}, doseq=True)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, p.fragment))


def extract_google_links(html_content: str) -> set:
    """Extract all result links from Google HTML."""
    links = set()
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        selectors = [
            "div.g a[href]",
            "div.SoaBEf a[href]",
            "div.yuRUbf a[href]",
            "div.MjjYud a[href]",
            "a[jsname='UWckNb']",
        ]

        for selector in selectors:
            for a in soup.select(selector):
                href = a.get("href", "")
                if is_valid_result_url(href):
                    links.add(href)

    except Exception as e:
        print(f"  ⚠️  Error parsing HTML: {e}")

    return links


# ---- Google News RSS ----

def decode_google_news_url(source_url: str) -> str:
    """
    Decode a Google News redirect URL to the actual article URL.
    Google News RSS uses base64-encoded redirect URLs.
    """
    try:
        # Extract the encoded part from Google News URLs
        # Format: https://news.google.com/rss/articles/CBMi...
        p = urlparse(source_url)
        path = p.path

        # Handle /rss/articles/<encoded> format
        match = re.search(r'/articles/([A-Za-z0-9_-]+)', path)
        if not match:
            # Not a Google News redirect, return as-is
            return source_url

        encoded = match.group(1)

        # Add padding if needed
        padding = 4 - len(encoded) % 4
        if padding != 4:
            encoded += "=" * padding

        # Try base64 decode
        try:
            decoded = base64.urlsafe_b64decode(encoded)
            # The decoded bytes contain the URL, often prefixed with some bytes
            # Try to find a URL pattern in the decoded data
            decoded_str = decoded.decode("utf-8", errors="ignore")
            url_match = re.search(r'https?://[^\s"\'<>]+', decoded_str)
            if url_match:
                return url_match.group(0)
        except:
            pass

        # Fallback: follow the redirect with curl_cffi
        try:
            resp = requests.get(
                source_url,
                impersonate="chrome",
                timeout=10,
                allow_redirects=True,
                verify=False,
            )
            final_url = str(resp.url)
            if final_url != source_url and "news.google.com" not in final_url:
                return final_url
        except:
            pass

        return source_url
    except:
        return source_url


def build_google_news_rss_url(search_url: str) -> str:
    """Convert a Google search URL to a Google News RSS feed URL."""
    p = urlparse(search_url)
    q = parse_qs(p.query, keep_blank_values=True)

    query = q.get("q", [""])[0]
    if not query:
        return None

    # Check if this is a news search (tbm=nws)
    tbm = q.get("tbm", [""])[0]
    if tbm != "nws":
        return None

    # Build RSS URL
    # tbs=qdr:w means past week, etc.
    tbs = q.get("tbs", [""])[0]
    params = {"q": query, "hl": "id", "gl": "ID", "ceid": "ID:id"}

    # Map time filter
    if "qdr:h" in tbs:
        params["when"] = "1h"
    elif "qdr:d" in tbs:
        params["when"] = "1d"
    elif "qdr:w" in tbs:
        params["when"] = "7d"
    elif "qdr:m" in tbs:
        params["when"] = "30d"
    elif "qdr:y" in tbs:
        params["when"] = "1y"

    rss_url = "https://news.google.com/rss/search?" + urlencode(params)
    return rss_url


def fetch_google_news_rss(search_url: str) -> set:
    """
    Fetch links from Google News RSS feed.
    No CAPTCHA, but decoded URLs need rate limiting.
    """
    if not FEEDPARSER_AVAILABLE:
        return set()

    rss_url = build_google_news_rss_url(search_url)
    if not rss_url:
        return set()

    print(f"  📡 Trying Google News RSS: {rss_url}")

    try:
        # Fetch RSS feed with curl_cffi to avoid blocks
        resp = requests.get(
            rss_url,
            impersonate="chrome",
            timeout=15,
            verify=False,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
    except Exception as e:
        print(f"  ⚠️  RSS fetch failed: {e}")
        return set()

    if not feed.entries:
        print(f"  ⚠️  RSS feed returned 0 entries")
        return set()

    links = set()
    print(f"  📡 RSS returned {len(feed.entries)} entries, decoding URLs...")

    for i, entry in enumerate(feed.entries):
        raw_link = entry.get("link", "")
        if not raw_link:
            continue

        # Decode Google News redirect URL
        actual_url = decode_google_news_url(raw_link)

        if actual_url and is_valid_result_url(actual_url):
            links.add(actual_url)

        # Rate limit decoding to avoid getting blocked
        if RSS_DECODE_DELAY > 0 and i < len(feed.entries) - 1:
            time.sleep(RSS_DECODE_DELAY)

    print(f"  ✅ RSS decoded {len(links)} valid links")
    return links


# ---- Fetchers ----

def is_cloudflare_challenge(response_text: str) -> bool:
    """Detect if response is a Cloudflare challenge."""
    return "cf_challenge" in response_text or "Checking your browser" in response_text


def fetch_page_curl_cffi(url: str, proxy: str = None, retry: int = 0, auth: dict = None) -> str:
    """Fetch page using curl_cffi with browser impersonation."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }

    # Use browserforge headers if available
    if BROWSERFORGE_AVAILABLE:
        try:
            hg = HeaderGenerator()
            bf_headers = hg.generate()
            if bf_headers:
                headers.update(bf_headers)
        except:
            pass

    proxies_dict = None
    if proxy and USE_PROXY:
        proxies_dict = {"https": proxy, "http": proxy}

    auth_tuple = None
    if auth:
        auth_tuple = (auth.get("username"), auth.get("password"))

    try:
        response = requests.get(
            url,
            headers=headers,
            impersonate="chrome",
            timeout=WAIT_SEC,
            proxies=proxies_dict,
            allow_redirects=True,
            verify=False,
            auth=auth_tuple,
        )
        response.raise_for_status()

        if is_cloudflare_challenge(response.text):
            if USE_CLOUDFLARE_BYPASS and CLOUDSCRAPER_AVAILABLE:
                print(f"  🔒 Cloudflare challenge detected. Using cloudscraper...")
                return fetch_page_cloudscraper(url, proxy, auth)
            else:
                print(f"  ⚠️  Cloudflare challenge detected but bypass disabled")
                return None

        return response.text

    except Exception as e:
        if retry < RETRY_FAILED_PAGES:
            wait_time = random.uniform(2, 5) * (retry + 1)
            print(f"  ⚠️  Retry {retry + 1}/{RETRY_FAILED_PAGES} for {url} (wait {wait_time:.1f}s): {e}")
            time.sleep(wait_time)
            return fetch_page_curl_cffi(url, proxy, retry + 1, auth)
        else:
            print(f"  ❌ Failed to fetch {url}: {e}")
            return None


def fetch_page_cloudscraper(url: str, proxy: str = None, auth: dict = None) -> str:
    """Use cloudscraper for advanced Cloudflare bypass."""
    if not CLOUDSCRAPER_AVAILABLE:
        print(f"  ⚠️  cloudscraper not available")
        return None

    try:
        scraper = cloudscraper.create_scraper()

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
        }

        proxies_dict = None
        if proxy and USE_PROXY:
            proxies_dict = {"https": proxy, "http": proxy}

        auth_tuple = None
        if auth:
            auth_tuple = (auth.get("username"), auth.get("password"))

        response = scraper.get(
            url,
            headers=headers,
            timeout=WAIT_SEC,
            proxies=proxies_dict,
            auth=auth_tuple,
            verify=False,
        )
        response.raise_for_status()

        print(f"  ✅ Successfully bypassed Cloudflare")
        return response.text

    except Exception as e:
        print(f"  ⚠️  cloudscraper failed: {e}")
        return None


def fetch_page(url: str, proxy: str = None, auth: dict = None, browser_mgr: BrowserManager = None) -> str:
    """
    Main fetch function with mode-based fallback chain.
    - "curl": curl_cffi only
    - "playwright": playwright only (uses persistent browser)
    - "auto": curl_cffi first, fallback to playwright if no links
    """
    if FETCH_MODE == "playwright":
        if browser_mgr:
            return browser_mgr.fetch(url)
        print("  ⚠️  Playwright mode but no browser manager")
        return None

    if FETCH_MODE == "curl":
        return fetch_page_curl_cffi(url, proxy, auth=auth)

    # "auto" mode: try curl_cffi first
    return fetch_page_curl_cffi(url, proxy, auth=auth)


def process_one_url(search_url: str, proxy: str = None, auth: dict = None, browser_mgr: BrowserManager = None):
    """Process a single search URL across multiple pages."""
    links_all = set()

    print(f"\n[{search_url}] Starting... (mode: {FETCH_MODE})")
    if proxy and USE_PROXY:
        print(f"  Using proxy: {proxy}")

    # Try Google News RSS first (free, no CAPTCHA)
    if USE_GOOGLE_RSS:
        rss_links = fetch_google_news_rss(search_url)
        if rss_links:
            links_all |= rss_links
            print(f"[{search_url}] RSS: +{len(rss_links)} links")

    # Playwright mode: open one tab, click "Next" to paginate
    if FETCH_MODE == "playwright" and browser_mgr:
        pw_links = browser_mgr.browse_and_paginate(search_url, MAX_PAGES_PER_SEARCH, CONSECUTIVE_EMPTY_PAGES)
        links_all |= pw_links
        print(f"[{search_url}] ✅ Complete: {len(links_all)} total links")
        return links_all

    # curl / auto mode: fetch each page separately
    consecutive_empty = 0
    for page_idx in range(MAX_PAGES_PER_SEARCH):
        page_url = build_paginated_url(search_url, page_idx)

        html = fetch_page(page_url, proxy, auth, browser_mgr)
        if html is None:
            print(f"[{search_url}] page {page_idx+1}: Failed to fetch (stopping)")
            break

        page_links = extract_google_links(html)

        # Auto mode: if curl_cffi got HTML but 0 links, fall back to Playwright
        if not page_links and FETCH_MODE == "auto" and browser_mgr:
            print(f"[{search_url}] page {page_idx+1}: No links from curl_cffi, switching to Playwright...")
            # Use browse_and_paginate for the rest — no point retrying curl
            pw_links = browser_mgr.browse_and_paginate(
                build_paginated_url(search_url, page_idx),
                MAX_PAGES_PER_SEARCH - page_idx,
                CONSECUTIVE_EMPTY_PAGES
            )
            links_all |= pw_links
            break

        new = page_links - links_all
        links_all |= page_links

        if new:
            consecutive_empty = 0
            print(f"[{search_url}] page {page_idx+1}: +{len(new)} new ({len(links_all)} total)")
        else:
            consecutive_empty += 1
            print(f"[{search_url}] page {page_idx+1}: No new links ({consecutive_empty}/{CONSECUTIVE_EMPTY_PAGES})")

            if consecutive_empty >= CONSECUTIVE_EMPTY_PAGES:
                print(f"[{search_url}] Stopping: {CONSECUTIVE_EMPTY_PAGES} consecutive empty pages")
                break

        time.sleep(random.uniform(1.5, 3.5))

    print(f"[{search_url}] ✅ Complete: {len(links_all)} total links")
    return links_all


def main():
    """Main execution."""
    if not os.path.exists(URLS_FILE):
        print(f"❌ Missing {URLS_FILE}")
        sys.exit(1)

    urls = read_urls(URLS_FILE)
    if not urls:
        print("❌ No URLs to process.")
        sys.exit(0)

    # ✅ RESUME SUPPORT: Load existing URLs so we don't re-scrape or overwrite them
    existing_links = set()
    if os.path.exists(OUT_FILE):
        with open(OUT_FILE, "r", encoding="utf-8") as f:
            existing_links = {line.strip() for line in f if line.strip()}
        if existing_links:
            print(f"✅ Resume mode: {len(existing_links)} existing URLs loaded from {OUT_FILE}")

    proxies = []
    if USE_PROXY:
        proxies = read_proxies(PROXIES_FILE)

    auth = read_auth()

    print(f"✅ Processing {len(urls)} URL(s) — mode: {FETCH_MODE}")
    print(f"✅ Filtering social media URLs ({len(SOCIAL_MEDIA_DOMAINS)} domains excluded)")

    if USE_GOOGLE_RSS:
        print(f"✅ Google News RSS: ENABLED (decode delay: {RSS_DECODE_DELAY}s)")

    if proxies:
        print(f"✅ Proxy rotation enabled ({len(proxies)} proxy/proxies)")
    else:
        print("⚠️  No proxies loaded - proceeding without proxy rotation")

    if USE_CLOUDFLARE_BYPASS:
        if CLOUDSCRAPER_AVAILABLE:
            print(f"✅ Cloudflare bypass: ENABLED (cloudscraper)")
        else:
            print(f"⚠️  Cloudflare bypass: curl_cffi only")

    if STEALTH_AVAILABLE:
        print(f"✅ Playwright stealth: ENABLED")
    if BROWSERFORGE_AVAILABLE:
        print(f"✅ browserforge fingerprints: ENABLED")

    # Create persistent browser manager (shared across all pages)
    browser_mgr = None
    if FETCH_MODE in ("auto", "playwright") and PLAYWRIGHT_AVAILABLE:
        proxy = random.choice(proxies) if proxies else None
        browser_mgr = BrowserManager(proxy=proxy)
        # Lazy start — only launches when first needed
        print(f"✅ Persistent browser: READY (will launch on first use)")

    all_links = set()
    saved_count = [0]  # mutable counter for nested function

    def save_links_immediately(new_found_links):
        """Langsung tulis URL baru ke file begitu ditemukan."""
        for link in new_found_links:
            clean = strip_amp(link)
            if clean not in existing_links and clean not in all_links:
                all_links.add(clean)
                with open(OUT_FILE, "a", encoding="utf-8") as f:
                    f.write(clean + "\n")
                saved_count[0] += 1

    try:
        # When using playwright mode, run sequentially (one browser)
        if FETCH_MODE == "playwright":
            # Shuffle so the date walk isn't sequential (less scraper-like)
            shuffled = list(urls)
            random.shuffle(shuffled)
            for i, u in enumerate(shuffled):
                result = process_one_url(u, None, auth, browser_mgr) or set()
                save_links_immediately(result)
                print(f"  💾 Total tersimpan: {len(existing_links) + len(all_links)} URL")
                # Jitter between search URLs to avoid burst-rate detection
                if i < len(shuffled) - 1:
                    delay = random.uniform(3, 8)
                    print(f"  ⏸  Waiting {delay:.1f}s before next URL...")
                    time.sleep(delay)
        else:
            workers = min(PARALLEL_WORKERS, len(urls))
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futures = {}
                    for u in urls:
                        proxy = random.choice(proxies) if proxies else None
                        futures[ex.submit(process_one_url, u, proxy, auth, browser_mgr)] = u

                    for fut in as_completed(futures):
                        u = futures[fut]
                        try:
                            res = fut.result() or set()
                            save_links_immediately(res)
                        except Exception as e:
                            print(f"[{u}] ❌ Failed: {e}")
            else:
                for u in urls:
                    proxy = random.choice(proxies) if proxies else None
                    result = process_one_url(u, proxy, auth, browser_mgr) or set()
                    save_links_immediately(result)
    finally:
        # Always close browser
        if browser_mgr:
            browser_mgr.close()
            print(f"✅ Browser closed")

    total_links = len(existing_links) + len(all_links)
    print(f"\n✅ Selesai! (+{saved_count[0]} baru | total unique: {total_links})")

    if RUN_BATCH:
        try:
            subprocess.run(["scrape-onm-list.bat"], check=True, shell=True)
            print("✅ scrape-onm-list.bat executed.")
            print(f"\n✅ count of links: (unique: {len(all_links)})")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error executing scrape-onm-list.bat: {e}")
        except FileNotFoundError:
            print("⚠️  scrape-onm-list.bat not found")

    # Panggil fungsi scraping berita setelah selesai
    scrape_article_contents(list(all_links))


def scrape_article_contents(links):
    print(f"\n📡 Mulai mengekstrak isi teks berita dari {len(links)} link...")
    target_domains = ["kompas.com", "detik.com", "cnnindonesia.com", "tempo.co", "tribunnews.com", "okezone.com"]
    
    with open("hasil_berita.txt", "w", encoding="utf-8") as f:
        f.write("=== HASIL EKSTRAKSI BERITA ===\n\n")
        
    for link in links:
        if not any(domain in link.lower() for domain in target_domains):
            continue
            
        print(f"  Mengekstrak: {link}")
        try:
            html = fetch_page_curl_cffi(link, None, 0, None)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            
            title = ""
            content = ""
            
            if "kompas.com" in link:
                t = soup.select_one(".read__title")
                title = t.text.strip() if t else soup.title.text
                ps = soup.select(".read__content p")
                content = "\n".join(p.text.strip() for p in ps)
            elif "detik.com" in link:
                t = soup.select_one(".detail__title")
                title = t.text.strip() if t else soup.title.text
                ps = soup.select(".detail__body-text p")
                content = "\n".join(p.text.strip() for p in ps)
            elif "cnnindonesia.com" in link:
                t = soup.select_one(".title")
                title = t.text.strip() if t else soup.title.text
                ps = soup.select(".detail-text p")
                content = "\n".join(p.text.strip() for p in ps)
            elif "tempo.co" in link:
                t = soup.select_one("h1.title")
                title = t.text.strip() if t else soup.title.text
                ps = soup.select("#isi p")
                content = "\n".join(p.text.strip() for p in ps)
            elif "tribunnews.com" in link:
                t = soup.select_one("#arttitle")
                title = t.text.strip() if t else soup.title.text
                ps = soup.select(".txt-article p")
                content = "\n".join(p.text.strip() for p in ps)
            elif "okezone.com" in link:
                t = soup.select_one(".title")
                title = t.text.strip() if t else soup.title.text
                ps = soup.select(".read p")
                content = "\n".join(p.text.strip() for p in ps)
            
            with open("hasil_berita.txt", "a", encoding="utf-8") as f:
                f.write(f"URL: {link}\n")
                f.write(f"Judul: {title}\n")
                f.write(f"Isi:\n{content}\n")
                f.write("-" * 80 + "\n\n")
                
            print(f"  ✅ Sukses: {title[:50]}...")
            time.sleep(2)
        except Exception as e:
            print(f"  ❌ Gagal: {e}")

if __name__ == "__main__":
    main()
