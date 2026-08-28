"""Offline regression check for every engine: pagination, extraction, filtering.

No network needed — a fake Playwright page feeds canned HTML to BrowserManager.

    python tests/test_engines.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import base64

from linktaker.browser import BrowserManager
from linktaker.engines import BING, GOOGLE, YAHOO, expand_mode

GOOGLE_PAGE = """
<div class="g"><a href="https://site{n}.example.com/berita/kpk-tangkap-bupati-sidoarjo">x</a></div>
<div class="g"><a href="https://site{n}.example.com/berita/korupsi-dana-desa-diusut">y</a></div>
<div class="g"><a href="https://www.facebook.com/spam">social</a></div>
<div class="g"><a href="https://support.google.com/internal">internal</a></div>
<!-- All tab without javascript: every result sits behind a /url?q= wrapper -->
<div class="Gx5Zad"><a href="/url?q=https%3A%2F%2Fportal{n}.example.com%2F2026%2F08%2F20%2Fpelni-tambah-rute&amp;sa=U">z</a></div>
<div class="Gx5Zad"><a href="/url?q=https%3A%2F%2Fwww.google.com%2Fsettings&amp;sa=U">internal</a></div>
"""


def ck(url):
    payload = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    return f"https://www.bing.com/ck/a?!&&p=abc&u=a1{payload}"


BING_PAGE = """
<li class="b_algo"><h2><a href="{w1}">x</a></h2></li>
<li class="b_algo"><h2><a href="{w2}">y</a></h2></li>
<li class="b_ad"><h2><a href="https://www.bing.com/aclick?ad=1">ad</a></h2></li>
<li class="b_algo"><h2><a href="{social}">social</a></h2></li>
"""


YAHOO_PAGE = """
<div class="algo"><div class="compTitle"><a href="{w1}">x</a></div></div>
<div class="algo"><div class="compTitle"><a href="{w2}">y</a></div></div>
<div class="ads"><div class="compTitle"><a href="https://ads.yahoo.com/click">ad</a></div></div>
<div class="algo"><div class="compTitle"><a href="{social}">s</a></div></div>
"""


def ru(url):
    from urllib.parse import quote
    return f"https://r.search.yahoo.com/_ylt=abc/RV=2/RU={quote(url, safe='')}/RK=2/RS=sig-"


class FakeElement:
    def __init__(self, page):
        self.page = page

    def click(self):
        self.page.idx += 1
        self.page.visited.append(f"click->page{self.page.idx + 1}")


class FakePage:
    def __init__(self, engine, total_pages):
        self.engine = engine
        self.total = total_pages
        self.idx = 0
        self.visited = []
        self.url = "https://start"

    # --- playwright surface used by BrowserManager ---
    def set_default_timeout(self, ms): pass

    def goto(self, url, **kw):
        self.url = url
        self.visited.append(url)
        for param in ("first=", "b="):
            if param in url:
                self.idx = (int(url.split(param)[1].split("&")[0]) - 1) // 10

    def wait_for_selector(self, sel, timeout=None):
        if self.idx >= self.total:
            raise RuntimeError("no results")

    def wait_for_load_state(self, state): pass

    def query_selector_all(self, sel):
        return [] if self.idx >= self.total else [1, 2]

    def query_selector(self, sel):
        if sel == "#pnnext":
            return FakeElement(self) if self.idx + 1 < self.total else None
        return None

    def inner_text(self, sel):
        return ""

    def content(self):
        if self.idx >= self.total:
            return ""
        if self.engine is GOOGLE:
            return GOOGLE_PAGE.format(n=self.idx)
        if self.engine is YAHOO:
            return YAHOO_PAGE.format(
                w1=ru(f"https://ysite{self.idx}.example.com/berita/kpk-tangkap-bupati"),
                w2=ru(f"https://ysite{self.idx}.example.com/berita/korupsi-dana-desa"),
                social=ru("https://instagram.com/spam"),
            )
        return BING_PAGE.format(
            w1=ck(f"https://bsite{self.idx}.example.com/berita/kpk-tangkap-bupati"),
            w2=ck(f"https://bsite{self.idx}.example.com/berita/korupsi-dana-desa"),
            social=ck("https://twitter.com/spam"),
        )

    def close(self): pass


class FakeContext:
    def __init__(self, page): self.page = page
    def new_page(self): return self.page


def run(engine, total_pages, max_pages):
    page = FakePage(engine, total_pages)
    mgr = BrowserManager()
    mgr._context = FakeContext(page)
    links = mgr.browse_and_paginate("https://start", max_pages, 2, engine)
    return links, page.visited


print("=== GOOGLE: 3 pages available, max_pages=2 ===")
links, visited = run(GOOGLE, 3, 2)
print("links:", sorted(links))
print("navigation:", visited)
assert len(links) == 6, links                      # 3 results x 2 pages
assert any(l.startswith("https://portal") for l in links)  # /url?q= wrapper unwrapped
assert not any(l.startswith("/url") for l in links)        # ...and never stored raw
assert not any("facebook" in l for l in links)     # social filtered
assert not any("google.com" in l for l in links)   # engine-internal filtered
assert visited.count("click->page2") == 1          # clicked exactly once
assert not any("click->page3" in v for v in visited)  # stopped at max_pages

print("\n=== GOOGLE: 1 page available, max_pages=5 ===")
links, visited = run(GOOGLE, 1, 5)
print("links:", sorted(links), "| nav:", visited)
assert len(links) == 3

print("\n=== BING: 4 pages available, max_pages=3 ===")
links, visited = run(BING, 4, 3)
print("links:", sorted(links))
print("navigation:", visited)
assert len(links) == 6, links                      # 2 results x 3 pages, redirects decoded
assert all(l.startswith("https://bsite") for l in links)
assert not any("bing.com" in l for l in links)     # ads + internal filtered
assert not any("twitter" in l for l in links)      # social filtered
assert "first=11" in visited[1] and "first=21" in visited[2]
assert len(visited) == 3                           # no wasted 4th navigation

print("\n=== BING: unlimited pages (max_pages=None), engine runs out after 2 ===")
links, visited = run(BING, 2, None)
print("links:", len(links), "| nav:", visited)
assert len(links) == 4

print("\n=== YAHOO: 3 pages available, max_pages=3 ===")
links, visited = run(YAHOO, 3, 3)
print("links:", sorted(links))
print("navigation:", visited)
assert len(links) == 6, links                       # tracking URLs decoded
assert all(l.startswith("https://ysite") for l in links)
assert not any("yahoo.com" in l for l in links)     # tracking wrapper + ads filtered
assert not any("instagram" in l for l in links)     # social filtered
assert "b=11" in visited[1] and "b=21" in visited[2]

print("\n=== YAHOO: date filter buckets ===")
from datetime import date
from linktaker.engines.yahoo import relative_time_filter
today = date(2026, 8, 20)
assert relative_time_filter(date(2026, 8, 20), None, today) == "d"
assert relative_time_filter(date(2026, 8, 15), None, today) == "w"
assert relative_time_filter(date(2026, 8, 8), None, today) == "m"
assert relative_time_filter(date(2019, 1, 1), None, today) is None
assert relative_time_filter(None, None, today) is None
print("  d/w/m/none buckets OK")

print("\n=== GOOGLE: search tabs (issue #3) ===")
from urllib.parse import parse_qs, urlparse
from linktaker.engines.google import build_google_search_url, unwrap_google_redirect

def params(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}

span = (date(2026, 8, 8), date(2026, 8, 16))
all_tab = params(build_google_search_url("kpk", *span, "latest", "web"))
news_tab = params(build_google_search_url("kpk", *span, "latest", "nws"))
print("  all tab :", all_tab)
print("  news tab:", news_tab)
assert "tbm" not in all_tab                          # no tbm = the "Semua" / All tab
assert news_tab["tbm"] == "nws"
# The date range and the ordering survive on both tabs.
assert all_tab["tbs"] == news_tab["tbs"] == "cdr:1,cd_min:8/8/2026,cd_max:8/16/2026,sbd:1"
assert GOOGLE.default_mode == "web"                  # All tab is what a plain run crawls
assert expand_mode("both") == ("web", "nws")         # --mode both covers each tab once
assert expand_mode("nws") == ("nws",) and expand_mode("web") == ("web",)

assert unwrap_google_redirect("/url?q=https%3A%2F%2Fx.example.com%2Fa&sa=U") == "https://x.example.com/a"
assert unwrap_google_redirect("https://x.example.com/a") == "https://x.example.com/a"
assert unwrap_google_redirect("/url?sa=t&nothing=here") == ""
print("  all/news tab URLs, default mode, and /url?q= unwrapping OK")

print("\n=== GEO: --geo resolution (issue #17) ===")
from linktaker import geo
from linktaker.engines.bing import build_bing_search_url
from linktaker.engines.yahoo import build_yahoo_search_url, regional_host

# A code, a name, the same name capitalised, and the Indonesian name all land
# on one country — that is the whole point of resolving before building a URL.
for typed in ("my", "MY", "malaysia", "Malaysia", " Malaysia "):
    assert geo.resolve(typed).code == "my", typed
assert geo.resolve("jerman").code == "de"      # Indonesian name
assert geo.resolve("uk").code == "gb"          # shorthand, not the ISO code
assert geo.resolve("timor-leste").code == "tl"  # hyphen folded to a space
assert geo.resolve("is").code == "is"          # a code that reads like a word
assert str(geo.resolve("my")) == "Malaysia (my)"

# An unusable --geo has to be rejected, and a near miss has to say what was meant.
for bad in ("", "zz", "narnia"):
    try:
        geo.resolve(bad)
        raise AssertionError(f"{bad!r} should not resolve")
    except ValueError:
        pass
assert "Malaysia" in geo.suggest("malaysa")
try:
    geo.resolve("malaysa")
except ValueError as e:
    assert "Did you mean" in str(e) and "Malaysia" in str(e)

# Chinese carries its own region tag, so the market/edition tags must not
# double it up into zh-CN-CN.
assert geo.resolve("cn").market == "zh-CN" and geo.resolve("cn").ceid == "CN:zh-CN"
assert geo.resolve("my").market == "ms-MY" and geo.resolve("my").ceid == "MY:ms"
print("  codes, names, aliases, suggestions and market/edition tags OK")

print("\n=== GEO: every engine spends it its own way ===")
MY = geo.resolve("malaysia")

g = params(build_google_search_url("kpk", None, None, "relevance", "web", MY))
assert g["gl"] == "my" and g["hl"] == "ms"          # the issue's &gl=my
assert "gl" not in params(build_google_search_url("kpk"))   # absent without --geo

b = params(build_bing_search_url("kpk", None, None, "relevance", "web", MY))
assert b["cc"] == "my" and b["mkt"] == "ms-MY"
assert "cc" not in params(build_bing_search_url("kpk"))

# Yahoo has no country parameter — the region is the host.
assert build_yahoo_search_url("kpk", geo=MY).startswith("https://malaysia.search.yahoo.com/")
assert build_yahoo_search_url("kpk").startswith("https://id.search.yahoo.com/")

# The country has to survive pagination, or only page 1 is localised.
for engine, page2 in ((GOOGLE, "start=10"), (BING, "first=11"), (YAHOO, "b=11")):
    url = engine.build_search_url("kpk", None, None, "relevance", "web", MY)
    paged = engine.build_paginated_url(url, 1)
    assert page2 in paged, (engine.name, paged)
    marker = "malaysia.search.yahoo.com" if engine is YAHOO else "my"
    assert marker in paged, (engine.name, paged)

# A country with no Yahoo property keeps the default host and says so, rather
# than inventing gl.search.yahoo.com and quietly returning nothing.
GL = geo.resolve("greenland")
assert regional_host(GL) is None
assert build_yahoo_search_url("kpk", geo=GL).startswith("https://id.search.yahoo.com/")
assert any("Greenland" in n for n in YAHOO.capability_notes("web", "relevance", None, None, GL))
assert GOOGLE.capability_notes("web", "relevance", None, None, GL) == []
print("  gl=/cc=/regional host, pagination, and the missing-property note OK")

print("\n=== NEWS FILTER: only news articles reach the output ===")
from linktaker import news_filter
from linktaker.news_filter import is_news_url, looks_like_article, registrable_domain

ALLOW = {"detik.com", "tribunnews.com", "fajar.co.id", "infopublik.id"}

# Registrable domain, so one allowlist line covers every regional subdomain.
assert registrable_domain("surabaya.tribunnews.com") == "tribunnews.com"
assert registrable_domain("harian.fajar.co.id") == "fajar.co.id"
assert registrable_domain("www.detik.com") == "detik.com"
assert registrable_domain("detik.com") == "detik.com"

# Article shape: a story has a slug, a date or a CMS id; a listing has none.
assert looks_like_article("https://x.id/berita/kpk-tangkap-bupati-sidoarjo")
assert looks_like_article("https://x.id/2026/08/20/pelni-tambah-rute")
assert looks_like_article("https://x.id/read/8071234")
assert looks_like_article("https://x.id/?p=112078")          # old WordPress permalink
assert not looks_like_article("https://x.id/")               # homepage
assert not looks_like_article("https://x.id/tag/korupsi")    # listing
assert not looks_like_article("https://x.id/indeks")
assert not looks_like_article("https://x.id/laporan-tahunan.pdf")
assert not looks_like_article("https://24timezones.com/difference/jakarta/malaysia")
# A listing word can prefix a real article, and the story id is what proves it.
assert looks_like_article("https://infopublik.id/kategori/nasional/985004/kpk-tahan-eks-pejabat")
assert not looks_like_article("https://infopublik.id/kategori/nusantara/983107/index.html")

# smart: known non-news hosts out, unknown portals still in.
smart = lambda u: is_news_url(u, "smart", ALLOW)
assert smart("https://portalbaru.id/berita/bupati-diperiksa-kpk")   # unknown but news-shaped
assert not smart("https://en.wikipedia.org/wiki/Sidoarjo_Regency")  # encyclopedia
assert not smart("https://www.sinonim.com/sinonim/korupsi")         # dictionary
assert not smart("https://www.traveloka.com/id-id/hotel/malaysia")  # booking
assert not smart("https://www.msn.com/en-my/news/other/a-story/ar-AA2axKai")  # aggregator
assert not smart("https://bekasikab.go.id/pemkab-bekasi-serahkan-hibah-traktor")  # institution
assert not smart("https://www.detik.com/")                          # publisher, but a homepage

# strict: nothing outside the allowlist, however news-shaped it looks.
strict = lambda u: is_news_url(u, "strict", ALLOW)
assert strict("https://news.detik.com/berita/d-8071234/judul-berita-panjang")
assert strict("https://surabaya.tribunnews.com/2026/08/20/kpk-periksa-pejabat")
assert not strict("https://portalbaru.id/berita/bupati-diperiksa-kpk")
assert not strict("https://en.wikipedia.org/wiki/Sidoarjo_Regency")

# off: the pre-filter behaviour, kept for comparison runs.
assert is_news_url("https://en.wikipedia.org/wiki/Sidoarjo_Regency", "off", ALLOW)
assert is_news_url("https://x.id/", "off", ALLOW)
print("  domain rules, article shape, and smart/strict/off modes OK")

print("\n=== NEWS FILTER: the run-wide gate and its rejection report ===")
news_filter.configure("smart", ALLOW)
assert news_filter.accepts("https://portalbaru.id/berita/bupati-diperiksa-kpk")
assert not news_filter.accepts("https://en.wikipedia.org/wiki/Sidoarjo")
assert not news_filter.accepts("https://id.wikipedia.org/wiki/Korupsi")
assert not news_filter.accepts("https://www.sinonim.com/sinonim/korupsi")
assert news_filter.rejected.total == 3
assert news_filter.rejected.by_domain["wikipedia.org"] == 2   # subdomains roll up
assert news_filter.rejected.top(1) == [("wikipedia.org", 2)]

news_filter.configure("off")                       # off records nothing
assert news_filter.accepts("https://en.wikipedia.org/wiki/Sidoarjo")
assert news_filter.rejected.total == 0
print("  gate wiring and rejection counters OK")

# Leave the module on its default so an importing run is not affected.
news_filter.configure("smart")


# --------------------------------------------------------------------------
# CAPTCHA handoff (issue #6): headless by default, a window only when one is
# actually needed, and pagination picking up where it stopped rather than at
# page one.
# --------------------------------------------------------------------------
print("\n=== CAPTCHA: headless borrows a window, then resumes (issue #6) ===")

from linktaker import browser as browser_mod


class HandoffPage(FakePage):
    """A Bing result set whose page 2 is challenged until someone clears it.

    The challenge only lifts while a window is open, which is what makes the
    handoff observable: a run that never opens one never gets past page 2.
    """

    def __init__(self, engine, total_pages, state):
        super().__init__(engine, total_pages)
        self.state = state

    def _blocked(self):
        return self.idx == 1 and not self.state["solved"]

    def wait_for_selector(self, sel, timeout=None):
        if self._blocked():
            if self.state["headed"]:
                self.state["solved"] = True     # a human clears it in the window
                return
            raise RuntimeError("challenge page")
        super().wait_for_selector(sel, timeout)

    def query_selector_all(self, sel):
        return [] if self._blocked() else super().query_selector_all(sel)

    def query_selector(self, sel):
        if self._blocked() and "challenge" in sel:
            return FakeElement(self)            # marks the page as a challenge
        return super().query_selector(sel)

    def content(self):
        return "" if self._blocked() else super().content()


def run_handoff(on_captcha):
    state = {"solved": False, "headed": False, "relaunches": []}
    page = HandoffPage(BING, 3, state)
    mgr = BrowserManager(headless=True, on_captcha=on_captcha)
    mgr._context = FakeContext(page)
    mgr._live_headless = True                   # as if start() had launched headless

    def fake_relaunch(headless):
        # Stands in for the stop/start of a real Chromium; records the swap.
        state["relaunches"].append("headless" if headless else "headed")
        state["headed"] = not headless
        mgr._live_headless = headless
        return True

    mgr._relaunch = fake_relaunch

    slept = browser_mod.time.sleep
    browser_mod.time.sleep = lambda s: None      # skip page and cooldown delays
    try:
        links = mgr.browse_and_paginate("https://start", 3, 2, BING)
    finally:
        browser_mod.time.sleep = slept
    return links, page.visited, state


links, visited, state = run_handoff("headed")
print("navigation:", visited)
print("relaunches:", state["relaunches"])

# One round trip: out to a window for the challenge, straight back to headless.
assert state["relaunches"] == ["headed", "headless"], state["relaunches"]
assert state["solved"]

# The whole point: it resumed at the page that stalled, not back at page 1.
# first=11 is visited three times — the original turn, the headed retry, and the
# headless retry after the solve — while page 1 is never opened again.
assert visited.count("https://start?first=11") == 3, visited
assert visited.count("https://start") == 1, visited
# ...and the walk carried on past the challenged page.
assert "https://start?first=21" in visited, visited

# Page 2 was actually harvested once the challenge cleared, and page 3 followed,
# so the handoff neither dropped a page nor ended the walk.
assert any("bsite1." in l for l in links), sorted(links)
assert any("bsite2." in l for l in links), sorted(links)
print("  headed handoff, resume-in-place, and continued pagination OK")

# skip is what an unattended run uses: no window, no waiting, just stop there.
links, visited, state = run_handoff("skip")
assert state["relaunches"] == [], state["relaunches"]
assert not state["solved"]
assert any("bsite0." in l for l in links), sorted(links)     # page 1 still kept
assert not any("bsite1." in l for l in links), sorted(links)  # challenged page dropped
print("  --on-captcha skip stops without opening a window OK")

print("\nALL CHECKS PASSED")
