import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup

from .config import SOCIAL_MEDIA_DOMAINS

# Netloc fragments that mean "this is the search engine itself, not a result".
GOOGLE_BAD_NETLOC = ("google.com", "google.co.", "gstatic.com", "googleusercontent.com")


def strip_amp(url: str) -> str:
    """Remove AMP artifacts from a URL."""
    try:
        p = urlparse(url)

        # Strip amp. subdomain (e.g. amp.example.com -> example.com)
        netloc = p.netloc
        if netloc.startswith("amp."):
            netloc = netloc[4:]

        # Strip /amp/, /amp from path
        path = re.sub(r'/amp(/|$)', '/', p.path)
        # Remove trailing slash added by cleanup (but keep root /)
        if path != '/' and path.endswith('/'):
            path = path.rstrip('/')

        # Remove amp-related query params
        qs = parse_qs(p.query, keep_blank_values=True)
        qs.pop('amp', None)
        qs.pop('amp_js_v', None)
        qs.pop('usqp', None)
        qs.pop('outputType', None)
        new_query = urlencode(
            {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in qs.items()},
            doseq=True,
        )

        return urlunparse((p.scheme, netloc, path, p.params, new_query, p.fragment))
    except:
        return url


def is_social_media(url: str) -> bool:
    """Check if URL belongs to a social media platform."""
    try:
        p = urlparse(url)
        netloc = p.netloc.lower()

        if netloc.startswith("www."):
            netloc = netloc[4:]
        if netloc in SOCIAL_MEDIA_DOMAINS:
            return True
        for domain in SOCIAL_MEDIA_DOMAINS:
            if netloc.endswith("." + domain) or netloc == domain:
                return True

        return False
    except:
        return False


def is_valid_result_url(href: str, bad_netloc=GOOGLE_BAD_NETLOC) -> bool:
    """Validate if URL is a real search result and not social media.

    bad_netloc: host fragments belonging to the search engine itself, so its own
    internal links and ad redirects never reach the output file.
    """
    if not href:
        return False

    if "/url?q=" in href:
        try:
            qs = parse_qs(urlparse(href).query)
            if "q" in qs:
                href = qs["q"][0]
        except:
            return False

    if is_social_media(href):
        return False

    p = urlparse(href)
    if p.scheme not in ("http", "https"):
        return False
    if not p.netloc:
        return False

    if any(b in p.netloc for b in bad_netloc):
        return False

    return True


def build_paginated_url(base_url: str, page_index: int) -> str:
    """Build Google search URL with pagination."""
    start = page_index * 10
    p = urlparse(base_url)
    q = parse_qs(p.query, keep_blank_values=True)
    q["start"] = [str(start)]
    new_query = urlencode({k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in q.items()}, doseq=True)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, p.fragment))


def extract_google_links(html_content: str) -> set:
    """Extract all result links from Google HTML."""
    links = set()
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        selectors = [
            "div.g a[href]",
            "div.SoaBEf a[href]",
            "div.yuRUbf a[href]",
            "div.MjjYud a[href]",
            "a[jsname='UWckNb']",
        ]

        for selector in selectors:
            for a in soup.select(selector):
                href = a.get("href", "")
                if is_valid_result_url(href):
                    links.add(href)

    except Exception as e:
        print(f"  Error parsing HTML: {e}")

    return links
