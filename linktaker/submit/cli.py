"""Perintah `python -m linktaker.submit` — merangkai state, client, dan setelan.

    python -m linktaker.submit data/hasil/links-all-20260831-1100.txt
    python -m linktaker.submit data/hasil/*.txt --dry-run

Tanpa argumen file pun tetap berguna: antrean dari run yang gagal kirim
sebelumnya ikut dikosongkan di sini, jadi run yang crawl-nya gagal atau
menghasilkan 0 link tetap menuntaskan sisa kiriman.
"""

import argparse
import sys
from datetime import datetime

from .client import Submitter
from .settings import Settings
from .state import PendingQueue, SentLog, read_url_file, select_new


def log(msg):
    """Satu baris ke stdout — run-linktaker.sh yang mengarahkannya ke log file."""
    print("%s %s" % (datetime.now().astimezone().isoformat(timespec="seconds"), msg))
    sys.stdout.flush()


def build_parser():
    p = argparse.ArgumentParser(
        prog="python -m linktaker.submit",
        description="Kirim hasil crawl ke endpoint submit_batch.",
    )
    p.add_argument("files", nargs="*", metavar="FILE",
                   help="file hasil crawl, satu URL per baris (boleh lebih dari satu)")
    p.add_argument("--dry-run", action="store_true",
                   help="tampilkan apa yang akan dikirim, tanpa mengirim")
    p.add_argument("--url", metavar="URL", help="endpoint tujuan")
    p.add_argument("--batch-size", type=int, metavar="N", help="link per satu POST")
    p.add_argument("--state-dir", metavar="DIR",
                   help="lokasi riwayat kirim dan antrean")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    # Environment dulu (dari deploy/linktaker.env), lalu flag menimpanya —
    # urutan yang sama dengan setelan crawl.
    settings = Settings.from_env()
    for name in ("url", "batch_size", "state_dir"):
        value = getattr(args, name)
        if value is not None:
            setattr(settings, name, value)

    fresh = [url for path in args.files for url in read_url_file(path)]
    queue = PendingQueue(settings.queue_file, settings.queue_max)
    queued = queue.load()          # sisa run sebelumnya, dikirim lebih dulu
    sent = SentLog(settings.sent_file, settings.keep_days).load()

    links = select_new(queued + fresh, sent)
    log("kirim: %d link (%d dari hasil, %d dari antrean, %d dilewati "
        "(duplikat atau sudah pernah dikirim))"
        % (len(links), len(fresh), len(queued), len(fresh) + len(queued) - len(links)))

    if not links:
        # Antrean ternyata sudah terkirim semua — kosongkan supaya tidak
        # dibaca ulang tiap run.
        if queued:
            queue.clear()
        return 0

    if args.dry_run:
        log("--dry-run: tidak ada yang dikirim. Tujuan: %s" % settings.url)
        for url in links[:5]:
            print("  " + url)
        if len(links) > 5:
            print("  ... dan %d lainnya" % (len(links) - 5))
        return 0

    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    submitter = Submitter(settings, log=log,
                          on_sent=lambda batch: sent.add(batch, stamp))
    result = submitter.send(links)

    # Riwayat ditulis lebih dulu: kalau proses mati di antara dua penulisan,
    # link yang terlanjur terkirim tidak ikut dikirim ulang.
    sent.save()
    queue.save(result.queued)

    if result.queued:
        log("terkirim %d, %d masuk antrean untuk run berikutnya (%s)"
            % (result.sent, len(result.queued), settings.queue_file))
    else:
        log("terkirim %d link" % result.sent)
    if result.dropped:
        log("%d link dibuang karena ditolak server" % result.dropped)

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
