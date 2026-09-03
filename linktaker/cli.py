import argparse
import os
import random
import signal
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import geo, news_filter
from .browser import BrowserManager, reset_profile
from .config import (
    KEYWORDS_FILE, URLS_FILE, PROXIES_FILE, OUT_FILE, NEWS_DOMAINS_FILE,
    MAX_PAGES_PER_SEARCH, DEFAULT_SORT, DEFAULT_ENGINE, NEWS_FILTER,
    FETCH_MODE, USE_GOOGLE_RSS, RSS_DECODE_DELAY,
    USE_CLOUDFLARE_BYPASS, PARALLEL_WORKERS, SOCIAL_MEDIA_DOMAINS,
    PERSIST_PROFILE, BROWSER_PROFILE_DIR, DEFAULT_GEO,
    HEADLESS, ON_CAPTCHA, CAPTCHA_WAIT_TIMEOUT,
)
from .deps import CLOUDSCRAPER_AVAILABLE, STEALTH_AVAILABLE, BROWSERFORGE_AVAILABLE, PLAYWRIGHT_AVAILABLE
from .engines import ENGINES, MODE_LABELS, SEARCH_MODES, expand_mode, get_engine
from .fetchers import process_one_url
from .inputs import (RELATIVE_HELP, parse_date, read_auth, read_keywords,
                     read_news_domains, read_proxies, read_urls)
from .url_utils import strip_amp

EXAMPLE = """example:
  python linktaker.py --input keyword1.txt --from 2026-08-08 --until 2026-08-16 --sort latest --output hasil.txt --max-pages 2

  python linktaker.py --engine bing --input keyword1.txt --from 2026-08-08 --until 2026-08-16 --sort latest
  python linktaker.py --engine yahoo --input keyword1.txt --from 2026-08-08 --until 2026-08-16
  python linktaker.py --input keyword1.txt
  python linktaker.py --input keyword1.txt --mode both --from 2026-08-08 --until 2026-08-16
  python linktaker.py --input keyword1.txt --proxy http://user:password@proxycrawler.dashboard.nolimit.id:2570

  # news only, allowlisted publishers exclusively (bing and yahoo need this most)
  python linktaker.py --engine bing --input keyword1.txt --news-filter strict

  # search as if from another country — a code or the country's name
  python linktaker.py --input keyword1.txt --geo my
  python linktaker.py --input keyword1.txt --geo malaysia
  python linktaker.py --engine all --input keyword1.txt --geo singapura

  # run google, yahoo and bing back to back into one merged output file
  python linktaker.py --engine all --input keyword1.txt --from 2026-08-18 --until 2026-08-24 --sort latest --mode both --output hasil.txt

  # relative dates — resolved every run, so a schedule never falls behind
  python linktaker.py --input keyword1.txt --from w                 # last week to now
  python linktaker.py --input keyword1.txt --from 3d --until today  # last three days
  python linktaker.py --input keyword1.txt --from 1m --sort latest  # last month

  # unattended (cron, systemd): no window at all, challenged pages dropped
  python linktaker.py --input keyword1.txt --from w --headless --on-captcha skip

  # attended: no window until a CAPTCHA needs one, then straight back to headless
  python linktaker.py --input keyword1.txt --headless --on-captcha headed
"""


def positive_int(value: str) -> int:
    """argparse type for --max-pages."""
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number, got '{value}'")
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or greater, got '{value}'")
    return number


