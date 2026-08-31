#!/usr/bin/env python3
"""Kirim link hasil crawl ke endpoint submit_batch.

Dipanggil run-linktaker.sh tepat setelah crawl selesai:

    deploy/submit-links.py hasil/links-all-20260831-1100.txt

Setara dengan curl yang biasa dipakai manual:

    curl -X POST http://103.191.17.47:8001/submit_batch/ -H 'Content-Type: application/json' -d '{"links":["..."]}'

Yang diurus di sini dan tidak diurus curl:

  - Link yang sudah pernah terkirim tidak dikirim lagi. Jadwal 3 jam sekali
    dengan --from 1d membuat satu berita yang sama muncul di +-8 run berturut-
    turut; tanpa filter ini topik Kafka menerima delapan salinan tiap berita.
  - Kiriman dipecah per SUBMIT_BATCH_SIZE link, bukan satu body raksasa.
  - Kalau server sedang mati, link masuk antrean dan ikut terkirim pada run
    berikutnya — tidak ada hasil crawl yang hilang karena jaringan.

Hanya memakai pustaka standar Python: tidak ada tambahan di requirements.txt,
dan script ini tetap jalan meski dipanggil dengan python3 sistem.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

URL = os.environ.get("SUBMIT_URL", "http://103.191.17.47:8001/submit_batch/")
BATCH_SIZE = int(os.environ.get("SUBMIT_BATCH_SIZE", "200"))
RETRIES = int(os.environ.get("SUBMIT_RETRIES", "3"))
TIMEOUT = float(os.environ.get("SUBMIT_TIMEOUT", "30"))
STATE_DIR = os.environ.get("SUBMIT_STATE_DIR", "state")
# Umur ingatan "sudah pernah dikirim". Lewat dari ini sebuah link boleh
# terkirim ulang — jauh lebih lama dari jendela crawl (--from 1d), jadi dalam
# praktiknya tidak pernah terjadi selama jendelanya tidak diperlebar.
KEEP_DAYS = int(os.environ.get("SUBMIT_KEEP_DAYS", "30"))
# Batas antrean, supaya server yang mati seminggu tidak memenuhi disk.
QUEUE_MAX = int(os.environ.get("SUBMIT_QUEUE_MAX", "20000"))

SENT_FILE = os.path.join(STATE_DIR, "sent-urls.txt")
QUEUE_FILE = os.path.join(STATE_DIR, "pending-urls.txt")


def log(msg):
    """Satu baris ke stdout — run-linktaker.sh yang mengarahkannya ke log file."""
    print("%s %s" % (datetime.now().astimezone().isoformat(timespec="seconds"), msg))
    sys.stdout.flush()


def key_of(url):
    """Bentuk URL yang dipakai untuk membandingkan, bukan untuk dikirim.

    Dua alamat yang isinya sama sering ditulis berbeda antar mesin pencari:
    http vs https, dengan atau tanpa www., dengan atau tanpa garis miring di
    ujung, kadang berekor #fragment. Yang dikirim tetap URL aslinya.
    """
    try:
        p = urlsplit(url.strip())
        host = p.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = p.path.rstrip("/") or "/"
        return urlunsplit(("", host, path, p.query, ""))
    except ValueError:
        return url.strip()


def read_urls(path):
    """Baca file berisi satu URL per baris; komentar dan baris kosong dibuang."""
    if not path or not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "://" in line:
                out.append(line)
    return out


def read_sent():
    """Riwayat kirim: satu baris "<waktu><TAB><kunci URL>", yang kedaluwarsa dibuang.

    Mengembalikan (kunci yang masih berlaku, baris yang layak ditulis ulang).
    """
    if not os.path.exists(SENT_FILE):
        return set(), []
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    keys, rows = set(), []
    with open(SENT_FILE, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stamp, _, key = line.rstrip("\n").partition("\t")
            if not key:
                continue
            try:
                # Baris yang tanggalnya rusak diperlakukan sebagai masih baru:
                # lebih baik menahan satu link daripada mengirim ulang semuanya.
                if datetime.fromisoformat(stamp).replace(tzinfo=None) < cutoff:
                    continue
            except ValueError:
                pass
            keys.add(key)
            rows.append((stamp, key))
    return keys, rows


def write_lines(path, lines):
    """Tulis lewat file sementara lalu ganti, supaya run yang mati di tengah
    tidak meninggalkan state setengah jadi."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    os.replace(tmp, path)


