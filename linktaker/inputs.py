"""Reading what the user hands the crawler: keywords, URLs, proxies, credentials.

Engine-neutral — turning a keyword into a search URL is each engine's job.
"""

import calendar
import json
import os
import re
from datetime import date, datetime, timedelta

from .config import AUTH_FILE, DATA_DIR, NEWS_DOMAINS_FILE

DATE_FORMAT = "%Y-%m-%d"

# Relative dates: "7d", "2w", "m", "1y". A bare unit means one of it, so "w" is
# last week. Written this way a scheduled run keeps asking for the same window
# relative to the day it runs, instead of drifting further behind a fixed date.
RELATIVE_RE = re.compile(r"^-?(\d*)\s*([dwmy])$")

TODAY_WORDS = {"today", "now", "0"}
YESTERDAY_WORDS = {"yesterday", "kemarin"}

RELATIVE_HELP = ("YYYY-MM-DD, or relative to today: today, yesterday, "
                 "7d (days), 2w (weeks), 3m (months), 1y (years) — "
                 "a bare unit means one, so 'w' is a week ago")


def resolve_data_path(path):
    """Path apa adanya, kecuali file lamanya masih tergeletak di root project.

    Semua input pindah ke `data/` saat struktur project dirapikan. Mesin yang
    sudah jalan masih memegang salinan lama di root, dan sebuah run terjadwal
    jam tiga pagi tidak boleh mati hanya karena file belum dipindahkan —
    dipakai yang lama, dengan pengingat sekali per run.
    """
    if os.path.exists(path):
        return path
    legacy = os.path.basename(path)
    if os.path.dirname(path) == DATA_DIR and os.path.exists(legacy):
        print("[!] %s masih di root project — pindahkan ke %s" % (legacy, path))
        return legacy
    return path


def shift_months(anchor: date, months: int) -> date:
    """`anchor` moved back by whole months, clamped to the target month's length.

    Subtracting a month from the 31st has no exact answer, so the day is pulled
    back to the last one that exists: 31 March minus one month is 28 February.
    """
    total = anchor.year * 12 + (anchor.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def parse_date(value: str, flag: str, today: date = None) -> date:
    """Parse a CLI date — absolute YYYY-MM-DD or relative to today.

    Resolved fresh on every run, so a crawler left on a schedule walks its
    window forward with the calendar rather than re-crawling one fixed range.
    """
    anchor = today or date.today()
    raw = value.strip().lower()

    if raw in TODAY_WORDS:
        return anchor
    if raw in YESTERDAY_WORDS:
        return anchor - timedelta(days=1)

    match = RELATIVE_RE.match(raw)
    if match:
        count = int(match.group(1)) if match.group(1) else 1
        unit = match.group(2)
        if unit == "d":
            return anchor - timedelta(days=count)
        if unit == "w":
            return anchor - timedelta(weeks=count)
        if unit == "m":
            return shift_months(anchor, count)
        return shift_months(anchor, count * 12)

    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date()
    except ValueError:
        raise ValueError(f"{flag} must be {RELATIVE_HELP} (got '{value}')")


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
    path = resolve_data_path(path)
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
    path = resolve_data_path(path)
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
