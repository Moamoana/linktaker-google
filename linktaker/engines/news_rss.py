import base64
import re
import time
from urllib.parse import urlparse, parse_qs, urlencode

import curl_cffi.requests as requests

from .. import geo
from ..config import RSS_DECODE_DELAY
from ..deps import FEEDPARSER_AVAILABLE, feedparser
from ..url_utils import is_valid_result_url


def decode_google_news_url(source_url: str) -> str:
    """
    Decode a Google News redirect URL to the actual article URL.
    Google News RSS uses base64-encoded redirect URLs.
    """
    try:
        # Extract the encoded part from Google News URLs
        # Format: https://news.google.com/rss/articles/CBMi...
        p = urlparse(source_url)
        path = p.path

        # Handle /rss/articles/<encoded> format
        match = re.search(r'/articles/([A-Za-z0-9_-]+)', path)
        if not match:
            # Not a Google News redirect, return as-is
            return source_url

        encoded = match.group(1)

        # Add padding if needed
        padding = 4 - len(encoded) % 4
        if padding != 4:
            encoded += "=" * padding

        # Try base64 decode
        try:
            decoded = base64.urlsafe_b64decode(encoded)
            # The decoded bytes contain the URL, often prefixed with some bytes
            # Try to find a URL pattern in the decoded data
            decoded_str = decoded.decode("utf-8", errors="ignore")
            url_match = re.search(r'https?://[^\s"\'<>]+', decoded_str)
            if url_match:
                return url_match.group(0)
        except:
            pass

        # Fallback: follow the redirect with curl_cffi
        try:
            resp = requests.get(
                source_url,
                impersonate="chrome",
                timeout=10,
                allow_redirects=True,
                verify=False,
            )
            final_url = str(resp.url)
            if final_url != source_url and "news.google.com" not in final_url:
                return final_url
        except:
            pass

        return source_url
    except:
        return source_url


def build_google_news_rss_url(search_url: str) -> str:
    """Convert a Google search URL to a Google News RSS feed URL."""
    p = urlparse(search_url)
    q = parse_qs(p.query, keep_blank_values=True)

    query = q.get("q", [""])[0]
    if not query:
        return None

    # Check if this is a news search (tbm=nws)
    tbm = q.get("tbm", [""])[0]
    if tbm != "nws":
        return None

    # Build RSS URL
    # tbs=qdr:w means past week, etc.
    tbs = q.get("tbs", [""])[0]

    # The feed picks its edition from hl/gl/ceid. --geo already wrote gl into the
    # search URL, so read it back rather than pinning Indonesia the way this did
    # before --geo existed; without it the Indonesian edition stays the default.
    # A hand-written url.txt can carry any gl at all, so an unreadable one falls
    # back rather than taking the run down over a feed that is optional anyway.
    edition = geo.Geo(code="id", name="Indonesia", language="id")
    country = q.get("gl", [""])[0]
    if country:
        try:
            edition = geo.resolve(country)
        except ValueError:
            pass

    params = {"q": query, "hl": edition.language, "gl": edition.upper,
              "ceid": edition.ceid}

    # Map time filter
    if "qdr:h" in tbs:
        params["when"] = "1h"
    elif "qdr:d" in tbs:
        params["when"] = "1d"
    elif "qdr:w" in tbs:
        params["when"] = "7d"
    elif "qdr:m" in tbs:
        params["when"] = "30d"
    elif "qdr:y" in tbs:
        params["when"] = "1y"

    rss_url = "https://news.google.com/rss/search?" + urlencode(params)
    return rss_url


def fetch_google_news_rss(search_url: str) -> set:
    """
    Fetch links from Google News RSS feed.
    No CAPTCHA, but decoded URLs need rate limiting.
    """
    if not FEEDPARSER_AVAILABLE:
        return set()

    rss_url = build_google_news_rss_url(search_url)
    if not rss_url:
        return set()

    print(f"  Trying Google News RSS: {rss_url}")

    try:
        # Fetch RSS feed with curl_cffi to avoid blocks
        resp = requests.get(
            rss_url,
            impersonate="chrome",
            timeout=15,
            verify=False,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
    except Exception as e:
        print(f"  RSS fetch failed: {e}")
        return set()

    if not feed.entries:
        print(f"  RSS feed returned 0 entries")
        return set()

    links = set()
    print(f"  RSS returned {len(feed.entries)} entries, decoding URLs...")

    for i, entry in enumerate(feed.entries):
        raw_link = entry.get("link", "")
        if not raw_link:
            continue

        # Decode Google News redirect URL
        actual_url = decode_google_news_url(raw_link)

        if actual_url and is_valid_result_url(actual_url):
            links.add(actual_url)

        # Rate limit decoding to avoid getting blocked
        if RSS_DECODE_DELAY > 0 and i < len(feed.entries) - 1:
            time.sleep(RSS_DECODE_DELAY)

    print(f"  RSS decoded {len(links)} valid links")
    return links
