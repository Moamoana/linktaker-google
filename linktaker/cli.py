import argparse
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import news_filter
from .browser import BrowserManager
from .config import (
    KEYWORDS_FILE, URLS_FILE, PROXIES_FILE, OUT_FILE, NEWS_DOMAINS_FILE,
    MAX_PAGES_PER_SEARCH, DEFAULT_SORT, DEFAULT_ENGINE, NEWS_FILTER,
    FETCH_MODE, USE_GOOGLE_RSS, RSS_DECODE_DELAY,
    USE_CLOUDFLARE_BYPASS, PARALLEL_WORKERS, SOCIAL_MEDIA_DOMAINS,
)
from .deps import CLOUDSCRAPER_AVAILABLE, STEALTH_AVAILABLE, BROWSERFORGE_AVAILABLE, PLAYWRIGHT_AVAILABLE
from .engines import ENGINES, MODE_LABELS, SEARCH_MODES, expand_mode, get_engine
from .fetchers import process_one_url
from .inputs import (parse_date, read_auth, read_keywords, read_news_domains,
                     read_proxies, read_urls)
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
        "--engine", choices=tuple(ENGINES), default=DEFAULT_ENGINE,
        help=f"search engine to crawl (default: {DEFAULT_ENGINE})",
    )
    parser.add_argument(
        "--input", metavar="FILE", default=KEYWORDS_FILE,
        help=f"text file with one keyword per line (default: {KEYWORDS_FILE})",
    )
    parser.add_argument(
        "--from", dest="date_from", metavar="YYYY-MM-DD",
        help="only results published on/after this date (optional)",
    )
    parser.add_argument(
        "--until", dest="date_until", metavar="YYYY-MM-DD",
        help="only results published on/before this date (optional)",
    )
    parser.add_argument(
        "--sort", choices=("latest", "relevance"), default=DEFAULT_SORT,
        help=f"result ordering (default: {DEFAULT_SORT})",
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


def parse_args(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    args.engine = get_engine(args.engine)
    if args.mode is None:
        args.mode = args.engine.default_mode

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
        parser.error(f"--from ({args.date_from}) is later than --until ({args.date_until})")

    args.allowlist = read_news_domains(args.news_domains)
    if args.news_filter == "strict" and not args.allowlist:
        parser.error(f"--news-filter strict needs a populated {args.news_domains}, "
                     f"otherwise every link is rejected. Add domains to it, point "
                     f"--news-domains at another file, or use --news-filter smart.")

    return args


def build_urls(args):
    """Turn the keyword input file into a list of Google search URLs."""
    if os.path.exists(args.input):
        keywords = read_keywords(args.input)
        if not keywords:
            print(f"No keywords found in {args.input} — the file is empty or only has comments.")
            sys.exit(1)

        print(f"Loaded {len(keywords)} keyword(s) from {args.input}")
        urls = []
        for kw in keywords:
            for mode in expand_mode(args.mode):
                url = args.engine.build_search_url(kw, args.date_from, args.date_until,
                                                   args.sort, mode)
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


def describe_run(args, url_count):
    """Print what this run is about to do."""
    if args.date_from and args.date_until:
        date_range = f"{args.date_from} .. {args.date_until}"
    elif args.date_from:
        date_range = f"from {args.date_from}"
    elif args.date_until:
        date_range = f"until {args.date_until}"
    else:
        date_range = "any date"

    pages = "all" if args.max_pages is None else str(args.max_pages)
    print(f"Processing {url_count} search(es) on {args.engine.name} "
          f"— fetch mode: {FETCH_MODE}, search: {MODE_LABELS.get(args.mode, args.mode)}")
    print(f"Date: {date_range} | Sort: {args.sort} | Max pages: {pages} | Output: {args.output}")

    if args.news_filter == "off":
        print("News filter: OFF — every non-social link is kept, including "
              "dictionaries, shops and tools")
    else:
        print(f"News filter: {args.news_filter} "
              f"({len(args.allowlist)} publisher(s) from {args.news_domains})")

    for note in args.engine.capability_notes(args.mode, args.sort,
                                            args.date_from, args.date_until):
        print(note)


def main(argv=None):
    """Main execution."""
    args = parse_args(argv)

    # Arm the news gate before any extractor runs — every engine reaches it
    # through url_utils.is_valid_result_url.
    news_filter.configure(args.news_filter, args.allowlist)

    urls = build_urls(args)
    proxies = resolve_proxies(args)
    auth = read_auth()

    describe_run(args, len(urls))
    print(f"Filtering social media URLs ({len(SOCIAL_MEDIA_DOMAINS)} domains excluded)")

    if USE_GOOGLE_RSS and args.engine.name == "google":
        # The RSS feed is a news-tab feature; an All-tab URL has no feed to read.
        if "nws" in expand_mode(args.mode):
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
        browser_mgr = BrowserManager(proxy=proxy)
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
                                              args.max_pages, args.engine) or set())
                # Jitter between search URLs to avoid burst-rate detection
                if i < len(shuffled) - 1:
                    delay = random.uniform(8, 20)
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
                                          args.max_pages, args.engine)] = u

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
                                                  args.max_pages, args.engine) or set())
    finally:
        # Always close browser
        if browser_mgr:
            browser_mgr.close()
            print(f"Browser closed")

    # Strip AMP from all collected links
    all_links = {strip_amp(link) for link in all_links}

    # Write results
    out_dir = os.path.dirname(os.path.abspath(args.output))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for link in sorted(all_links):
            f.write(link + "\n")

    print(f"\nLinks saved to {args.output} (unique: {len(all_links)})")
    report_rejections()


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
