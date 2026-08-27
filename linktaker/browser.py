import json
import os
import random
import shutil
import sys
import time
from itertools import count
from urllib.parse import unquote, urlparse, urlunparse

from .config import (
    USER_AGENTS, CAPTCHA_WAIT_TIMEOUT,
    PERSIST_PROFILE, BROWSER_PROFILE_DIR, FINGERPRINT_FILE,
    PAGE_DELAY_MIN, PAGE_DELAY_MAX,
    CAPTCHA_COOLDOWN_MIN, CAPTCHA_COOLDOWN_MAX,
)
from .deps import (
    PLAYWRIGHT_AVAILABLE, sync_playwright,
    STEALTH_AVAILABLE, stealth_sync,
    BROWSERFORGE_AVAILABLE, FingerprintGenerator,
)
from .engines import GOOGLE


# Playwright can override the user agent string, but not navigator.platform,
# navigator.userAgentData, or the Sec-CH-UA-Platform client hint Chrome attaches
# to every request. A macOS user agent coming out of a Chromium running on
# Windows contradicts all three at once — Google answers that with a page that
# holds no results rather than with a CAPTCHA, which looks like "nothing was
# scraped" instead of like a block. So the fingerprint follows the real host OS.
HOST_OS = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
HOST_OS_UA_MARKER = {"windows": "Windows", "macos": "Mac OS", "linux": "Linux"}[HOST_OS]


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


def reset_profile():
    """Delete the stored browser profile and its pinned fingerprint.

    Google flags profiles as well as addresses; once one is flagged, reusing it
    only keeps earning challenges. --fresh-profile calls this to start clean.
    """
    for path, is_dir in ((BROWSER_PROFILE_DIR, True), (FINGERPRINT_FILE, False)):
        target = os.path.abspath(path)
        if not os.path.exists(target):
            continue
        try:
            shutil.rmtree(target) if is_dir else os.remove(target)
            print(f"Removed {target}")
        except Exception as e:
            print(f"Could not remove {target}: {e}")


