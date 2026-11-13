"""Yahoo-specific bits: search URL building, pagination, and link extraction.

Same shape as `bing.py` — see `__init__.py` for how it is wired into the shared
crawl flow.
"""

import re
from datetime import date
from urllib.parse import parse_qs, quote_plus, unquote, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..url_utils import is_valid_result_url
from .base import Engine

# Yahoo's own hosts: the search pages themselves, ad servers, and boilerplate.
YAHOO_BAD_NETLOC = ("search.yahoo.com", "ads.yahoo.com", "beap.gemini.yahoo.com",
                    "adspecs.yahoo.com", "policies.yahoo.com", "legal.yahoo.com",
                    "help.yahoo.com", "guce.yahoo.com")

RESULTS_PER_PAGE = 10
YAHOO_SEARCH_HOST = "https://id.search.yahoo.com"

# Organic results only — Yahoo keeps ads outside `div.algo`.
YAHOO_LINK_SELECTORS = (
    "div.algo div.compTitle a[href]",
    "div.algo h3.title a[href]",
)

# Tracking links look like .../RU=<url-encoded target>/RK=2/RS=<signature>
REDIRECT_TARGET = re.compile(r"/RU=(.+?)/R[KS]=")

# Yahoo offers no custom date range, only these relative buckets.
TIME_FILTERS = ((1, "d"), (7, "w"), (31, "m"))


def relative_time_filter(date_from: date = None, date_until: date = None, today: date = None):
    """Pick the Yahoo `btf` bucket that best covers the requested range.

    Yahoo's filter is always relative to now (past day / week / month), so an
    arbitrary --from/--until can only be approximated. Returns None when the
    range reaches further back than a month, or when nothing was requested.
    """
    if not date_from and not date_until:
        return None

    today = today or date.today()
    start = date_from or date_until
    days_back = (today - start).days

    for limit, code in TIME_FILTERS:
        if days_back <= limit:
            return code
    return None


def build_yahoo_search_url(keyword: str, date_from: date = None, date_until: date = None,
                           sort: str = "relevance", mode: str = "web") -> str:
    """Build a Yahoo search URL for one keyword.

    Only Yahoo's web index is used: `news.search.yahoo.com` is unreachable and
    Yahoo web search exposes neither a custom date range nor date ordering.
    `capability_notes()` spells out what the engine drops.
    """
    params = {"p": keyword.strip()}

    btf = relative_time_filter(date_from, date_until)
    if btf:
        params["btf"] = btf

    return YAHOO_SEARCH_HOST + "/search?" + urlencode(params, quote_via=quote_plus)


def build_yahoo_paginated_url(base_url: str, page_index: int) -> str:
    """Yahoo pages via `b=` — 1, 11, 21, ... (page 1 carries no parameter)."""
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query, keep_blank_values=True)

    if page_index <= 0:
        query.pop("b", None)
    else:
        query["b"] = [str(page_index * RESULTS_PER_PAGE + 1)]

    new_query = urlencode(
        {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in query.items()},
        doseq=True, quote_via=quote_plus,
    )
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def decode_yahoo_redirect(url: str) -> str:
    """Turn a r.search.yahoo.com tracking link into the article URL it points at.

    Non-tracking URLs are returned untouched; a tracking URL whose target cannot
    be read returns empty so the caller drops it.
    """
    if "/RU=" not in url:
        return url

    match = REDIRECT_TARGET.search(url)
    if not match:
        return ""

    target = unquote(match.group(1))
    # Yahoo double-encodes some targets (%253a -> %3a -> :).
    if target.startswith("http%3") or target.startswith("https%3"):
        target = unquote(target)
    return target


def extract_yahoo_links(html_content: str) -> set:
    """Extract organic result links from a Yahoo search page."""
    links = set()
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        for selector in YAHOO_LINK_SELECTORS:
            for a in soup.select(selector):
                href = decode_yahoo_redirect(a.get("href", ""))
                if is_valid_result_url(href, YAHOO_BAD_NETLOC):
                    links.add(href)

    except Exception as e:
        print(f"  Error parsing HTML: {e}")

    return links


def capability_notes(mode: str, sort: str, date_from: date = None,
                     date_until: date = None) -> list:
    """Say plainly which parts of the request Yahoo cannot honour."""
    notes = []

    if mode in ("nws", "both"):
        notes.append("Note: Yahoo News search is not supported — "
                     "crawling Yahoo web search instead.")

    if sort == "latest":
        notes.append("Note: Yahoo has no date ordering — results come back by relevance.")

    if date_from or date_until:
        btf = relative_time_filter(date_from, date_until)
        if btf:
            bucket = {"d": "past day", "w": "past week", "m": "past month"}[btf]
            notes.append(f"Note: Yahoo has no custom date range — using its '{bucket}' filter "
                         f"(btf={btf}) as the closest match; some results may fall outside "
                         f"the requested range.")
        else:
            notes.append("Note: Yahoo has no custom date range and the requested range reaches "
                         "further back than a month — crawling without a date filter.")

    return notes


YAHOO = Engine(
    name="yahoo",
    # Yahoo News search is unreachable, so the web index is the only vertical.
    default_mode="web",
    build_search_url=build_yahoo_search_url,
    build_paginated_url=build_yahoo_paginated_url,
    extract_links=extract_yahoo_links,
    results_selector="div.algo",
    captcha_selector="form[action*='challenge'], div.captcha, iframe[src*='challenge']",
    # The consent wall blocks results the same way a challenge does, so it is
    # handled through the same "solve it in the window" wait.
    captcha_url_markers=("/challenge", "guce.yahoo.com", "consent.yahoo.com"),
    capability_notes=capability_notes,
    # Yahoo has a Next button, but the verified `&b=` offsets are simpler.
    next_selector=None,
    captcha_text_markers=("unusual traffic", "verify you are"),
)
