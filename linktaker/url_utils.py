"""URL helpers shared by every engine: AMP cleanup, social filter, validation."""

import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from .config import SOCIAL_MEDIA_DOMAINS
from .news_filter import accepts as accepts_as_news


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


def dedup_key(url: str) -> str:
    """The form of a URL used for comparing, never for sending or storing.

    Two addresses that lead to the same story are written differently by
    different search engines: http vs https, with or without `www.`, with or
    without a trailing slash, sometimes with a #fragment attached. Callers keep
    the original URL and compare these keys.
    """
    try:
        p = urlparse(url.strip())
        host = p.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = p.path.rstrip("/") or "/"
        return urlunparse(("", host, path, "", p.query, ""))
    except ValueError:
        return url.strip()


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


def is_valid_result_url(href: str, bad_netloc=()) -> bool:
    """Validate if URL is a real search result, not social media, and a news story.

    bad_netloc: host fragments belonging to the search engine itself, so its own
    internal links and ad redirects never reach the output file.

    The news gate runs last so that the cheap structural checks reject first,
    and so its rejection report only counts links that were otherwise usable.
    See `news_filter` for what it drops and how `--news-filter` tunes it.
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

    return accepts_as_news(href)
