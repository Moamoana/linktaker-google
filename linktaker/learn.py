"""Memanen penerbit baru dari file hasil yang sudah ada, tanpa crawl ulang.

`--learn-domains` memungut domain sambil crawl berjalan. Modul ini melakukan hal
yang sama terhadap file hasil yang sudah tergeletak di `data/hasil/` — dan untuk
menumbuhkan allowlist, ini jalan yang lebih masuk akal:

  * selesai dalam hitungan detik, bukan menunggu satu crawl penuh
  * tidak membuka browser, jadi tidak ada CAPTCHA dan tidak ada risiko diblokir
  * bisa diulang berkali-kali dengan ambang berbeda atas data yang sama
  * bisa dijalankan atas hasil lama, termasuk yang dikumpulkan bulan lalu

    python -m linktaker.learn data/hasil/*.txt                  # laporan saja
    python -m linktaker.learn data/hasil/*.txt --min 5          # ambang 5 link
    python -m linktaker.learn data/hasil/*.txt --min 5 --write  # tulis ke allowlist

Default-nya hanya melapor. `--write` yang benar-benar menyentuh file allowlist,
dan tulisannya masuk di bawah komentar bertanggal seperti `--learn-domains`.

Setiap URL dilewatkan gerbang yang sama persis dengan yang dipakai saat crawl
(`url_utils.is_valid_result_url` di mode `smart`), jadi yang terpungut di sini
sama dengan yang akan terpungut saat crawl — termasuk aturan bahwa URL media
sosial dan URL berakhiran `.html` tidak pernah ikut.

Hanya memakai pustaka standar Python: menjalankan ini tidak menuntut Playwright
dan kawan-kawan ikut terpasang.
"""

import argparse
import os
import sys

from . import news_filter
from .config import NEWS_DOMAINS_FILE
from .inputs import append_news_domains, read_news_domains
from .url_utils import is_valid_result_url


def baca_url(path):
    """URL per baris dari satu file hasil; baris kosong dan komentar dilewati."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            url = line.strip()
            if url and not url.startswith("#"):
                yield url


def pungut(paths, allowlist):
    """Lewatkan seluruh URL di `paths` ke gerbang berita, kembalikan (jumlah, catatan).

    Catatannya adalah `news_filter.learned` yang sama dengan yang diisi saat
    crawl, jadi ambang `--min` dan penulisan file-nya berbagi kode yang sama.
    """
    news_filter.configure("smart", allowlist)

    diperiksa = 0
    for path in paths:
        for url in baca_url(path):
            diperiksa += 1
            is_valid_result_url(url)

    return diperiksa, news_filter.learned


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m linktaker.learn",
        description="Panen penerbit yang belum terdaftar dari file hasil crawl.",
    )
    parser.add_argument("files", nargs="+", help="file hasil yang mau dibaca")
    parser.add_argument(
        "--news-domains", "--news_domains", dest="news_domains",
        metavar="FILE", default=NEWS_DOMAINS_FILE,
        help=f"file allowlist yang dibandingkan dan ditulis "
             f"(default: {NEWS_DOMAINS_FILE})",
    )
    parser.add_argument(
        "--min", dest="min_hits", type=int, default=1, metavar="N",
        help="berapa kali sebuah domain harus muncul sebelum dihitung baru "
             "(default: 1)",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="tulis hasilnya ke file allowlist; tanpa ini hanya melapor",
    )
    parser.add_argument(
        "--limit", type=int, default=30, metavar="N",
        help="berapa domain yang ditampilkan di laporan (default: 30)",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.min_hits < 1:
        print("[!] --min minimal 1")
        return 2

    ada = [p for p in args.files if os.path.exists(p)]
    for hilang in (p for p in args.files if p not in ada):
        print(f"[!] {hilang} tidak ditemukan — dilewati")
    if not ada:
        print("[!] tidak ada file yang bisa dibaca")
        return 2

    allowlist = read_news_domains(args.news_domains)
    diperiksa, catatan = pungut(ada, allowlist)

    print(f"{diperiksa} URL dari {len(ada)} file, dibandingkan dengan "
          f"{len(allowlist)} domain di {args.news_domains}")

    kandidat = catatan.domains(args.min_hits)
    if not kandidat:
        print(f"Tidak ada domain baru dengan ambang {args.min_hits} link "
              f"({len(catatan.by_domain)} host di luar allowlist).")
        return 0

    print(f"Domain di luar allowlist: {len(catatan.by_domain)} host, "
          f"{len(kandidat)} di antaranya mencapai {args.min_hits} link")

    # Yang ramai dulu, lalu abjad supaya urutannya sama tiap dijalankan.
    peringkat = sorted(((catatan.by_domain[d], d) for d in kandidat),
                       key=lambda pasangan: (-pasangan[0], pasangan[1]))
    for jumlah, domain in peringkat[:args.limit]:
        print(f"  {jumlah:>5}  {domain}")
    sisa = len(peringkat) - len(peringkat[:args.limit])
    if sisa > 0:
        print(f"  ... dan {sisa} domain lagi")

    if not args.write:
        print(f"\nLaporan saja — tambahkan --write untuk menuliskannya ke "
              f"{args.news_domains}.")
        return 0

    try:
        ditulis = append_news_domains(kandidat, args.news_domains)
    except OSError as e:
        print(f"[!] gagal menulis {args.news_domains}: {e}")
        return 1

    if ditulis:
        print(f"\n{len(ditulis)} domain ditambahkan ke {args.news_domains}. "
              f"Tinjau blok bertanggal di akhir file sebelum di-commit.")
    else:
        print(f"\nSemua kandidat ternyata sudah ada di {args.news_domains}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
