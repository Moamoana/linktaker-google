import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup

from .config import SOCIAL_MEDIA_DOMAINS


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


def is_valid_result_url(href: str) -> bool:
    """Validate if URL is a real search result and not social media."""
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

    bad = ("google.com", "google.co.", "gstatic.com", "googleusercontent.com")
    if any(b in p.netloc for b in bad):
        return False

    # --- Extreme News Filter (Issue #3) ---
    # Hanya mengambil murni artikel berita di tab "Semua" secara ekstrim.
    path = p.path.strip("/")
    if not path:  # Buang homepage (misal: karir.pelni.co.id)
        return False
        
    path_lower = p.path.lower()
    
    # Kriteria Emas Artikel Berita:
    # 1. Judul panjang (biasanya >3 tanda hubung di path URL)
    is_long_slug = path.count("-") >= 3
    
    # 2. Path mengandung direktori khas portal berita
    news_keywords = ["/berita", "/news", "/read", "/article", "/detail", "/2023", "/2024", "/2025", "/2026"]
    has_news_keyword = any(kw in path_lower for kw in news_keywords)
    
    # 3. Negative Filter (Anti-Media): Tolak mentah-mentah jika ini adalah halaman Video, Foto, atau Podcast
    media_keywords = ["video", "foto", "gallery", "galeri", "podcast"]
    is_media_page = any(kw in path_lower for kw in media_keywords)
    
    # Jika terdeteksi sebagai halaman media, langsung buang!
    if is_media_page:
        return False
    
    # Jika tidak memiliki slug panjang DAN tidak memiliki kata kunci berita, BUANG!
    if not (is_long_slug or has_news_keyword):
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
            # Fallback universal untuk mengatasi perombakan kelas CSS Google (Issue 3)
            "a[href]",
        ]

        for selector in selectors:
            for a in soup.select(selector):
                href = a.get("href", "")
                if is_valid_result_url(href):
                    links.add(href)

    except Exception as e:
        print(f"  Error parsing HTML: {e}")

    return links