def build_parser():
    parser = argparse.ArgumentParser(
        prog="linktaker.py",
        description="Collect result links from Google or Bing search for a list of keywords.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EXAMPLE,
    )
    parser.add_argument(
        "--engine", choices=tuple(ENGINES) + ("all",), default=DEFAULT_ENGINE,
        help=f"search engine to crawl, or 'all' to run google, yahoo and bing "
             f"back to back into one merged output file (default: {DEFAULT_ENGINE})",
    )
    parser.add_argument(
        "--input", metavar="FILE", default=KEYWORDS_FILE,
        help=f"text file with one keyword per line (default: {KEYWORDS_FILE})",
    )
    parser.add_argument(
        "--from", dest="date_from", metavar="DATE",
        help=f"only results published on/after this date (optional). "
             f"{RELATIVE_HELP}. A relative date is resolved on every run, so a "
             f"scheduled crawl keeps asking for the same window as the "
             f"calendar moves",
    )
    parser.add_argument(
        "--until", dest="date_until", metavar="DATE",
        help=f"only results published on/before this date (optional). "
             f"Same formats as --from",
    )
    parser.add_argument(
        "--sort", choices=("latest", "relevance"), default=DEFAULT_SORT,
        help=f"result ordering (default: {DEFAULT_SORT})",
    )
    parser.add_argument(
        "--geo", metavar="COUNTRY", default=DEFAULT_GEO,
        help="search as if from this country — an ISO country code (my) or a "
             "country name (malaysia, jerman). Google gets gl=, Bing cc=, and "
             "Yahoo its regional site "
             f"(default: {DEFAULT_GEO or 'wherever the browser appears to be'})",
    )
    parser.add_argument(
        "--output", metavar="FILE", default=OUT_FILE,
        help=f"file to write the collected links to (default: {OUT_FILE})",
    )
    parser.add_argument(
        "--max-pages", "--max_pages", dest="max_pages", metavar="N", type=positive_int,
        default=MAX_PAGES_PER_SEARCH,
        help="max result pages to crawl per keyword (default: all pages)",
    )
    parser.add_argument(
        "--proxy", metavar="URL", default=None,
        help="proxy to route requests through, e.g. http://user:password@host:2570 (default: no proxy)",
    )
    parser.add_argument(
        "--fresh-profile", "--fresh_profile", dest="fresh_profile", action="store_true",
        help=f"delete {BROWSER_PROFILE_DIR}/ and its pinned fingerprint before "
             f"starting, so the run begins from a clean browser. Use this when "
             f"the saved profile itself has been flagged and every search is "
             f"landing on a CAPTCHA",
    )
    parser.add_argument(
        "--headless", dest="headless", action="store_true", default=HEADLESS,
        help=f"run the browser without a window "
             f"(default: {'headless' if HEADLESS else 'headed'})",
    )
    parser.add_argument(
        "--headed", "--no-headless", dest="headless", action="store_false",
        help="run with a visible browser window throughout",
    )
    parser.add_argument(
        "--on-captcha", "--on_captcha", dest="on_captcha",
        choices=("headed", "skip"), default=ON_CAPTCHA,
        help=f"what a headless run does at a challenge page: headed = reopen "
             f"the same profile with a window at that result page, wait for a "
             f"human, then go back to headless and carry on; skip = drop the "
             f"page and move on, which is the setting an unattended run wants "
             f"(default: {ON_CAPTCHA})",
    )
    parser.add_argument(
        "--mode", choices=SEARCH_MODES, default=None,
        help="which tab to search: web = all tab, nws = news tab, "
             "both = all tab + news tab merged "
             "(default: web for google/bing/yahoo)",
    )
    parser.add_argument(
        "--news-filter", "--news_filter", dest="news_filter",
        choices=("smart", "strict", "off"), default=NEWS_FILTER,
        help=f"keep only news articles in the output: smart = drop known "
             f"non-news hosts and non-article URLs, strict = only hosts in "
             f"{NEWS_DOMAINS_FILE}, off = keep everything "
             f"(default: {NEWS_FILTER})",
    )
    parser.add_argument(
        "--news-domains", "--news_domains", dest="news_domains",
        metavar="FILE", default=NEWS_DOMAINS_FILE,
        help=f"publisher allowlist, one domain per line "
             f"(default: {NEWS_DOMAINS_FILE})",
    )
    return parser


def describe_date(resolved, raw) -> str:
    """The date, plus the shorthand it came from when the two differ."""
    if raw and str(raw).strip().lower() != resolved.isoformat():
        return f"{resolved} (dari '{raw}')"
    return str(resolved)


