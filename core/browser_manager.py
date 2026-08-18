"""
Persistent Playwright browser manager with stealth, fingerprinting,
and automatic CAPTCHA pause-and-resume.

A single ``BrowserManager`` instance is shared across all search URLs
to avoid the cost of launching a new browser process per request.
"""

from __future__ import annotations

import logging
import random
from typing import Optional

from config import CAPTCHA_WAIT_TIMEOUT, USE_PROXY, USER_AGENTS, USE_SECURE_DNS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional dependency guards
# ---------------------------------------------------------------------------

try:
    from playwright.sync_api import BrowserContext, Page, sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    logger.warning(
        "playwright not installed — "
        "install with: pip install playwright && playwright install chromium"
    )

try:
    from playwright_stealth import Stealth
    _STEALTH_AVAILABLE = True
except ImportError:
    Stealth = None  # type: ignore[assignment, misc]
    _STEALTH_AVAILABLE = False
    logger.warning("playwright-stealth not installed — install with: pip install playwright-stealth")

try:
    from browserforge.fingerprints import FingerprintGenerator
    _BROWSERFORGE_AVAILABLE = True
except ImportError:
    FingerprintGenerator = None  # type: ignore[assignment, misc]
    _BROWSERFORGE_AVAILABLE = False
    logger.warning("browserforge not installed — install with: pip install browserforge")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_DESKTOP_WIDTH: int = 1024
_MAX_FINGERPRINT_ATTEMPTS: int = 5
_MOBILE_KEYWORDS: tuple[str, ...] = ("Mobile", "Android", "iPhone", "iPad", "iPod")

_CAPTCHA_SELECTORS: tuple[str, ...] = (
    "#captcha-form",
    "#recaptcha",
    'iframe[src*="recaptcha"]',
    'form[action*="sorry"]',
    "#g-recaptcha",
    "div.g-recaptcha",
)

_LAUNCH_ARGS: tuple[str, ...] = (
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
)


# ---------------------------------------------------------------------------
# BrowserManager
# ---------------------------------------------------------------------------

