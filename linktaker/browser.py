import random
from itertools import count
from urllib.parse import unquote, urlparse, urlunparse

from .config import USER_AGENTS, CAPTCHA_WAIT_TIMEOUT
from .deps import (
    PLAYWRIGHT_AVAILABLE, sync_playwright,
    STEALTH_AVAILABLE, stealth_sync,
    BROWSERFORGE_AVAILABLE, FingerprintGenerator,
)
from .engines import GOOGLE


def playwright_proxy(proxy_url: str) -> dict:
    """Convert a proxy URL into Playwright's {server, username, password} form.

    Playwright ignores credentials embedded in the server URL, so
    http://user:pass@host:port is split into its parts.
    """
    parsed = urlparse(proxy_url if "://" in proxy_url else "http://" + proxy_url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"

    proxy = {"server": urlunparse((parsed.scheme or "http", host, "", "", "", ""))}
    if parsed.username:
        proxy["username"] = unquote(parsed.username)
    if parsed.password:
        proxy["password"] = unquote(parsed.password)
    return proxy


class BrowserManager:
    """Persistent browser manager — one browser instance reused across all pages."""

    def __init__(self, proxy=None):
        self._playwright = None
        self._browser = None
        self._context = None
        self._proxy = proxy
        self._fingerprint = None
        self._is_headed = False

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
                        print(f"  Attempt {attempt+1}: got mobile UA, retrying...")
                        continue

                # Reject small viewports (mobile screens)
                if hasattr(fp, 'screen') and fp.screen:
                    w = getattr(fp.screen, 'width', 0) or 0
                    if int(w) < MIN_DESKTOP_WIDTH:
                        print(f"  Attempt {attempt+1}: got small viewport ({w}px), retrying...")
                        continue

                return fp
            except Exception as e:
                print(f"  browserforge fingerprint generation failed: {e}")
                return None

        print(f"  Could not generate desktop fingerprint after {MAX_ATTEMPTS} attempts, using defaults")
        return None

    def start(self, headed=False):
        """Launch browser with stealth and fingerprint."""
        if not PLAYWRIGHT_AVAILABLE:
            print("  Playwright not installed.")
            return False

        self._playwright = sync_playwright().start()
        self._is_headed = headed

        launch_args = {
            "headless": not headed,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
            ],
        }
        proxy_settings = playwright_proxy(self._proxy) if self._proxy else None
        if proxy_settings:
            launch_args["proxy"] = proxy_settings

        self._browser = self._playwright.chromium.launch(**launch_args)

        # Build context options with browserforge fingerprint
        context_opts = {}
        if proxy_settings:
            # Chromium drops the launch-level credentials unless the context repeats them.
            context_opts["proxy"] = proxy_settings
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
            print(f"  browserforge fingerprint applied")
        else:
            context_opts["user_agent"] = random.choice(USER_AGENTS)
            context_opts["viewport"] = {"width": 1366, "height": 768}

        context_opts["java_script_enabled"] = True

        self._context = self._browser.new_context(**context_opts)
        return True

    def _relaunch_headed_for_captcha(self, current_url: str, engine):
        """Tear down headless browser, restart headed, and return a new page at the URL."""
        print("\n  [Handoff] CAPTCHA detected! Relaunching in HEADED mode so you can solve it...")
        # Save state if needed (not strictly required if we just restart at the same URL)
        state = self._context.storage_state()
        
        self.close()
        self.start(headed=True)
        
        page = self._context.new_page()
        if STEALTH_AVAILABLE:
            stealth_sync(page)
        self._context.add_cookies(state.get("cookies", []))
            
        page.goto(current_url, wait_until="domcontentloaded")
        return page

    def _is_captcha_page(self, page, engine=GOOGLE):
        """Check if the current page is the engine's CAPTCHA / challenge page."""
        url = page.url
        if any(marker in url for marker in engine.captcha_url_markers):
            return True

        if page.query_selector(engine.captcha_selector):
            return True

        if engine.captcha_text_markers:
            try:
                text = page.inner_text("body")[:3000].lower()
            except Exception:
                text = ""
            if any(marker in text for marker in engine.captcha_text_markers):
                return True

        return False

    def _wait_for_page_ready(self, page, engine=GOOGLE, initial_timeout_ms: int = 15000) -> bool:
        """
        Wait for either search results OR a CAPTCHA page to appear after navigation.
        If CAPTCHA, hand off to _wait_for_results so user can solve it.
        Returns True if results are eventually visible, False otherwise.
        """
        try:
            page.wait_for_selector(
                f"{engine.results_selector}, {engine.captcha_selector}",
                timeout=initial_timeout_ms,
            )
        except Exception:
            # Selector never appeared — may still be a challenge page with different markup.
            if self._is_captcha_page(page, engine):
                pass  # fall through to _wait_for_results CAPTCHA handler
            else:
                return False
        return self._wait_for_results(page, engine)

    def _wait_for_results(self, page, engine=GOOGLE):
        """Wait for search results. Distinguishes CAPTCHA from end-of-results."""
        results = page.query_selector_all(engine.results_selector)
        if results:
            return True

        # No results found — check if it's actually a CAPTCHA
        if self._is_captcha_page(page, engine):
            if not self._is_headed:
                # We hit a CAPTCHA while invisible. Relaunch headed!
                new_page = self._relaunch_headed_for_captcha(page.url, engine)
                # Swap the page reference for the caller (this is tricky in Python pass-by-value, 
                # but we return a special signal instead).
                return "CAPTCHA_HANDOFF", new_page
                
            print(f"  CAPTCHA detected! Solve it in the browser window... (waiting up to {CAPTCHA_WAIT_TIMEOUT}s)")
            try:
                page.wait_for_selector(
                    engine.results_selector,
                    timeout=CAPTCHA_WAIT_TIMEOUT * 1000
                )
                print(f"  Search results detected after CAPTCHA solve!")
                return True
            except:
                print(f"  Timeout waiting for CAPTCHA solve")
                return False

        # Not a CAPTCHA — just no results (end of results or empty page)
        print(f"  No results on this page (end of results)")
        return False

    def fetch(self, url: str, engine=GOOGLE) -> str:
        """Fetch a single page using the persistent browser."""
        if not self._context:
            if not self.start():
                return None

        page = self._context.new_page()
        if STEALTH_AVAILABLE:
            stealth_sync(page)

        try:
            page.set_default_timeout(0)
            page.goto(url, wait_until="domcontentloaded")
            
            res = self._wait_for_page_ready(page, engine)
            if isinstance(res, tuple) and res[0] == "CAPTCHA_HANDOFF":
                page = res[1]
                res = self._wait_for_results(page, engine)
                
            content = page.content()
            page.close()
            return content
        except Exception as e:
            print(f"  Playwright fetch failed: {e}")
            try:
                page.close()
            except:
                pass
            return None

    def browse_and_paginate(self, start_url: str, max_pages: int, consecutive_empty_limit: int,
                            engine=GOOGLE):
        """
        Open one tab, navigate to start_url, extract links, then move on to the
        next page — by clicking the engine's "Next" button (Google) or by
        navigating to the next page URL (Bing). One tab is reused throughout.
        Returns all collected links.

        max_pages: how many pages to visit; None keeps going until the engine
        runs out of pages.
        """
        if not self._context:
            if not self.start():
                return set()

        page = self._context.new_page()
        if STEALTH_AVAILABLE:
            stealth_sync(page)

        all_links = set()
        consecutive_empty = 0

        try:
            page.set_default_timeout(0)
            page.goto(start_url, wait_until="domcontentloaded")
            
            res = self._wait_for_page_ready(page, engine)
            if isinstance(res, tuple) and res[0] == "CAPTCHA_HANDOFF":
                page = res[1]
                res = self._wait_for_results(page, engine)
                
            if not res:
                print(f"  Could not load results for {start_url}")
                return all_links

            pages = count() if max_pages is None else range(max_pages)
            for page_idx in pages:

                # Extract links from current page
                html = page.content()
                page_links = engine.extract_links(html)
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

                if max_pages is not None and page_idx + 1 >= max_pages:
                    break

                # Move to the next page: click the engine's button, or open its URL.
                if engine.next_selector:
                    next_btn = page.query_selector(engine.next_selector)
                    if not next_btn:
                        print(f"  No 'Next' button found — last page reached")
                        break

                    print(f"  Clicking next...")
                    next_btn.click()
                    page.wait_for_load_state("domcontentloaded")
                else:
                    next_url = engine.build_paginated_url(start_url, page_idx + 1)
                    print(f"  Opening page {page_idx+2}...")
                    page.goto(next_url, wait_until="domcontentloaded")

                res = self._wait_for_page_ready(page, engine)
                if isinstance(res, tuple) and res[0] == "CAPTCHA_HANDOFF":
                    page = res[1]
                    res = self._wait_for_results(page, engine)
                    
                if not res:
                    print(f"  Next page failed to load — stopping pagination")
                    break

        except Exception as e:
            print(f"  Playwright pagination failed: {e}")
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
