"""Keyword + date input — the simple alternative to hand-crafting url.txt."""

from urllib.parse import urlencode, quote_plus

# Relative Google time filters (same codes used by tbs=qdr:*)
RELATIVE_DATE_CODES = {"h": "qdr:h", "d": "qdr:d", "w": "qdr:w", "m": "qdr:m", "y": "qdr:y"}


def parse_date_filter(date_filter: str):
    """
    Convert a date filter string into (tbs_value, query_suffix).

    Supported formats:
      - "" / None                    -> no filter
      - "h" / "d" / "w" / "m" / "y"  -> relative filter (past hour/day/week/month/year)
      - "YYYY-MM-DD..YYYY-MM-DD"     -> custom date range (after:/before: search operators)
      - "YYYY-MM-DD.."               -> only "after" date
      - "..YYYY-MM-DD"               -> only "before" date
    """
    date_filter = (date_filter or "").strip()
    if not date_filter:
        return None, ""

    code = date_filter.lower()
    if code in RELATIVE_DATE_CODES:
        return RELATIVE_DATE_CODES[code], ""

    if ".." in date_filter:
        start, _, end = date_filter.partition("..")
        start, end = start.strip(), end.strip()
        parts = []
        if start:
            parts.append(f"after:{start}")
        if end:
            parts.append(f"before:{end}")
        return None, (" " + " ".join(parts) if parts else "")

    print(f"  Unrecognized date filter '{date_filter}', ignoring.")
    return None, ""


def build_search_url(keyword: str, date_from: str = "", date_until: str = "", sort: str = "", mode: str = "nws") -> str:
    """Build a Google search URL from a keyword and optional filters (Issue #2)."""
    
    parts = []
    if date_from:
        parts.append(f"after:{date_from}")
    if date_until:
        parts.append(f"before:{date_until}")
        
    query_suffix = " " + " ".join(parts) if parts else ""
    query = keyword.strip() + query_suffix

    params = {"q": query}
    
    # Menangani Issue #3 (Tab Semua vs Berita)
    if mode == "nws":
        params["tbm"] = "nws"
        
    # Menangani --sort latest (hanya berlaku jika mode news)
    if sort == "latest":
        params["tbs"] = "sbd:1"

    return "https://www.google.com/search?" + urlencode(params, quote_via=quote_plus)


def read_keywords(path):
    """
    Read keyword search requests from file — the simple alternative to url.txt.
    Each non-comment, non-empty line:

        keyword | date_filter | mode

    Only `keyword` is required. Examples:

        startup indonesia
        ai regulation | w
        breaking news jakarta | 2024-01-01..2024-06-30 | web

    Returns a list of (keyword, date_filter, mode) tuples.
    """
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = [p.strip() for p in line.split("|")]
            keyword = parts[0]
            if not keyword:
                continue

            date_filter = parts[1] if len(parts) > 1 else ""
            mode = parts[2].lower() if len(parts) > 2 and parts[2] else "nws"
            if mode not in ("nws", "web"):
                print(f"  Unknown mode '{mode}' for keyword '{keyword}', defaulting to 'nws'")
                mode = "nws"

            entries.append((keyword, date_filter, mode))
    return entries
