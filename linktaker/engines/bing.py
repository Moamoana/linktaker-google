"""Bing-specific bits: search URL building, pagination, and link extraction.

Kept separate from the Google helpers so every engine can share the same crawl
flow in `fetchers.py` / `browser.py` — see `__init__.py` for the glue.
"""

import base64
from datetime import date
from urllib.parse import parse_qs, quote, quote_plus, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..url_utils import is_valid_result_url
from .base import Engine

# Bing wraps organic results in its own redirector and marks ads with /aclick.
BING_BAD_NETLOC = ("bing.com", "bing.net", "go.microsoft.com", "login.live.com",
                   "microsofttranslator.com")

RESULTS_PER_PAGE = 10
EPOCH = date(1970, 1, 1)

# Organic results only — `li.b_ad` (ads) is deliberately not in this list.
BING_LINK_SELECTORS = (
    "li.b_algo h2 a[href]",
    "li.b_algo div.b_title a[href]",
    "div.news-card a.title[href]",
    "div.newsitem a.title[href]",
)


def epoch_days(day: date) -> int:
    """Bing's date filter counts days since 1970-01-01."""
    return (day - EPOCH).days


def build_bing_search_url(keyword: str, date_from: date = None, date_until: date = None,
                          sort: str = "relevance", mode: str = "web", geo=None) -> str:
    """Build a Bing search URL for one keyword.

    mode: "web" for Bing Search, "nws" for Bing News.

    Bing splits the two capabilities across its verticals: the web index accepts a
    custom date range (`filters=ex1:"ez5_<from>_<until>"`), while only Bing News
    can order results by date (`qft=sortbydate="1"`). `capability_notes()` reports
    whichever half the chosen vertical cannot honour.

    geo: a `geo.Geo` (from --geo) or None. Bing spells the country `cc=` and
    pairs it with a market, `mkt=<lang>-<COUNTRY>` — Google's `gl` equivalent,
    covering both verticals.
    """
    path = "/news/search" if mode == "nws" else "/search"
    params = {"q": keyword.strip()}
    if geo:
        params["cc"] = geo.code
        params["mkt"] = geo.market

    extra = ""
    if mode == "nws":
        if sort == "latest":
            # Quotes are part of the value Bing expects, so build this by hand.
            extra = '&qft=' + quote('sortbydate="1"', safe="")
    elif date_from or date_until:
        start = epoch_days(date_from) if date_from else 0
        end = epoch_days(date_until) if date_until else epoch_days(date.today())
        extra = "&filters=" + quote(f'ex1:"ez5_{start}_{end}"', safe="")

    return "https://www.bing.com" + path + "?" + urlencode(params, quote_via=quote_plus) + extra


def build_bing_paginated_url(base_url: str, page_index: int) -> str:
    """Bing pages via `first=` — 1, 11, 21, ... (page 1 carries no parameter)."""
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query, keep_blank_values=True)

    if page_index <= 0:
        query.pop("first", None)
    else:
        query["first"] = [str(page_index * RESULTS_PER_PAGE + 1)]

    new_query = urlencode(
        {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in query.items()},
        doseq=True, quote_via=quote_plus,
    )
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def decode_bing_redirect(url: str) -> str:
    """Unwrap https://www.bing.com/ck/a?...&u=a1<base64> into the real target URL.

    Returns the original URL untouched when it is not a Bing redirect, and an
    empty string when it is one but cannot be decoded (an internal link).
    """
    if "bing.com/ck/a" not in url:
        return url

    try:
        wrapped = parse_qs(urlparse(url).query).get("u", [""])[0]
        if not wrapped.startswith("a1"):
            return ""
        payload = wrapped[2:]
        payload += "=" * (-len(payload) % 4)
        return base64.urlsafe_b64decode(payload).decode("utf-8", "replace")
    except Exception:
        return ""


def extract_bing_links(html_content: str) -> set:
    """Extract organic result links from a Bing search or Bing News page."""
    links = set()
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        for selector in BING_LINK_SELECTORS:
            for a in soup.select(selector):
                href = decode_bing_redirect(a.get("href", ""))
                if is_valid_result_url(href, BING_BAD_NETLOC):
                    links.add(href)

    except Exception as e:
        print(f"  Error parsing HTML: {e}")

    return links


def capability_notes(mode: str, sort: str, date_from: date = None,
                     date_until: date = None, geo=None) -> list:
    """Warn about the half of the request the chosen Bing vertical cannot serve."""
    notes = []
    if mode == "both":
        return ["Note: --mode both searches Bing Search (which honours --from/--until) "
                "and Bing News (which honours --sort latest), so every keyword costs "
                "two searches."]
    if mode == "nws" and (date_from or date_until):
        notes.append("Note: Bing News ignores custom date ranges — "
                     "use --mode web so --from/--until take effect.")
    if mode == "web" and sort == "latest":
        notes.append("Note: Bing web search has no date ordering — "
                     "use --mode nws for newest-first results.")
    return notes


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