class BrowserManager:
    """Persistent browser manager — one browser instance reused across all pages."""

    def __init__(self, proxy=None):
        self._playwright = None
        self._browser = None
        self._context = None
        self._proxy = proxy

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
                    os=(HOST_OS,),
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

    def _fingerprint_opts(self):
        """Context options — user agent, locale, viewport — for this profile.

        Generated once and pinned to disk. A stored cookie jar that turns up
        under a different user agent and screen size on every run is a worse
        signal than either would be alone, so the fingerprint has to outlive the
        process the same way the cookies do.
        """
        if PERSIST_PROFILE and os.path.exists(FINGERPRINT_FILE):
            try:
                with open(FINGERPRINT_FILE, encoding="utf-8") as f:
                    pinned = json.load(f)
            except Exception as e:
                print(f"  Could not read {FINGERPRINT_FILE} ({e}) — generating a fresh one")
            else:
                # Pinning is only safe while the pinned value still matches the
                # machine. A file written on a different OS — or by the earlier
                # build that picked one at random — would otherwise keep the
                # contradiction alive for every future run.
                ua = pinned.get("user_agent", "")
                if HOST_OS_UA_MARKER in ua:
                    print(f"  Fingerprint: reusing the one pinned in {FINGERPRINT_FILE}")
                    return pinned
                print(f"  Pinned fingerprint claims a different OS than this machine "
                      f"({HOST_OS}) — discarding it and generating a matching one")

        opts = {}
        fp = self._generate_fingerprint()
        if fp:
            nav = getattr(fp, "navigator", None)
            if nav:
                if getattr(nav, "userAgent", None):
                    opts["user_agent"] = nav.userAgent
                if getattr(nav, "language", None):
                    opts["locale"] = nav.language

            screen = getattr(fp, "screen", None)
            width = int(getattr(screen, "width", 0) or 0) if screen else 0
            height = int(getattr(screen, "height", 0) or 0) if screen else 0
            opts["viewport"] = ({"width": width, "height": height}
                                if width >= 1024 and height
                                else {"width": 1366, "height": 768})
            print("  browserforge fingerprint applied")
        else:
            # Same constraint as above, and Firefox strings are out too: the
            # browser underneath is Chromium, so a Gecko user agent contradicts
            # the client hints just as loudly as the wrong OS does.
            usable = [ua for ua in USER_AGENTS
                      if HOST_OS_UA_MARKER in ua and "Firefox" not in ua]
            opts["user_agent"] = random.choice(usable or USER_AGENTS)
            opts["viewport"] = {"width": 1366, "height": 768}

        if PERSIST_PROFILE:
            try:
                with open(FINGERPRINT_FILE, "w", encoding="utf-8") as f:
                    json.dump(opts, f, indent=2)
                print(f"  Fingerprint pinned to {FINGERPRINT_FILE}")
            except Exception as e:
                print(f"  Could not pin fingerprint: {e}")

        return opts

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
                # A reused profile whose last run was killed reopens with the
                # "restore pages?" bubble covering the results.
                "--hide-crash-restore-bubble",
            ],
        }
        proxy_settings = playwright_proxy(self._proxy) if self._proxy else None
        if proxy_settings:
            launch_args["proxy"] = proxy_settings

        context_opts = dict(self._fingerprint_opts())
        context_opts["java_script_enabled"] = True
        if proxy_settings:
            # Chromium drops the launch-level credentials unless the context repeats them.
            context_opts["proxy"] = proxy_settings

        if PERSIST_PROFILE:
            # launch_persistent_context takes the launch flags and the context
            # options together, and hands back the context directly — there is
            # no separate browser object to keep, so close() has to allow for
            # self._browser staying None.
            profile_dir = os.path.abspath(BROWSER_PROFILE_DIR)
            os.makedirs(profile_dir, exist_ok=True)
            # Merged rather than double-unpacked: both dicts carry "proxy" when
            # one is configured, and **a, **b on a shared key is a TypeError.
            self._context = self._playwright.chromium.launch_persistent_context(
                profile_dir, **{**launch_args, **context_opts}
            )
            print(f"  Persistent profile: {profile_dir}")
        else:
            self._browser = self._playwright.chromium.launch(**launch_args)
            self._context = self._browser.new_context(**context_opts)

        return True

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
                # Say why, otherwise this looks like a silent failure.
                print(f"  No results after {initial_timeout_ms // 1000}s and no challenge page "
                      f"recognised — landed on: {page.url[:100]}")
                return False
        return self._wait_for_results(page, engine)

    def _wait_for_results(self, page, engine=GOOGLE):
        """Wait for search results. Distinguishes CAPTCHA from end-of-results."""
        results = page.query_selector_all(engine.results_selector)
        if results:
            return True

        # No results found — check if it's actually a CAPTCHA
        if self._is_captcha_page(page, engine):
            print(f"  CAPTCHA detected! Solve it in the browser window... (waiting up to {CAPTCHA_WAIT_TIMEOUT}s)")
            try:
                page.wait_for_selector(
                    engine.results_selector,
                    timeout=CAPTCHA_WAIT_TIMEOUT * 1000
                )
                cooldown = random.uniform(CAPTCHA_COOLDOWN_MIN, CAPTCHA_COOLDOWN_MAX)
                print(f"  Search results detected after CAPTCHA solve! "
                      f"Cooling off {cooldown:.0f}s before continuing...")
                # Picking straight back up at full speed after a challenge is a
                # reliable way to earn the next one.
                time.sleep(cooldown)
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
            self._wait_for_page_ready(page, engine)
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
            if not self._wait_for_page_ready(page, engine):
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

                # Pause before turning the page. Without this, "Next" is clicked
                # the moment the load finishes — a burst no reader produces, and
                # the pattern that draws the challenge in the first place.
                delay = random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX)
                print(f"  Waiting {delay:.1f}s before page {page_idx+2}...")
                time.sleep(delay)

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

                if not self._wait_for_page_ready(page, engine):
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
        """Shutdown browser.

        Closing the context is what flushes the profile's cookies to disk, so a
        run that skips this loses exactly the state the next run needs. With a
        persistent profile there is no separate browser to close.
        """
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
