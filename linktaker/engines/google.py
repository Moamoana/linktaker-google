"""Google-specific bits: search URL building, pagination, and link extraction."""

import re
from datetime import date
from urllib.parse import parse_qs, quote_plus, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..url_utils import is_valid_result_url
from .base import Engine

# Google's own hosts — its internal links must never reach the output file.
# The ad hosts matter more now than they used to: the sweep below reads the raw
# page source, where ad and conversion-tracking URLs sit in plain text even
# though no result anchor ever pointed at them.
GOOGLE_BAD_NETLOC = ("google.com", "google.co.", "gstatic.com", "googleusercontent.com",
                     "googleadservices.com", "googlesyndication.com", "doubleclick.net",
                     "googletagmanager.com", "google-analytics.com")

# Hosts that only ever serve page furniture — thumbnails, avatars, markup
# vocabularies. The sweep below reaches them constantly and none are results.
GOOGLE_ASSET_HOSTS = ("googleapis.com", "ytimg.com", "ggpht.com",
                      "schema.org", "w3.org")

RESULTS_PER_PAGE = 10

# Covers three markups: the News tab (`div.SoaBEf`), the All tab as rendered by
# a real browser (`div.g` / `div.MjjYud` / `div.yuRUbf` / `div.tF2Cxc`), and the
# script-less HTML curl_cffi gets back, where every result is a `/url?q=` link.
GOOGLE_LINK_SELECTORS = (
    "div.g a[href]",
    "div.SoaBEf a[href]",
    "div.yuRUbf a[href]",
    "div.tF2Cxc a[href]",
    "div.MjjYud a[href]",
    "a[jsname='UWckNb']",
    "a[href^='/url?q=']",
)


def _google_date(d: date) -> str:
    """Google's tbs date format — M/D/YYYY, no zero padding."""
    return f"{d.month}/{d.day}/{d.year}"


def build_tbs(date_from: date = None, date_until: date = None, sort: str = "relevance") -> str:
    """
    Build the Google `tbs` parameter from a date range and a sort order.

    - custom date range -> cdr:1,cd_min:8/8/2026,cd_max:8/16/2026
    - sort latest       -> sbd:1   (sort by date; relevance is Google's default)
    """
    parts = []
    if date_from or date_until:
        parts.append("cdr:1")
        if date_from:
            parts.append(f"cd_min:{_google_date(date_from)}")
        if date_until:
            parts.append(f"cd_max:{_google_date(date_until)}")
    if sort == "latest":
        parts.append("sbd:1")
    return ",".join(parts)


def build_google_search_url(keyword: str, date_from: date = None, date_until: date = None,
                            sort: str = "relevance", mode: str = "web") -> str:
    """Build a Google search URL for one keyword.

    mode: "web" for the All tab (Google's default vertical), "nws" for the News
    tab. Both accept the same `tbs` date range, so --from/--until work either way.
    """
    params = {"q": keyword.strip()}
    if mode == "nws":
        params["tbm"] = "nws"

    tbs = build_tbs(date_from, date_until, sort)
    if tbs:
        params["tbs"] = tbs

    return "https://www.google.com/search?" + urlencode(params, quote_via=quote_plus)


def build_google_paginated_url(base_url: str, page_index: int) -> str:
    """Google pages via `start=` — 0, 10, 20, ..."""
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["start"] = [str(page_index * RESULTS_PER_PAGE)]

    new_query = urlencode(
        {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in query.items()},
        doseq=True,
    )
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def unwrap_google_redirect(url: str) -> str:
    """Turn Google's `/url?q=<target>` wrapper into the URL it points at.

    The script-less HTML — what curl_cffi gets, and what the All tab falls back
    to — wraps every result this way. Direct links come back untouched, and a
    wrapper whose target cannot be read returns empty so the caller drops it.
    """
    if "/url?" not in url:
        return url

    try:
        query = parse_qs(urlparse(url).query)
        return (query.get("q") or query.get("url") or [""])[0]
    except Exception:
        return ""


# A URL as it appears in the page source, stopping at whatever quoting or
# bracketing encloses it in the surrounding JSON.
RESULT_URL_RE = re.compile(r'https?://[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}(?:/[^\s"\'<>\\)\]}]*)?')