class BrowserManager:
    """Manages a single persistent Chromium instance across all search URLs.

    Usage::

        mgr = BrowserManager()
        try:
            ctx = mgr.context          # lazy-initialised
            ...
        finally:
            mgr.close()

    Attributes:
        proxy: Optional proxy address forwarded to the browser launch args.
    """

    def __init__(self, proxy: Optional[str] = None, force_proxy: bool = False) -> None:
        self.proxy = proxy
        self._force_proxy = force_proxy
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None

    # ------------------------------------------------------------------
    # Context initialisation
    # ------------------------------------------------------------------

    @property
    def context(self) -> Optional[BrowserContext]:
        """Return the active ``BrowserContext``, launching the browser if needed."""
        if self._context is None:
            self._start()
        return self._context

    def _start(self) -> bool:
        """Launch Chromium with stealth and fingerprint settings."""
        if not _PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright is not installed; cannot start browser")
            return False

        self._playwright = sync_playwright().start()

        launch_kwargs: dict = {
            "headless": False,
            "args": list(_LAUNCH_ARGS),
        }
        if USE_SECURE_DNS:
            launch_kwargs["args"].extend([
                "--enable-features=SecureDns",
                "--force-fieldtrials=SecureDns/Enable",
                "--force-fieldtrial-params=SecureDns.Enable:Mode/secure/Templates/https%3A%2F%2Fcloudflare-dns.com%2Fdns-query"
            ])
            
        if self.proxy and (USE_PROXY or self._force_proxy):
            launch_kwargs["proxy"] = {"server": self.proxy}

        self._browser = self._playwright.chromium.launch(**launch_kwargs)
        self._context = self._browser.new_context(**self._build_context_options())
        return True

    def _build_context_options(self) -> dict:
        """Construct Playwright context options, applying browserforge if available."""
        opts: dict = {"java_script_enabled": True}
        fingerprint = self._generate_fingerprint()

        if fingerprint:
            nav = getattr(fingerprint, "navigator", None)
            if nav:
                if getattr(nav, "userAgent", None):
                    opts["user_agent"] = nav.userAgent
                if getattr(nav, "language", None):
                    opts["locale"] = nav.language

            screen = getattr(fingerprint, "screen", None)
            if screen:
                w = int(getattr(screen, "width", 0) or 0)
                h = int(getattr(screen, "height", 0) or 0)
                opts["viewport"] = (
                    {"width": w, "height": h}
                    if w >= _MIN_DESKTOP_WIDTH
                    else {"width": 1366, "height": 768}
                )
            logger.debug("browserforge fingerprint applied")
        else:
            opts["user_agent"] = random.choice(USER_AGENTS)
            opts["viewport"] = {"width": 1366, "height": 768}

        return opts

    def _generate_fingerprint(self):
        """Generate a desktop-only fingerprint, retrying on mobile results."""
        if not _BROWSERFORGE_AVAILABLE:
            return None

        for attempt in range(_MAX_FINGERPRINT_ATTEMPTS):
            try:
                fp = FingerprintGenerator(  # type: ignore[misc]
                    browser="chrome",
                    os=("windows", "macos", "linux"),
                ).generate()

                ua = getattr(getattr(fp, "navigator", None), "userAgent", "") or ""
                if any(kw in ua for kw in _MOBILE_KEYWORDS):
                    logger.debug("Attempt %d: discarding mobile UA", attempt + 1)
                    continue

                w = int(getattr(getattr(fp, "screen", None), "width", 0) or 0)
                if w < _MIN_DESKTOP_WIDTH:
                    logger.debug("Attempt %d: discarding narrow viewport (%dpx)", attempt + 1, w)
                    continue

                return fp
            except Exception:
                logger.exception("Fingerprint generation error on attempt %d", attempt + 1)
                return None

        logger.warning("Could not generate desktop fingerprint; using defaults")
        return None

    # ------------------------------------------------------------------
    # Page helpers
    # ------------------------------------------------------------------

    def new_page(self) -> Optional[Page]:
        """Open a new page in the current context with stealth applied."""
        ctx = self.context
        if ctx is None:
            return None
        page = ctx.new_page()
        if _STEALTH_AVAILABLE and Stealth is not None:
            try:
                Stealth().apply_stealth_sync(page)
            except Exception:
                logger.debug("playwright-stealth application failed", exc_info=True)
        return page

    def is_captcha_page(self, page: Page) -> bool:
        """Return ``True`` when the page appears to show a CAPTCHA or block.

        Args:
            page: Active Playwright page.

        Returns:
            ``True`` when a known CAPTCHA pattern is detected.
        """
        if "/sorry/" in page.url or "google.com/sorry" in page.url:
            return True
        return any(page.query_selector(sel) is not None for sel in _CAPTCHA_SELECTORS)

    def wait_for_results(self, page: Page, result_selector: str) -> bool:
        """Block until search results are visible or a CAPTCHA is solved.

        When a CAPTCHA is detected the method prints an instruction for the
        operator and blocks for up to ``CAPTCHA_WAIT_TIMEOUT`` seconds.

        Args:
            page:            Active Playwright page.
            result_selector: CSS selector identifying successful search results.

        Returns:
            ``True`` when results are eventually visible, ``False`` on timeout.
        """
        if page.query_selector_all(result_selector):
            return True

        if self.is_captcha_page(page):
            logger.warning(
                "CAPTCHA detected on %s — solve it in the browser window "
                "(timeout: %ds)", page.url, CAPTCHA_WAIT_TIMEOUT,
            )
            try:
                page.wait_for_selector(
                    result_selector, timeout=CAPTCHA_WAIT_TIMEOUT * 1000
                )
                logger.info("Search results visible after CAPTCHA resolution")
                return True
            except Exception:
                logger.error("Timed out waiting for CAPTCHA resolution")
                return False

        logger.debug("No results on page and no CAPTCHA detected")
        return False

    def wait_for_page_ready(
        self, page: Page, result_selector: str, timeout_ms: int = 15_000
    ) -> bool:
        """Wait for page load then delegate to :meth:`wait_for_results`.

        Waits only for the result selector (or a CAPTCHA indicator) to appear
        rather than full network-idle, keeping page transitions fast.

        Args:
            page:            Active Playwright page.
            result_selector: CSS selector for expected search results.
            timeout_ms:      Selector wait timeout in milliseconds.

        Returns:
            ``True`` when results are ready, ``False`` otherwise.
        """
        try:
            page.wait_for_selector(
                f"{result_selector}, #captcha-form, #recaptcha, "
                'form[action*="sorry"], #g-recaptcha',
                timeout=timeout_ms,
            )
        except Exception:
            if not self.is_captcha_page(page):
                return False

        return self.wait_for_results(page, result_selector)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Cleanly shut down the browser and Playwright runtime."""
        for attr in ("_context", "_browser", "_playwright"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.close() if attr != "_playwright" else obj.stop()
                except Exception:
                    pass
                setattr(self, attr, None)
        logger.info("Browser closed")
