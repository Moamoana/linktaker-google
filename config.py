"""
Configuration module for the News Link Harvester pipeline.

All runtime parameters are centralized here. Modify this file to
tune scraping behavior without touching engine or core logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet


# ---------------------------------------------------------------------------
# I/O paths
# ---------------------------------------------------------------------------

URLS_FILE_GOOGLE: str = "url.txt"
OUT_FILE_GOOGLE:  str = "output.txt"

URLS_FILE_BING:   str = "url_bing.txt"
OUT_FILE_BING:    str = "bing_without_site/output_bing.txt"

PROXIES_FILE:     str = "proxies.txt"
AUTH_FILE:        str = "auth.json"


# ---------------------------------------------------------------------------
# Scraping behavior
# ---------------------------------------------------------------------------

MAX_PAGES_PER_SEARCH:    int   = 100
CONSECUTIVE_EMPTY_PAGES: int   = 5
REQUEST_TIMEOUT:         int   = 10      # seconds per HTTP request
PARALLEL_WORKERS:        int   = 5
USE_PROXY:               bool  = False
RETRY_FAILED_PAGES:      int   = 3
USE_CLOUDFLARE_BYPASS:   bool  = True

# Fetch mode — controls which HTTP backend is used.
# Options: "playwright" | "curl" | "auto" (curl first, Playwright fallback)
FETCH_MODE: str = "playwright"


# ---------------------------------------------------------------------------
# Timing  (fast mode — expects occasional manual CAPTCHA resolution)
# ---------------------------------------------------------------------------

PAGE_DELAY_MIN:    float = 0.5   # seconds between successive result pages
PAGE_DELAY_MAX:    float = 1.5
KEYWORD_DELAY_MIN: float = 1.5   # seconds between distinct search URLs
KEYWORD_DELAY_MAX: float = 3.0


# ---------------------------------------------------------------------------
# Browser / fingerprinting
# ---------------------------------------------------------------------------

CAPTCHA_WAIT_TIMEOUT: int = 120   # seconds user has to solve a CAPTCHA

USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
)


# ---------------------------------------------------------------------------
# URL filtering
# ---------------------------------------------------------------------------

BLOCKED_DOMAINS: FrozenSet[str] = frozenset({
    # Social media
    "facebook.com", "fb.com", "twitter.com", "x.com", "instagram.com",
    "tiktok.com", "youtube.com", "youtu.be", "linkedin.com", "reddit.com",
    "snapchat.com", "pinterest.com", "tumblr.com", "telegram.org", "t.me",
    "whatsapp.com", "discord.com", "twitch.tv", "threads.net",
    "bluesky.social", "mastodon.social",
    # Developer / collaboration
    "github.com", "gitlab.com", "bitbucket.org", "stackoverflow.com",
    "dev.to", "medium.com",
    # Misc
    "quora.com", "behance.net", "dribbble.com", "vimeo.com",
    "wechat.com", "viber.com", "signal.org", "lemmy.ml", "kik.com",
    "omegle.com", "slack.com", "myspace.com", "nextdoor.com",
    "flipboard.com", "substack.com", "patreon.com", "kickstarter.com",
})


# ---------------------------------------------------------------------------
# Google News RSS (optional, no CAPTCHA but rate-limited)
# ---------------------------------------------------------------------------

USE_GOOGLE_RSS:  bool  = False
RSS_DECODE_DELAY: float = 2.0
