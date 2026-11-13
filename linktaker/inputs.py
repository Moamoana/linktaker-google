"""Reading what the user hands the crawler: keywords, URLs, proxies, credentials.

Engine-neutral — turning a keyword into a search URL is each engine's job.
"""

import json
import os
from datetime import date, datetime

from .config import AUTH_FILE, NEWS_DOMAINS_FILE

DATE_FORMAT = "%Y-%m-%d"


def parse_date(value: str, flag: str) -> date:
    """Parse a YYYY-MM-DD CLI date. Raises ValueError with a readable message."""
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date()
    except ValueError:
        raise ValueError(f"{flag} must be in YYYY-MM-DD format (got '{value}')")


def read_keywords(path):
    """
    Read keywords from file — one keyword per line.
    Blank lines and lines starting with `#` are ignored.

        pelni
        startup indonesia
        ai regulation

    Legacy lines using the old `keyword | date | mode` format still work:
    only the keyword part is used, the rest now comes from CLI flags.
    """
    keywords = []
    seen = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Legacy "keyword | date | mode" lines: keep the keyword only.
            keyword = line.split("|")[0].strip()
            if not keyword or keyword.lower() in seen:
                continue

            seen.add(keyword.lower())
            keywords.append(keyword)
    return keywords


def read_urls(path):
    """Read search URLs from file."""
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]


def read_proxies(path):
    """Read proxies from file."""
    if not os.path.exists(path):
        print(f"{path} not found. Proceeding without proxy rotation.")
        return []

    proxies = [ln.strip() for ln in open(path, "r", encoding="utf-8")
               if ln.strip() and not ln.strip().startswith("#")]
    print(f"Loaded {len(proxies)} proxy/proxies")
    return proxies


def read_news_domains(path=NEWS_DOMAINS_FILE):
    """Read the publisher allowlist — one registrable domain per line.

    Entries are normalised so a pasted URL or a leading `www.`/`*.` still works:

        tribunnews.com
        www.detik.com          -> detik.com
        https://tempo.co/      -> tempo.co

    A missing file is not an error in `smart` mode, which works without one;
    `--news-filter strict` checks for it separately and refuses to run blind.
    """
    if not os.path.exists(path):
        return set()

    domains = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            entry = line.strip().lower()
            if not entry or entry.startswith("#"):
                continue

            entry = entry.split("//")[-1]          # drop a pasted scheme
            entry = entry.split("/")[0]            # drop a pasted path
            entry = entry.lstrip("*.")
            if entry.startswith("www."):
                entry = entry[4:]
            if entry:
                domains.add(entry)
    return domains


def read_auth():
    """Read authentication credentials from JSON file."""
    if not os.path.exists(AUTH_FILE):
        return None

    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            auth = json.load(f)
        print(f"Loaded authentication for user: {auth.get('username')}")
        return auth
    except Exception as e:
        print(f"Error reading {AUTH_FILE}: {e}")
        return None
