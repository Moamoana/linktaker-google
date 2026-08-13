"""
News Link Harvester — main entry point.

Collects article URLs from one or more search engines and writes
deduplicated, AMP-stripped results to plain-text output files.

Usage::

    python main.py --engine google
    python main.py --engine bing
    python main.py --engine all

Output files are configured in ``config.py``.
"""

from __future__ import annotations

import argparse
import logging
import random
import sys

from config import (
    AUTH_FILE,
    FETCH_MODE,
    OUT_FILE_BING,
    OUT_FILE_GOOGLE,
    OUT_FILE_YAHOO,
    OUT_FILE_DDG,
    PROXIES_FILE,
    URLS_FILE_BING,
    URLS_FILE_GOOGLE,
    URLS_FILE_YAHOO,
    URLS_FILE_DDG,
    USE_PROXY,
)
from core.browser_manager import (
    BrowserManager,
    _BROWSERFORGE_AVAILABLE,
    _PLAYWRIGHT_AVAILABLE,
    _STEALTH_AVAILABLE,
)
from core.utils import read_auth, read_proxies, read_urls


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Engine registry
# ---------------------------------------------------------------------------

_ENGINE_MAP: dict[str, tuple[str, str]] = {
    "google":     (URLS_FILE_GOOGLE, OUT_FILE_GOOGLE),
    "bing":       (URLS_FILE_BING,   OUT_FILE_BING),
    "yahoo":      (URLS_FILE_YAHOO,  OUT_FILE_YAHOO),
    "duckduckgo": (URLS_FILE_DDG,    OUT_FILE_DDG),
}


def _build_engine(name: str, browser_mgr: BrowserManager | None):
    """Instantiate the correct engine class for *name*."""
    if name == "google":
        from engines.google import GoogleEngine
        return GoogleEngine(browser_mgr)
    if name == "bing":
        from engines.bing import BingEngine
        return BingEngine(browser_mgr)
    if name == "yahoo":
        from engines.yahoo import YahooEngine
        return YahooEngine(browser_mgr)
    if name == "duckduckgo":
        from engines.duckduckgo import DuckDuckGoEngine
        return DuckDuckGoEngine(browser_mgr)
    raise ValueError(f"Unknown engine: {name!r}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(engine_name: str, proxies: list[str], auth: dict | None) -> None:
    """Execute a single engine's collection run.

    Args:
        engine_name: One of ``"google"``, ``"bing"``, ``"yahoo"``, or ``"duckduckgo"``.
        proxies:     List of proxy strings (may be empty).
        auth:        Basic-auth credentials dict, or ``None``.
    """
    urls_file, out_file = _ENGINE_MAP[engine_name]

    urls = read_urls(urls_file)
    if not urls:
        logger.error("No URLs found in %s — skipping %s", urls_file, engine_name)
        return

    logger.info(
        "Starting %s  |  %d URLs  |  output → %s",
        engine_name.upper(), len(urls), out_file,
    )

    browser_mgr: BrowserManager | None = None
    if FETCH_MODE in ("auto", "playwright") and _PLAYWRIGHT_AVAILABLE:
        proxy = random.choice(proxies) if proxies else None
        browser_mgr = BrowserManager(proxy=proxy)
        logger.info(
            "Browser ready  |  stealth=%s  fingerprint=%s",
            _STEALTH_AVAILABLE, _BROWSERFORGE_AVAILABLE,
        )

    engine = _build_engine(engine_name, browser_mgr)

    try:
        saved = engine.run(urls, out_file)
    finally:
        if browser_mgr:
            browser_mgr.close()

    logger.info("Done  |  engine=%s  new_urls=%d  output=%s", engine_name, saved, out_file)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="News Link Harvester — collect article URLs from Google / Bing / Yahoo / DuckDuckGo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py --engine google\n"
            "  python main.py --engine bing\n"
            "  python main.py --engine yahoo\n"
            "  python main.py --engine duckduckgo\n"
            "  python main.py --engine all\n"
        ),
    )
    parser.add_argument(
        "--engine",
        choices=["google", "bing", "yahoo", "duckduckgo", "all"],
        default="google",
        metavar="ENGINE",
        help="Search engine to harvest (google | bing | yahoo | duckduckgo | all).  Default: google",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    proxies = read_proxies(PROXIES_FILE) if USE_PROXY else []
    auth = read_auth(AUTH_FILE)

    targets = ["google", "bing", "yahoo", "duckduckgo"] if args.engine == "all" else [args.engine]

    for engine_name in targets:
        run(engine_name, proxies, auth)


if __name__ == "__main__":
    main()