def parse_args(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.engine == "all":
        # Per-engine mode default is resolved per iteration in main().
        pass
    else:
        args.engine = get_engine(args.engine)
        if args.mode is None:
            args.mode = args.engine.default_mode

    if args.geo:
        try:
            args.geo = geo.resolve(args.geo)
        except ValueError as e:
            parser.error(str(e))

    # Keep what was typed. "w" resolving to a date is exactly the thing worth
    # showing back, and an out-of-order range is unreadable as two ISO dates
    # when the user wrote a relative one.
    args.date_from_raw = args.date_from
    args.date_until_raw = args.date_until

    if args.date_from:
        try:
            args.date_from = parse_date(args.date_from, "--from")
        except ValueError as e:
            parser.error(str(e))

    if args.date_until:
        try:
            args.date_until = parse_date(args.date_until, "--until")
        except ValueError as e:
            parser.error(str(e))

    if args.date_from and args.date_until and args.date_from > args.date_until:
        parser.error(f"--from ({describe_date(args.date_from, args.date_from_raw)}) "
                     f"is later than --until "
                     f"({describe_date(args.date_until, args.date_until_raw)})")

    args.allowlist = read_news_domains(args.news_domains)
    if args.news_filter == "strict" and not args.allowlist:
        parser.error(f"--news-filter strict needs a populated {args.news_domains}, "
                     f"otherwise every link is rejected. Add domains to it, point "
                     f"--news-domains at another file, or use --news-filter smart.")

    return args


def build_urls(args, engine, mode):
    """Turn the keyword input file into a list of search URLs for one engine."""
    if os.path.exists(args.input):
        keywords = read_keywords(args.input)
        if not keywords:
            print(f"No keywords found in {args.input} — the file is empty or only has comments.")
            sys.exit(1)

        print(f"Loaded {len(keywords)} keyword(s) from {args.input}")
        urls = []
        for kw in keywords:
            for m in expand_mode(mode):
                url = engine.build_search_url(kw, args.date_from, args.date_until,
                                               args.sort, m, args.geo)
                # Yahoo builds the same URL for either vertical — crawl it once.
                if url not in urls:
                    urls.append(url)
        return urls

    # Fallback: pre-built Google search URLs (backwards compatible).
    if os.path.exists(URLS_FILE):
        urls = read_urls(URLS_FILE)
        if urls:
            print(f"{args.input} not found — loaded {len(urls)} search URL(s) from {URLS_FILE}")
            return urls

    print(f"Input file not found: {args.input}")
    print("Create it with one keyword per line, or point --input at another file.")
    sys.exit(1)


def resolve_proxies(args):
    """--proxy wins; otherwise fall back to proxies.txt when it exists; otherwise no proxy."""
    if args.proxy:
        return [args.proxy]
    if os.path.exists(PROXIES_FILE):
        return read_proxies(PROXIES_FILE)
    return []


def describe_run(args, engine, mode, url_count):
    """Print what this run is about to do."""
    # Show the resolved dates: a relative window is the whole point of being
    # able to leave this on a schedule, and it is also the one thing a reader
    # cannot check by eye.
    date_from = describe_date(args.date_from, getattr(args, "date_from_raw", None))
    date_until = describe_date(args.date_until, getattr(args, "date_until_raw", None))

    if args.date_from and args.date_until:
        date_range = f"{date_from} .. {date_until}"
    elif args.date_from:
        date_range = f"from {date_from}"
    elif args.date_until:
        date_range = f"until {date_until}"
    else:
        date_range = "any date"

    pages = "all" if args.max_pages is None else str(args.max_pages)
    region = str(args.geo) if args.geo else "not set"
    print(f"Processing {url_count} search(es) on {engine.name} "
          f"— fetch mode: {FETCH_MODE}, search: {MODE_LABELS.get(mode, mode)}")
    print(f"Date: {date_range} | Sort: {args.sort} | Max pages: {pages} | Output: {args.output}")
    print(f"Geolocation: {region}")

    if args.geo:
        # Worth being explicit: this asks the engine for another country's
        # results, it does not move the request there. A run from Jakarta still
        # leaves from Jakarta unless --proxy sends it somewhere else.
        print("  --geo sets the country the engine searches as, not where the "
              "request comes from — pair it with --proxy for a local IP")

    if args.news_filter == "off":
        print("News filter: OFF — every non-social link is kept, including "
              "dictionaries, shops and tools")
    else:
        print(f"News filter: {args.news_filter} "
              f"({len(args.allowlist)} publisher(s) from {args.news_domains})")

    if PERSIST_PROFILE:
        print(f"Browser profile: PERSISTENT ({BROWSER_PROFILE_DIR}/) — "
              f"cookies carry over between runs; --fresh-profile resets it")
    else:
        print("Browser profile: fresh each run (PERSIST_PROFILE is off) — "
              "expect a challenge on the first search")

    if args.headless:
        if args.on_captcha == "headed":
            print(f"Browser window: headless, borrowing a window per CAPTCHA "
                  f"(waits up to {CAPTCHA_WAIT_TIMEOUT}s for a human, then "
                  f"resumes headless at the same result page)")
            if not PERSIST_PROFILE:
                # The swap can only carry a solve through the cookie jar on disk.
                print("  PERSIST_PROFILE is off, so a solved CAPTCHA cannot be "
                      "carried back into headless — challenged pages will be "
                      "skipped. Use --headed for an attended run.")
        else:
            print("Browser window: headless, challenged pages are skipped "
                  "(--on-captcha skip) — the right setting when no one is watching")
    else:
        print("Browser window: headed throughout")

    if args.max_pages is None:
        print("Max pages: all — crawling deep into the result set is the biggest "
              "remaining CAPTCHA trigger; --max-pages 5 cuts it sharply")

    for note in engine.capability_notes(mode, args.sort, args.date_from,
                                        args.date_until, args.geo):
        print(note)


def crawl_engine(args, engine, mode):
    """Run one engine's crawl for every keyword, returning the unique links found."""
    urls = build_urls(args, engine, mode)
    proxies = resolve_proxies(args)
    auth = read_auth()

    describe_run(args, engine, mode, len(urls))
    print(f"Filtering social media URLs ({len(SOCIAL_MEDIA_DOMAINS)} domains excluded)")

    if USE_GOOGLE_RSS and engine.name == "google":
        # The RSS feed is a news-tab feature; an All-tab URL has no feed to read.
        if "nws" in expand_mode(mode):
            print(f"Google News RSS: ENABLED (decode delay: {RSS_DECODE_DELAY}s)")
        else:
            print("Google News RSS: skipped — it only covers the news tab (--mode nws/both)")

    if proxies:
        print(f"Proxy enabled ({len(proxies)} proxy/proxies)")
    else:
        print("No proxy configured - proceeding without proxy")

    if USE_CLOUDFLARE_BYPASS:
        if CLOUDSCRAPER_AVAILABLE:
            print(f"Cloudflare bypass: ENABLED (cloudscraper)")
        else:
            print(f"Cloudflare bypass: curl_cffi only")

    if STEALTH_AVAILABLE:
        print(f"Playwright stealth: ENABLED")
    if BROWSERFORGE_AVAILABLE:
        print(f"browserforge fingerprints: ENABLED")

    # Create persistent browser manager (shared across all pages)
    browser_mgr = None
    if FETCH_MODE in ("auto", "playwright") and PLAYWRIGHT_AVAILABLE:
        proxy = random.choice(proxies) if proxies else None
        # The handoff stops and restarts the shared browser. On the threaded
        # path that would pull the context out from under every other worker
        # mid-fetch, and Chromium would refuse the relaunch anyway while the
        # others still hold the profile's single-instance lock. Only the
        # sequential path can afford it.
        on_captcha = args.on_captcha
        if FETCH_MODE != "playwright" and on_captcha == "headed" \
                and min(PARALLEL_WORKERS, len(urls)) > 1:
            print("Note: --on-captcha headed needs one browser at a time — "
                  "using skip for this parallel run (FETCH_MODE=playwright "
                  "runs sequentially and supports it)")
            on_captcha = "skip"
        browser_mgr = BrowserManager(proxy=proxy, headless=args.headless,
                                     on_captcha=on_captcha)
        # Lazy start — only launches when first needed
        print(f"Persistent browser: READY (will launch on first use)")

    all_links = set()

    try:
        # When using playwright mode, run sequentially (one browser)
        if FETCH_MODE == "playwright":
            # Shuffle so the date walk isn't sequential (less scraper-like)
            shuffled = list(urls)
            random.shuffle(shuffled)
            for i, u in enumerate(shuffled):
                all_links |= (process_one_url(u, None, auth, browser_mgr,
                                              args.max_pages, engine) or set())
                # Jitter between search URLs to avoid burst-rate detection
                if i < len(shuffled) - 1:
                    delay = random.uniform(1, 5)
                    print(f"  Waiting {delay:.1f}s before next URL...")
                    time.sleep(delay)
        else:
            workers = min(PARALLEL_WORKERS, len(urls))
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futures = {}
                    for u in urls:
                        proxy = random.choice(proxies) if proxies else None
                        futures[ex.submit(process_one_url, u, proxy, auth, browser_mgr,
                                          args.max_pages, engine)] = u

                    for fut in as_completed(futures):
                        u = futures[fut]
                        try:
                            res = fut.result() or set()
                            all_links |= res
                        except Exception as e:
                            print(f"[{u}] Failed: {e}")
            else:
                for u in urls:
                    proxy = random.choice(proxies) if proxies else None
                    all_links |= (process_one_url(u, proxy, auth, browser_mgr,
                                                  args.max_pages, engine) or set())
    finally:
        # Always close browser
        if browser_mgr:
            browser_mgr.close()
            print(f"Browser closed")

    # Strip AMP from all collected links
    return {strip_amp(link) for link in all_links}


def _berhenti_pada_sigterm(signum, frame):
    """Ubah SIGTERM jadi KeyboardInterrupt.

    Perilaku bawaan Python untuk SIGTERM adalah mati seketika: blok `finally`
    tidak jalan, browser tidak ditutup rapi — sehingga cookie profil yang
    menahan CAPTCHA tidak sempat ditulis ke disk — dan link yang sudah
    terkumpul di engine yang sedang berjalan ikut hilang.

    Yang mengirim SIGTERM ke sini bukan hal langka: `timeout` di
    run-linktaker.sh, `pm2 stop`, `pm2 restart`, dan `systemctl stop`. Dijadikan
    KeyboardInterrupt supaya semuanya lewat jalur berhenti yang sama dengan
    Ctrl-C, yang sudah menyimpan hasil dan menutup browser.
    """
    raise KeyboardInterrupt


def main(argv=None):
    """Main execution."""
    signal.signal(signal.SIGTERM, _berhenti_pada_sigterm)

    args = parse_args(argv)

    if args.fresh_profile:
        reset_profile()

    # Arm the news gate before any extractor runs — every engine reaches it
    # through url_utils.is_valid_result_url.
    news_filter.configure(args.news_filter, args.allowlist)

    if args.engine == "all":
        # Google, then Yahoo, then Bing — one after another, merged into one output.
        engines_to_run = [ENGINES["google"], ENGINES["yahoo"], ENGINES["bing"]]
    else:
        engines_to_run = [args.engine]

    all_links = set()
    gagal = []
    for i, engine in enumerate(engines_to_run):
        if len(engines_to_run) > 1:
            print(f"\n=== Engine {i + 1}/{len(engines_to_run)}: {engine.name} ===")
        mode = args.mode or engine.default_mode
        try:
            all_links |= crawl_engine(args, engine, mode)
        except KeyboardInterrupt:
            # Ctrl-C, atau SIGTERM dari `timeout`/`pm2 stop`/`systemctl stop`
            # lewat _berhenti_pada_sigterm. Browser sudah ditutup oleh blok
            # finally di crawl_engine saat exception ini lewat, jadi di sini
            # tinggal menyimpan apa yang sempat terkumpul.
            print(f"\nDihentikan di engine {engine.name} — menyimpan yang sudah terkumpul")
            write_output(args.output, all_links)
            print(f"Links saved to {args.output} (unique: {len(all_links)})")
            # 130 = konvensi "dihentikan oleh sinyal". Bukan crawl yang gagal.
            return 130
        except Exception as e:
            # Satu engine yang gagal tidak boleh menghapus hasil engine lain.
            # Sebelum ini, exception di engine ketiga membuat seluruh run
            # berakhir tanpa file output sama sekali — termasuk link dari dua
            # engine yang sudah selesai dengan baik.
            print(f"\nEngine {engine.name} gagal: {e}")
            traceback.print_exc()
            gagal.append(engine.name)

        # Ditulis ulang tiap engine selesai, bukan sekali di akhir. File hasil
        # jadi selalu berisi apa pun yang sudah didapat sampai detik itu.
        write_output(args.output, all_links)

    print(f"\nLinks saved to {args.output} (unique: {len(all_links)})")
    if gagal:
        print(f"Engine yang gagal dan tidak menyumbang link: {', '.join(gagal)}")
    report_rejections()

    # Semua engine gagal berarti run ini memang gagal, dan exit code-nya harus
    # bilang begitu supaya terlihat di log scheduler. Sebagian gagal tidak:
    # file hasil tetap terisi dari engine yang berhasil, dan baris "Engine yang
    # gagal" di atas sudah menjelaskan sisanya.
    if gagal and len(gagal) == len(engines_to_run):
        return 1
    return 0


def write_output(path, links):
    """Tulis seluruh link ke file, menimpa isi sebelumnya.

    Dipanggil tiap engine selesai. Mode "w" memang menimpa, dan itu yang
    diinginkan: `links` selalu berisi akumulasi dari awal run, bukan potongan
    engine terakhir saja.
    """
    out_dir = os.path.dirname(os.path.abspath(path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for link in sorted(links):
            f.write(link + "\n")


def report_rejections(limit: int = 15):
    """List the hosts the news gate turned away, busiest first.

    This is how news_domains.txt grows: anything in here that is actually a
    publisher belongs in the allowlist, and anything that is not confirms the
    gate did its job.
    """
    dropped = news_filter.rejected
    if not dropped.total:
        return

    top = dropped.top(limit)
    print(f"News filter dropped {dropped.total} link(s) from "
          f"{len(dropped.by_domain)} host(s):")
    for domain, count in top:
        print(f"  {count:>5}  {domain}")

    remaining = len(dropped.by_domain) - len(top)
    if remaining > 0:
        print(f"  ... and {remaining} more host(s)")
    print(f"Any real publisher listed above belongs in {NEWS_DOMAINS_FILE}.")
