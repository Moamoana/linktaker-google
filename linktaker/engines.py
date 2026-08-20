"""Search engine adapters.

Everything that differs between Google and Bing lives here: how a keyword turns
into a search URL, how pages are walked, which selectors mark results, a
CAPTCHA, and the "next page" control. `fetchers.py` and `browser.py` stay engine
agnostic — they just read these fields.
"""

from dataclasses import dataclass
from typing import Callable

from .bing import (
    build_bing_paginated_url, build_bing_search_url, capability_notes, extract_bing_links,
)
from .keywords import build_search_url as build_google_search_url
from .url_utils import build_paginated_url as build_google_paginated_url, extract_google_links


def _no_notes(mode: str, sort: str, has_dates: bool) -> list:
    return []


@dataclass(frozen=True)
class Engine:
    """One search engine's flavour of the shared crawl flow."""

    name: str
    default_mode: str                 # vertical used when --mode is not given
    build_search_url: Callable        # (keyword, date_from, date_until, sort, mode) -> url
    build_paginated_url: Callable     # (search_url, page_index) -> url
    extract_links: Callable           # (html) -> set of links
    results_selector: str             # results are on screen once this matches
    captcha_selector: str             # CSS that marks a CAPTCHA / challenge page
    captcha_url_markers: tuple        # URL fragments that mean "challenge page"
    capability_notes: Callable = _no_notes
    next_selector: str = None         # click to paginate; None = navigate by URL
    captcha_text_markers: tuple = ()  # visible text that marks a challenge page


GOOGLE = Engine(
    name="google",
    default_mode="nws",
    build_search_url=build_google_search_url,
    build_paginated_url=build_google_paginated_url,
    extract_links=extract_google_links,
    results_selector="div.g, div.SoaBEf, div.yuRUbf, div.MjjYud",
    captcha_selector="#captcha-form, #recaptcha, iframe[src*='recaptcha'], "
                     "form[action*='sorry'], #g-recaptcha, div.g-recaptcha",
    captcha_url_markers=("/sorry/", "google.com/sorry"),
    next_selector="#pnnext",
)

BING = Engine(
    name="bing",
    # Bing Search is the vertical that honours --from/--until, so it is the default.
    default_mode="web",
    build_search_url=build_bing_search_url,
    build_paginated_url=build_bing_paginated_url,
    extract_links=extract_bing_links,
    results_selector="li.b_algo, div.news-card, div.newsitem",
    captcha_selector="#bIframeChallenge, iframe[src*='challenge'], form[action*='challenge']",
    captcha_url_markers=("/challenge", "bing.com/turing"),
    capability_notes=capability_notes,
    # Bing News has no "next" button (infinite scroll), so both verticals page by URL.
    next_selector=None,
    captcha_text_markers=("solve the challenge", "one last step"),
)

ENGINES = {engine.name: engine for engine in (GOOGLE, BING)}


def get_engine(name: str) -> Engine:
    """Look up an engine by CLI name."""
    return ENGINES[name]
