"""The Engine contract shared by every search engine adapter.

Kept in its own module so each engine can import `Engine` without importing the
package that collects them.
"""

from dataclasses import dataclass
from typing import Callable


def no_notes(mode: str, sort: str, date_from=None, date_until=None) -> list:
    """Default for engines that can honour every request as asked."""
    return []


@dataclass(frozen=True)
class Engine:
    """One search engine's flavour of the shared crawl flow.

    `fetchers.py` and `browser.py` read these fields instead of hard-coding any
    single engine, so adding one means writing a module like `bing.py` and
    registering it in `__init__.py`.
    """

    name: str
    default_mode: str                 # vertical used when --mode is not given
    build_search_url: Callable        # (keyword, date_from, date_until, sort, mode) -> url
    build_paginated_url: Callable     # (search_url, page_index) -> url
    extract_links: Callable           # (html) -> set of links
    results_selector: str             # results are on screen once this matches
    captcha_selector: str             # CSS that marks a CAPTCHA / challenge page
    captcha_url_markers: tuple        # URL fragments that mean "challenge page"
    capability_notes: Callable = no_notes  # (mode, sort, date_from, date_until) -> notes
    next_selector: str = None         # click to paginate; None = navigate by URL
    captcha_text_markers: tuple = ()  # visible text that marks a challenge page


# --mode values every engine understands. "both" is not a vertical of its own:
# it crawls the All tab and the News tab and merges what they return, because a
# news tab only lists portals the engine already knows as news sources, while a
# newly launched one shows up on the All tab first.
SEARCH_MODES = ("nws", "web", "both")

MODE_LABELS = {"nws": "news tab", "web": "all tab", "both": "all tab + news tab"}


def expand_mode(mode: str) -> tuple:
    """The verticals one --mode value crawls, in the order they are crawled."""
    return ("web", "nws") if mode == "both" else (mode,)
