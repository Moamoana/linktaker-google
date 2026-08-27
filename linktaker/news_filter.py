"""Keep the output file to news articles only.

Google's news tab hands back portals it has already classified as news sources,
so its links come out mostly clean. Bing and Yahoo do not: they return whatever
matches the keyword -- dictionaries, timezone converters, booking engines,
corporate landing pages, government service portals -- and all of it used to
land in the output file.

Every extracted link passes through `is_news_url` before it can be written out.
Three levels, picked with `--news-filter`:

  off      no gate at all (the behaviour before this module existed)
  smart    drop known non-news hosts and anything not shaped like an article;
           an unrecognised host still gets through, so a newly launched portal
           is not silently lost  (default)
  strict   only hosts listed in news_domains.txt, and still article-shaped

`smart` is the default because the whole reason `--mode web` exists is to reach
portals the engine has not classified as news yet -- an allowlist-only gate
would throw those away. Use `strict` when the clip list must be clean above all,
then grow news_domains.txt from the rejection report each run prints.
"""

import re
from collections import Counter
from urllib.parse import urlparse

# Two-label public suffixes common to this crawler's beat, so that
# `surabaya.tribunnews.com` and `harian.fajar.co.id` collapse onto the
# registrable domain their allowlist entry is written as.
MULTI_PART_SUFFIXES = frozenset({
    "co.id", "go.id", "or.id", "web.id", "my.id", "ac.id", "sch.id", "net.id",
    "mil.id", "desa.id", "ponpes.id", "biz.id",
    "com.my", "net.my", "org.my", "gov.my", "edu.my",
    "com.sg", "edu.sg", "gov.sg", "com.bn",
    "co.uk", "org.uk", "gov.uk", "ac.uk",
    "com.au", "gov.au", "edu.au", "net.au",
    "co.kr", "or.kr", "co.jp", "ne.jp", "or.jp",
    "com.pk", "com.bd", "com.np", "com.lk",
    "co.th", "in.th", "com.ph", "com.vn", "com.hk", "com.tw", "com.cn",
    "com.tr", "co.za", "com.br", "com.mx", "co.nz", "com.ar",
})

# Hosts that answer news keywords but never publish news.
NON_NEWS_DOMAINS = frozenset({
    # Encyclopedias, dictionaries, study material
    "wikipedia.org", "wikimedia.org", "wiktionary.org", "wikiwand.com",
    "wikisource.org", "wikivoyage.org", "dbpedia.org", "britannica.com",
    "merriam-webster.com", "dictionary.com", "thefreedictionary.com",
    "collinsdictionary.com", "vocabulary.com", "oup.com", "sinonim.com",
    "artikata.com", "kbbi.web.id", "persamaankata.com", "lektur.id",
    "scribd.com", "academia.edu", "researchgate.net", "jstor.org", "ssrn.com",
    "coursehero.com", "studocu.com", "quizlet.com", "slideshare.net",
    "brainly.co.id", "ruangguru.com", "zenius.net", "gramedia.com",
    # Clocks, calendars, calculators, maps, weather
    "worldtimebuddy.com", "timebie.com", "24timezones.com", "time.is",
    "timeanddate.com", "greenwichmeantime.com", "zeitverschiebung.net",
    "islamicfinder.org", "jadwalsholat.org", "calculator.net",
    "unitconverters.net", "distancesto.com", "latlong.net", "mapcarta.com",
    "wikimapia.org", "google.com", "weather.com", "accuweather.com",
    # Travel, ticketing, hotels
    "traveloka.com", "tiket.com", "tiketkeretaapi.com", "redbus.id",
    "pegipegi.com", "nusatrip.com", "pergimulu.com", "agoda.com",
    "booking.com", "trip.com", "airbnb.com", "expedia.com", "trivago.co.id",
    "klook.com", "tripadvisor.com", "tripadvisor.co.id", "skyscanner.co.id",
    "kayak.com", "12go.asia", "easybook.com", "busonlineticket.com",
    # Marketplaces and classifieds
    "tokopedia.com", "shopee.co.id", "bukalapak.com", "lazada.co.id",
    "lazada.com.my", "blibli.com", "qoo10.co.id", "zalora.co.id", "jd.id",
    "olx.co.id", "carousell.com", "mudah.my", "lelong.com.my", "amazon.com",
    "ebay.com", "alibaba.com", "aliexpress.com", "etsy.com", "indotrading.com",
    "ralali.com", "monotaro.id", "bhinneka.com", "rumah123.com", "99.co",
    "otodom.pl", "mobil123.com", "carmudi.co.id", "oto.com", "otospector.co.id",
    # Job boards and business directories
    "jobstreet.co.id", "jobstreet.com.my", "indeed.com", "glassdoor.com",
    "kalibrr.com", "yellowpages.co.id", "yelp.com", "foursquare.com",
    "zomato.com", "opentable.com", "crunchbase.com", "zoominfo.com",
    # Reference data and market tools (as opposed to market reporting)
    "stockanalysis.com", "i3investor.com", "klsescreener.com", "imoney.my",
    "ringgitplus.com", "wise.com", "xe.com", "exchange-rates.org",
    "tradingview.com", "morningstar.com", "macrotrends.net",
    # Legal and regulatory databases
    "lexlege.pl", "hukumonline.com", "peraturan.go.id", "jdih.go.id",
    "legalitas.org", "lawinsider.com",
    # User-generated platforms and blog hosts
    "kompasiana.com", "blogspot.com", "blogger.com", "wordpress.com",
    "wixsite.com", "weebly.com", "sites.google.com", "kaskus.co.id",
    "steemit.com", "hashnode.dev",
    # Media hosting rather than reporting
    "dailymotion.com", "soundcloud.com", "spotify.com", "netflix.com",
    "issuu.com", "flickr.com", "imgur.com", "giphy.com",
    # Content farms and SEO filler caught in earlier Bing/Yahoo runs. This is a
    # long tail by nature — it is why `strict` exists — but the repeat offenders
    # are worth naming.
    "idezia.com", "nurcholis.com", "zaipad.com", "fabelia.com",
    "dominasidigital.com", "jasapenulisartikel.my.id", "proxycove.com",
    "productnation.co", "bizhankook.com", "embassies.net",
    # Aggregators and syndicators: real headlines, but the copy rather than the
    # source. A clip list wants the publisher's own URL, not this mirror.
    "msn.com", "news.google.com", "headtopics.com", "newsbreak.com",
    "biztoc.com", "flipboard.com", "smartnews.com", "inkl.com", "newsnow.co.uk",
})

