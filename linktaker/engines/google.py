"""Google-specific bits: search URL building, pagination, and link extraction."""

from datetime import date
from urllib.parse import parse_qs, quote_plus, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..url_utils import is_valid_result_url
from .base import Engine

# Google's own hosts — its internal links must never reach the output file.
GOOGLE_BAD_NETLOC = ("google.com", "google.co.", "gstatic.com", "googleusercontent.com")

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


def extract_google_links(html_content: str) -> set:
    """Extract all result links from Google HTML."""
    links = set()
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        for selector in GOOGLE_LINK_SELECTORS:
            for a in soup.select(selector):
                href = unwrap_google_redirect(a.get("href", ""))
                if is_valid_result_url(href, GOOGLE_BAD_NETLOC):
                    links.add(href)

    except Exception as e:
        print(f"  Error parsing HTML: {e}")

    return links


def capability_notes(mode: str, sort: str, date_from: date = None,
                     date_until: date = None) -> list:
    """Point out what the News tab leaves out, since that is why --mode exists."""
    if mode == "nws":
        return ["Note: the News tab only lists portals Google already indexes as news "
                "sources — use --mode web (All tab) or --mode both to reach newer ones."]
    if mode == "both":
        return ["Note: --mode both searches the All tab and the News tab, "
                "so every keyword costs two searches."]
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