# Trailing punctuation the enclosing JSON contributes, never part of the URL.
URL_TRAILING_JUNK = '\\",\'.;:'


def _unescape_page_source(html_content: str) -> str:
    """Undo the JS string escaping used inside the page's embedded data blobs.

    Google writes `\\/`, `\\u003d` and `\\u0026` in there. Left as-is, a swept
    URL gets cut short at its first query separator — `watch?v` instead of
    `watch?v=3K064ikq_Ko`.
    """
    return (html_content
            .replace("\\/", "/")
            .replace("\\u003d", "=").replace("\\u003D", "=")
            .replace("\\u0026", "&").replace("\\u0026amp;", "&"))


def sweep_result_urls(html_content: str) -> set:
    """Recover destination URLs from the raw page source.

    Google no longer puts destinations in the markup. Every result anchor now
    reads `/goto?url=<blob>`, and the blob is an encrypted protobuf — there is
    no URL inside it to unwrap, and resolving one means a network round trip per
    result. The destinations are still in the page, inside the JSON blobs its
    own JavaScript renders from, so a pattern sweep is what is left.

    Deliberately permissive: it also picks up publisher home pages, carousel
    entries and thumbnails. `is_valid_result_url` and the news filter behind it
    are what decide which of those survive, which is where that judgement
    already lives for every other engine.
    """
    links = set()
    for match in RESULT_URL_RE.findall(_unescape_page_source(html_content or "")):
        url = match.rstrip(URL_TRAILING_JUNK)
        if any(bad in url for bad in GOOGLE_BAD_NETLOC + GOOGLE_ASSET_HOSTS):
            continue
        if is_valid_result_url(url, GOOGLE_BAD_NETLOC):
            links.add(url)
    return links


def extract_google_links(html_content: str) -> set:
    """Extract all result links from Google HTML.

    Two paths, unioned: the anchor selectors still work on the script-less HTML
    curl_cffi receives and on the older markup, while `sweep_result_urls` covers
    the browser-rendered page, where the anchors carry nothing usable.
    """
    links = set()
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        for selector in GOOGLE_LINK_SELECTORS:
            for a in soup.select(selector):
                href = unwrap_google_redirect(a.get("href", ""))
                if is_valid_result_url(href, GOOGLE_BAD_NETLOC):
                    links.add(href)

        links |= sweep_result_urls(html_content)

    except Exception as e:
        print(f"  Error parsing HTML: {e}")

    return links


def capability_notes(mode: str, sort: str, date_from: date = None,
                     date_until: date = None) -> list:
    """Point out what the News tab leaves out, since that is why --mode exists."""
    # The News tab stopped being scrapeable: its result anchors are all
    # `/goto?url=<encrypted blob>`, and unlike the All tab it embeds no
    # destination URLs anywhere in the page source, so there is nothing left to
    # recover. It returns zero links rather than failing loudly, which is worth
    # saying out loud before a run spends its searches there.
    NWS_DEAD = ("Warning: the News tab yields no links — Google serves its results "
                "as encrypted /goto redirects with no destination anywhere in the "
                "page. Use --mode web; it reaches news portals too.")

    if mode == "nws":
        return [NWS_DEAD]
    if mode == "both":
        return [NWS_DEAD,
                "Note: --mode both still spends two searches per keyword, and the "
                "News tab half of them returns nothing."]
    return []


GOOGLE = Engine(
    name="google",
    # The All tab is the default: the News tab is limited to portals Google has
    # already classified as news sources, so a new one never shows up there.
    default_mode="web",
    build_search_url=build_google_search_url,
    build_paginated_url=build_google_paginated_url,
    extract_links=extract_google_links,
    results_selector="div.g, div.SoaBEf, div.yuRUbf, div.tF2Cxc, div.MjjYud",
    captcha_selector="#captcha-form, #recaptcha, iframe[src*='recaptcha'], "
                     "form[action*='sorry'], #g-recaptcha, div.g-recaptcha",
    captcha_url_markers=("/sorry/", "google.com/sorry"),
    capability_notes=capability_notes,
    next_selector="#pnnext",
    # Google serves several markups for its block page; the wording is the one
    # constant, so match on it too instead of trusting the URL alone.
    captcha_text_markers=("unusual traffic", "not a robot", "about this page"),
)
