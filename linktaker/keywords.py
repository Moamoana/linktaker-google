"""Keyword input + Google search URL builder.

The input file holds one keyword per line — dates, sorting and paging all
come from the command line, so the file stays as simple as possible.
"""

from datetime import date, datetime
from urllib.parse import urlencode, quote_plus

DATE_FORMAT = "%Y-%m-%d"


def parse_date(value: str, flag: str) -> date:
    """Parse a YYYY-MM-DD CLI date. Raises ValueError with a readable message."""
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date()
    except ValueError:
        raise ValueError(f"{flag} must be in YYYY-MM-DD format (got '{value}')")


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


def build_search_url(keyword: str, date_from: date = None, date_until: date = None,
                     sort: str = "relevance", mode: str = "nws") -> str:
    """Build a Google search URL for one keyword.

    mode: "nws" for Google News results, "web" for regular web search.
    """
    params = {"q": keyword.strip()}
    if mode == "nws":
        params["tbm"] = "nws"

    tbs = build_tbs(date_from, date_until, sort)
    if tbs:
        params["tbs"] = tbs

    return "https://www.google.com/search?" + urlencode(params, quote_via=quote_plus)


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
