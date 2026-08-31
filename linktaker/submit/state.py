"""Ingatan antar-run: apa yang sudah terkirim, dan apa yang masih tertunda.

Dua file teks di dalam SUBMIT_STATE_DIR:

    sent-urls.txt      "<waktu><TAB><kunci URL>" — supaya berita yang sama
                       tidak dikirim delapan kali sehari
    pending-urls.txt   URL yang belum berhasil dikirim, dicoba lagi run berikutnya

Keduanya sengaja teks biasa, satu baris per entri: bisa dibaca `wc -l`, `grep`,
dan `tail` saat run terjadwal perlu diperiksa jam tiga pagi.
"""

import os
from datetime import datetime, timedelta

from ..url_utils import dedup_key


def _write_lines(path, lines):
    """Tulis lewat file sementara lalu ganti.

    Run yang mati di tengah penulisan tidak boleh meninggalkan state setengah
    jadi — yang berarti riwayat kirim rusak dan ribuan link terkirim ulang.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    os.replace(tmp, path)


def read_url_file(path):
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


class SentLog:
    """Kunci URL yang sudah pernah terkirim, beserta kapan."""

    def __init__(self, path, keep_days):
        self.path = path
        self.keep_days = keep_days
        self.rows = []       # [(stamp, key)] yang layak ditulis ulang
        self.keys = set()

    def load(self):
        """Muat riwayat, buang yang lewat umur."""
        self.rows, self.keys = [], set()
        if not os.path.exists(self.path):
            return self
        cutoff = datetime.now() - timedelta(days=self.keep_days)
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stamp, _, key = line.rstrip("\n").partition("\t")
                if not key:
                    continue
                try:
                    # Baris yang tanggalnya rusak diperlakukan sebagai masih
                    # baru: lebih baik menahan satu link daripada mengirim
                    # ulang seluruh riwayat.
                    if datetime.fromisoformat(stamp).replace(tzinfo=None) < cutoff:
                        continue
                except ValueError:
                    pass
                self.keys.add(key)
                self.rows.append((stamp, key))
        return self

    def __contains__(self, url):
        return dedup_key(url) in self.keys

    def add(self, urls, stamp=None):
        stamp = stamp or datetime.now().astimezone().isoformat(timespec="seconds")
        for url in urls:
            key = dedup_key(url)
            if key not in self.keys:
                self.keys.add(key)
            self.rows.append((stamp, key))

    def save(self):
        _write_lines(self.path, ["%s\t%s" % (s, k) for s, k in self.rows])


class PendingQueue:
    """Link yang gagal terkirim dan menunggu run berikutnya."""

    def __init__(self, path, max_items):
        self.path = path
        self.max_items = max_items

    def load(self):
        return read_url_file(self.path)

    def save(self, urls):
        # Yang terbaru yang dipertahankan saat antrean melebihi batas: endpoint
        # yang mati seminggu tidak boleh memenuhi disk, dan berita lama paling
        # kecil nilainya.
        _write_lines(self.path, urls[-self.max_items:])

    def clear(self):
        _write_lines(self.path, [])


def select_new(urls, sent):
    """Sisakan link yang belum pernah terkirim dan belum kembar di daftar ini.

    Hasil crawl sudah unik per run, tapi antrean bisa memuat link yang muncul
    lagi di run sekarang, dan dua mesin pencari menulis alamat yang sama dengan
    cara berbeda — perbandingannya memakai dedup_key, bukan string mentah.
    """
    out, seen = [], set()
    for url in urls:
        key = dedup_key(url)
        if key in sent.keys or key in seen:
            continue
        seen.add(key)
        out.append(url)
    return out
