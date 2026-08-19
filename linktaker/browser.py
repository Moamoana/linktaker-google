import random

from .config import USER_AGENTS, USE_PROXY, CAPTCHA_WAIT_TIMEOUT
from .deps import (
    PLAYWRIGHT_AVAILABLE, sync_playwright,
    STEALTH_AVAILABLE, stealth_sync,
    BROWSERFORGE_AVAILABLE, FingerprintGenerator,
)
from .url_utils import extract_google_links


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

    def start(self):
        """Launch browser with stealth and fingerprint."""
        if not PLAYWRIGHT_AVAILABLE:
            print("  Playwright not installed.")
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
            print(f"  browserforge fingerprint applied")
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
            print(f"  CAPTCHA detected! Solve it in the browser window... (waiting up to {CAPTCHA_WAIT_TIMEOUT}s)")
            try:
                page.wait_for_selector(
                    "div.g, div.SoaBEf, div.yuRUbf, div.MjjYud",
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

    def fetch(self, url: str) -> str:
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
            self._wait_for_page_ready(page)
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
            stealth_sync(page)

        all_links = set()
        consecutive_empty = 0

        try:
            page.set_default_timeout(0)
            page.goto(start_url, wait_until="domcontentloaded")
            if not self._wait_for_page_ready(page):
                print(f"  Could not load results for {start_url}")
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