# Institutions publish press releases, not journalism. Their sites also serve a
# lot of forms and service portals, which is most of what leaked in before.
INSTITUTIONAL_SUFFIXES = (
    ".go.id", ".mil.id", ".ac.id", ".sch.id", ".desa.id", ".ponpes.id",
    ".gov.my", ".edu.my", ".gov.sg", ".edu.sg", ".gov.uk", ".ac.uk",
    ".gov.au", ".edu.au", ".gov", ".mil", ".edu", ".int",
)

# Path segments that mark a listing, a utility page, or plumbing -- never a story.
NON_ARTICLE_SEGMENTS = frozenset({
    "tag", "tags", "label", "labels", "category", "categories", "kategori",
    "topic", "topics", "topik", "kanal", "rubrik", "indeks", "index",
    "archive", "archives", "arsip", "search", "cari", "pencarian",
    "page", "halaman", "author", "authors", "penulis", "reporter", "redaksi",
    "about", "about-us", "tentang", "tentang-kami", "contact", "contact-us",
    "kontak", "privacy", "privacy-policy", "kebijakan-privasi", "disclaimer",
    "pedoman-media-siber", "terms", "syarat-ketentuan", "karir", "careers",
    "login", "signin", "register", "signup", "daftar", "subscribe", "berlangganan",
    "feed", "rss", "sitemap", "amp", "print", "cetak", "comments", "komentar",
    "cdn-cgi", "wp-content", "wp-admin", "wp-json", "wp-includes",
    "assets", "static", "uploads", "images", "img", "thumb",
    "cart", "checkout", "keranjang", "account", "akun", "profile", "profil",
    "faq", "help", "bantuan",
})

# Anything served as a file rather than a page.
NON_ARTICLE_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".apk", ".exe", ".dmg",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".webm", ".m3u8",
    ".xml", ".json", ".rss", ".atom", ".txt", ".css", ".js",
)

# Directory indexes, whatever the CMS calls them.
INDEX_FILENAMES = ("index.html", "index.htm", "index.php", "index.asp", "index.jsp")

