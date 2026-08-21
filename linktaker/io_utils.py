import json
import os

from .config import AUTH_FILE


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
