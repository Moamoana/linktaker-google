"""Search engine adapters.

Everything that differs between engines lives in one module each — how a keyword
turns into a search URL, how pages are walked, which selectors mark results, a
CAPTCHA, and the "next page" control. `fetchers.py` and `browser.py` stay engine
agnostic: they only read fields off the `Engine` objects collected here.

Adding an engine: write a module next to `bing.py` that ends with an `Engine(...)`
object, then add it to the tuple below.
"""

from .base import Engine, MODE_LABELS, SEARCH_MODES, expand_mode, no_notes
from .bing import BING
from .google import GOOGLE
from .yahoo import YAHOO

ENGINES = {engine.name: engine for engine in (GOOGLE, BING, YAHOO)}


def get_engine(name: str) -> Engine:
    """Look up an engine by CLI name."""
    return ENGINES[name]


__all__ = ["BING", "ENGINES", "Engine", "GOOGLE", "MODE_LABELS", "SEARCH_MODES",
           "YAHOO", "expand_mode", "get_engine", "no_notes"]