# An article path almost always carries one of these: a publication date, a CMS
# id, or a headline slug.
DATE_IN_PATH = re.compile(r"/(?:19|20)\d{2}/\d{1,2}(?:/\d{1,2})?(?:/|$)")
CMS_ID = re.compile(r"\d{5,}")
# Old WordPress installs publish at the root as `?p=112078`, so the id lives in
# the query rather than the path.
QUERY_ID = re.compile(r"(?:^|&)(?:p|id|page_id|post|artikel|news_id)=\d{3,}(?:&|$)")
MIN_SLUG_WORDS = 3          # "kpk-tangkap-bupati" is a headline; "kuala-lumpur" is not


def registrable_domain(host: str) -> str:
    """`surabaya.tribunnews.com` -> `tribunnews.com`, `harian.fajar.co.id` -> `fajar.co.id`."""
    host = (host or "").lower().split(":")[0].rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if ".".join(parts[-2:]) in MULTI_PART_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _host_matches(host: str, domains) -> bool:
    """True when `host` is one of `domains` or sits underneath one of them."""
    host = (host or "").lower().split(":")[0].rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return False
    if host in domains or registrable_domain(host) in domains:
        return True
    return any(host.endswith("." + d) for d in domains)


def _slug_words(segment: str) -> int:
    """How many word-ish tokens a hyphenated path segment carries."""
    return sum(1 for token in segment.split("-") if len(token) > 1 and not token.isdigit())


def looks_like_article(url: str) -> bool:
    """True when the path is shaped like a story rather than a listing or a tool."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    lowered = parsed.path.lower()
    query = parsed.query.lower()

    if lowered in ("", "/"):
        # Not a homepage when the story id rides in the query, the way old
        # WordPress permalinks do: `https://mediata.id/?p=112078`.
        return bool(QUERY_ID.search(query))
    if lowered.endswith(NON_ARTICLE_EXTENSIONS) or lowered.endswith(INDEX_FILENAMES):
        return False

    segments = [s for s in lowered.split("/") if s]
    has_id = bool(CMS_ID.search(lowered)) or bool(QUERY_ID.search(query))

    if any(s in NON_ARTICLE_SEGMENTS for s in segments):
        # A listing word can also be a section prefix on a real article —
        # infopublik.id files stories under `/kategori/<section>/<id>/<slug>`.
        # The story id is what tells the two apart: a tag or archive page never
        # carries one, an article almost always does.
        if not has_id:
            return False

    if has_id or DATE_IN_PATH.search(lowered):
        return True
    return any(_slug_words(s) >= MIN_SLUG_WORDS for s in segments)


def is_news_url(url: str, mode: str = "smart", allowlist=frozenset()) -> bool:
    """The gate. `mode` is one of off / smart / strict; see the module docstring."""
    if mode == "off":
        return True

    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    if not host:
        return False

    # An allowlisted host is a known publisher: skip the negative rules, but
    # still require an article path so its homepage and tag pages stay out.
    if _host_matches(host, allowlist):
        return looks_like_article(url)

    if mode == "strict":
        return False

    if _host_matches(host, NON_NEWS_DOMAINS):
        return False

    bare = host[4:] if host.startswith("www.") else host
    if bare.endswith(INSTITUTIONAL_SUFFIXES):
        return False

    return looks_like_article(url)


class RejectionLog:
    """Counts what the gate dropped, so a run can report which hosts to review."""

    def __init__(self):
        self.by_domain = Counter()

    def record(self, url: str):
        try:
            self.by_domain[registrable_domain(urlparse(url).netloc)] += 1
        except ValueError:
            self.by_domain["<unparsable>"] += 1

    @property
    def total(self) -> int:
        return sum(self.by_domain.values())

    def top(self, limit: int = 15):
        return self.by_domain.most_common(limit)


# --- Run-wide state -------------------------------------------------------
# `is_valid_result_url` is called from inside each engine's extractor, far from
# the CLI, so the chosen mode lives here and `configure()` sets it once at
# startup. The default matches config.NEWS_FILTER, which keeps direct library
# use and the offline tests filtering the way a plain run does.

_mode = "smart"
_allowlist = frozenset()
rejected = RejectionLog()


def configure(mode: str, allowlist=frozenset()):
    """Set the gate for this run and reset the rejection counters."""
    global _mode, _allowlist, rejected
    _mode = mode
    _allowlist = frozenset(allowlist)
    rejected = RejectionLog()


def accepts(url: str) -> bool:
    """Apply the configured gate, recording anything it turns away."""
    if is_news_url(url, _mode, _allowlist):
        return True
    if _mode != "off":
        rejected.record(url)
    return False
