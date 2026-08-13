"""
Abstract base class for all search-engine collectors.

Every engine (Google, Bing, …) must subclass ``BaseEngine`` and
implement :meth:`collect`, which returns a set of clean article URLs
for a single search query.
"""

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Optional

from config import KEYWORD_DELAY_MAX, KEYWORD_DELAY_MIN
from core.browser_manager import BrowserManager
from core.utils import append_url, load_existing_urls, strip_amp

logger = logging.getLogger(__name__)


class BaseEngine(ABC):
    """Abstract search-engine URL collector.

    Subclasses implement :meth:`collect` to handle engine-specific
    pagination, redirect decoding, and link extraction.

    Args:
        browser_mgr: Shared browser instance (``None`` in curl-only mode).
    """

    #: Human-readable engine label used in log messages.
    name: str = "base"

    def __init__(self, browser_mgr: Optional[BrowserManager] = None) -> None:
        self._browser = browser_mgr

    @abstractmethod
    def collect(self, search_url: str) -> set[str]:
        """Harvest article URLs from a single search query page.

        Args:
            search_url: Fully-qualified search URL (e.g. a Google or Bing query).

        Returns:
            Set of clean, AMP-stripped article URLs.
        """

    def run(self, urls: list[str], out_file: str) -> int:
        """Execute :meth:`collect` over every entry in *urls*.

        Handles deduplication, immediate persistence, and the inter-keyword
        delay to reduce burst-rate detection.

        Args:
            urls:     List of search query URLs to process.
            out_file: Path to the output ``.txt`` file.

        Returns:
            Total number of **new** URLs persisted during this run.
        """
        existing = load_existing_urls(out_file)
        seen: set[str] = set()
        saved = 0

        shuffled = random.sample(urls, len(urls))

        for idx, url in enumerate(shuffled):
            logger.info("[%s] Processing %d/%d: %s", self.name, idx + 1, len(shuffled), url)

            try:
                results = self.collect(url)
            except Exception:
                logger.exception("[%s] Unhandled error while processing %s", self.name, url)
                results = set()

            for link in results:
                clean = strip_amp(link)
                if clean and clean not in existing and clean not in seen:
                    seen.add(clean)
                    append_url(clean, out_file)
                    saved += 1

            logger.info(
                "[%s] %s — %d results | %d new this run | %d total saved",
                self.name, url, len(results), saved, len(existing) + len(seen),
            )

            if idx < len(shuffled) - 1:
                delay = random.uniform(KEYWORD_DELAY_MIN, KEYWORD_DELAY_MAX)
                logger.debug("Waiting %.1fs before next URL", delay)
                time.sleep(delay)

        return saved
