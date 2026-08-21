import datetime
from urllib.parse import urlencode, quote_plus, unquote, urlparse
from .url_utils import is_valid_result_url

def build_yahoo_search_url(keyword: str, date_from: str = None, date_until: str = None, sort_mode: str = "relevance") -> str:
    """Build a Yahoo search URL from a keyword and an optional date filter."""
    search_url = f"https://news.search.yahoo.com/search?p={quote_plus(keyword.strip())}"
    
    if sort_mode == "latest":
        search_url += "&fr2=time"
        
    if date_from:
        # Yahoo does not support exact date ranges, so we calculate age from today.
        try:
            d_from = datetime.datetime.strptime(date_from, "%Y-%m-%d")
            days_diff = max(1, (datetime.datetime.now() - d_from).days)
            search_url += f"&age={days_diff}d"
        except Exception:
            search_url += "&age=1mo"
    elif sort_mode == "latest":
        search_url += "&age=1d"
        
    return search_url

def decode_yahoo_url(source_url: str) -> str:
    """Extract actual article URL from Yahoo tracking URL."""
    try:
        if "RU=" in source_url:
            parts = source_url.split("RU=")
            if len(parts) > 1:
                # The encoded URL is until the next slash /RK= or end of string
                encoded = parts[1].split("/")[0]
                decoded = unquote(encoded)
                if is_valid_result_url(decoded) and "search.yahoo.com" not in urlparse(decoded).netloc:
                    return decoded
    except Exception:
        pass
        
    # Jika tidak ada pola tracking RU= (bukan hasil pencarian utama), abaikan
    return ""