def post(links):
    """Kirim satu batch. Mengembalikan (berhasil, boleh_dicoba_lagi)."""
    body = json.dumps({"links": links}).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )

    delay = 2.0
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                resp.read(2000)
                return True, False
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read(300).decode("utf-8", "replace").strip()
            except Exception:
                pass
            # 4xx selain 429 tidak akan berubah kalau diulang: payload atau
            # endpoint-nya yang salah. Mengantrekannya hanya membuat batch yang
            # sama gagal lagi tiap 3 jam sampai antrean penuh.
            if 400 <= e.code < 500 and e.code != 429:
                log("  ditolak HTTP %s (tidak diulang): %s" % (e.code, detail))
                return False, False
            log("  percobaan %d/%d gagal: HTTP %s %s" % (attempt, RETRIES, e.code, detail))
        except Exception as e:
            log("  percobaan %d/%d gagal: %s" % (attempt, RETRIES, e))

        if attempt < RETRIES:
            time.sleep(delay)
            delay *= 2

    return False, True


def main(argv):
    # Beberapa file sekaligus diperbolehkan, supaya `submit-links.py hasil/*.txt`
    # bisa dipakai untuk mengirim ulang hasil yang menumpuk.
    files = [a for a in argv[1:] if not a.startswith("-")]
    dry_run = "--dry-run" in argv

    fresh = [url for path in files for url in read_urls(path)]
    # Antrean lebih dulu: sisa run sebelumnya yang paling berhak terkirim.
    queued = read_urls(QUEUE_FILE)
    sent_keys, sent_rows = read_sent()

    # Buang yang sudah pernah terkirim, dan yang kembar di dalam batch ini
    # sendiri — hasil crawl sudah unik per run, tapi antrean bisa memuat link
    # yang muncul lagi di run sekarang.
    links, seen = [], set()
    for url in queued + fresh:
        k = key_of(url)
        if k in sent_keys or k in seen:
            continue
        seen.add(k)
        links.append(url)

    skipped = len(fresh) + len(queued) - len(links)
    log("kirim: %d link (%d dari hasil, %d dari antrean, %d dilewati (duplikat atau sudah pernah dikirim))"
        % (len(links), len(fresh), len(queued), skipped))

    if not links:
        # Antrean sudah habis atau isinya ternyata sudah terkirim — kosongkan
        # supaya tidak dibaca ulang tiap run.
        if queued:
            write_lines(QUEUE_FILE, [])
        return 0

    if dry_run:
        log("--dry-run: tidak ada yang dikirim. Tujuan: %s" % URL)
        for url in links[:5]:
            print("  " + url)
        if len(links) > 5:
            print("  ... dan %d lainnya" % (len(links) - 5))
        return 0

    ok_count, failed, dropped = 0, [], 0
    batches = [links[i:i + BATCH_SIZE] for i in range(0, len(links), BATCH_SIZE)]
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")

    for n, batch in enumerate(batches, 1):
        # Batch sesudah kegagalan jaringan tidak perlu ikut menunggu timeout
        # satu per satu; server yang mati akan tetap mati 30 detik lagi.
        if failed:
            failed.extend(batch)
            continue
        log("batch %d/%d (%d link) -> %s" % (n, len(batches), len(batch), URL))
        ok, retryable = post(batch)
        if ok:
            ok_count += len(batch)
            sent_rows.extend((stamp, key_of(u)) for u in batch)
        elif retryable:
            failed.extend(batch)
        else:
            dropped += len(batch)

    # Riwayat ditulis lebih dulu: kalau proses mati di antara dua penulisan,
    # link yang terlanjur terkirim tidak ikut dikirim ulang.
    write_lines(SENT_FILE, ["%s\t%s" % (s, k) for s, k in sent_rows])
    write_lines(QUEUE_FILE, failed[-QUEUE_MAX:])

    if failed:
        log("terkirim %d, %d masuk antrean untuk run berikutnya (%s)"
            % (ok_count, len(failed), QUEUE_FILE))
    else:
        log("terkirim %d link" % ok_count)
    if dropped:
        log("%d link dibuang karena ditolak server" % dropped)

    return 1 if failed or dropped else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
