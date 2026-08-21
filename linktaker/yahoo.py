"""Yahoo-specific bits: search URL building, pagination, and link extraction."""

import re
from datetime import date
from urllib.parse import parse_qs, quote_plus, unquote, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from .url_utils import is_valid_result_url

# Yahoo wraps results in redirectors and has its own internal properties.
YAHOO_BAD_NETLOC = (
    "search.yahoo.com", "news.search.yahoo.com",
    "login.yahoo.com", "mail.yahoo.com", "help.yahoo.com", "my.yahoo.com"
)

RESULTS_PER_PAGE = 10

YAHOO_LINK_SELECTORS = (
    "div.NewsArticle a.thmb[href]",
    "div.NewsArticle h4.s-title a[href]",
    "ul.compArticleList li div h4 a[href]",
    "div.compTitle a[href]",
    "h3.title a[href]",
    "div.algo-sr a[href]",
    ".compTitle a"
)


def build_yahoo_search_url(keyword: str, date_from: date = None, date_until: date = None,
                           sort: str = "relevance", mode: str = "web") -> str:
    """Build a Yahoo search URL for one keyword."""
    subdomain = "news.search.yahoo.com" if mode == "nws" else "search.yahoo.com"
    path = "/search"
    params = {"p": keyword.strip()}

    # Yahoo sorting/date parameters are largely undocumented. 
    # 'age=1d' or 'age=1w' are commonly used for 'Past day' or 'Past week'.
    extra = ""
    if sort == "latest":
        extra = "&age=1d" # Defaulting latest to past day.
    elif date_from or date_until:
        # Karena Yahoo tidak punya parameter URL 'custom date' yang standar, 
        # kita coba menyuntikkannya ke dalam string pencarian (query) sebagai rentang waktu
        # sebagai usaha terbaik (best-effort fallback).
        start_str = date_from.strftime("%Y-%m-%d") if date_from else ""
        end_str = date_until.strftime("%Y-%m-%d") if date_until else ""
        if start_str and end_str:
            params["p"] += f" {start_str}..{end_str}"
        elif start_str:
            params["p"] += f" after:{start_str}"
        elif end_str:
            params["p"] += f" before:{end_str}"

    return f"https://{subdomain}{path}?" + urlencode(params, quote_via=quote_plus) + extra


def build_yahoo_paginated_url(base_url: str, page_index: int) -> str:
    """Yahoo pages via `b=` — 11, 21, 31... (page 1 is absent or b=1)."""
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
    """Unwrap https://news.search.yahoo.com/.../RU=https%3a%2f%2f.../RK=2/... into the real target URL.

    Returns the original URL untouched when it is not a Yahoo redirect.
    """
    if "RU=" not in url:
        return url

    try:
        # Yahoo tracking URLs have path segments like /RU=encoded_url/RK=2
        # Use (?:/|$) to match either a slash or the end of the string
        match = re.search(r'/RU=([^/]+)(?:/|$)', url)
        if match:
            encoded_target = match.group(1)
            return unquote(encoded_target)
    except Exception:
        pass
    return ""


def extract_yahoo_links(html_content: str) -> set:
    """Extract organic result links from a Yahoo News search page."""
    links = set()
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        for selector in YAHOO_LINK_SELECTORS:
            for a in soup.select(selector):
                href = a.get("href", "")
                decoded = decode_yahoo_redirect(href)
                if is_valid_result_url(decoded, YAHOO_BAD_NETLOC):
                    links.add(decoded)

    except Exception as e:
        print(f"  Error parsing HTML: {e}")

    return links
