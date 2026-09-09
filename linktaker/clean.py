"""Membuang URL berakhiran `.html` dari file hasil yang sudah tertulis.

Gate saat crawl (`url_utils.ends_with_html`) menjaga file baru tetap bersih.
Modul ini untuk file yang terlanjur berisi link seperti itu:

    python -m linktaker.clean data/hasil/kpk-agustus-2026.txt
    python -m linktaker.clean data/hasil/*.txt --dry-run
    python -m linktaker.clean data/hasil/hasil.txt -o data/hasil/bersih.txt

Default menulis ulang file di tempat, dengan salinan `<file>.bak` di sebelahnya
supaya satu perintah yang salah sasaran masih bisa dikembalikan; `--no-backup`
mematikan salinan itu. `--dry-run` hanya menghitung, tidak menyentuh apa pun.

Baris kosong dan baris komentar (`#`) dibiarkan apa adanya — yang dinilai hanya
baris yang berisi URL, dan isinya ditulis ulang persis seperti aslinya.
"""

import argparse
import os
import shutil
import sys
from collections import namedtuple

from .url_utils import ends_with_html

Hasil = namedtuple("Hasil", "path disimpan dibuang ditulis")


def _is_url_line(line: str) -> bool:
    """Baris yang perlu dinilai: bukan kosong, bukan komentar."""
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def pisahkan_baris(lines):
    """Pecah kumpulan baris jadi (yang disimpan, yang dibuang).

    Urutan baris yang disimpan tidak berubah, termasuk baris kosong dan
    komentar di antaranya.
    """
    disimpan, dibuang = [], []
    for line in lines:
        raw = line.rstrip("\n").rstrip("\r")
        if _is_url_line(raw) and ends_with_html(raw.strip()):
            dibuang.append(raw.strip())
        else:
            disimpan.append(raw)
    return disimpan, dibuang


def bersihkan_file(path, output=None, backup=True, dry_run=False) -> Hasil:
    """Tulis ulang `path` tanpa URL `.html`.

    output   tulis hasilnya ke file lain, biarkan yang asli utuh
    backup   simpan `<path>.bak` sebelum menimpa file aslinya
    dry_run  hitung saja, tidak ada file yang ditulis

    File hanya ditulis kalau memang ada yang dibuang, jadi menjalankan ini dua
    kali tidak membuat cadangan kedua yang menimpa cadangan pertama.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    disimpan, dibuang = pisahkan_baris(lines)
    tujuan = output or path

    if dry_run or (not dibuang and tujuan == path):
        return Hasil(path, len(disimpan), len(dibuang), None)

    if backup and tujuan == path:
        shutil.copy2(path, path + ".bak")

    with open(tujuan, "w", encoding="utf-8", newline="\n") as f:
        for baris in disimpan:
            f.write(baris + "\n")

    return Hasil(path, len(disimpan), len(dibuang), tujuan)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m linktaker.clean",
        description="Buang URL yang berakhiran .html dari file hasil crawl.",
    )
    parser.add_argument("files", nargs="+", help="file hasil yang mau dibersihkan")
    parser.add_argument(
        "-o", "--output",
        help="tulis hasilnya ke file ini alih-alih menimpa yang asli "
             "(hanya untuk satu file input)",
    )
    parser.add_argument(
        "--no-backup", action="store_true",
        help="jangan simpan salinan <file>.bak sebelum menimpa",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="hitung saja, jangan menulis apa pun",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="tampilkan URL yang dibuang, bukan hanya jumlahnya",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.output and len(args.files) > 1:
        print("[!] --output hanya bisa dipakai untuk satu file input")
        return 2

    total_dibuang = 0
    for path in args.files:
        if not os.path.exists(path):
            print(f"[!] {path} tidak ditemukan — dilewati")
            continue

        hasil = bersihkan_file(
            path,
            output=args.output,
            backup=not args.no_backup,
            dry_run=args.dry_run,
        )
        total_dibuang += hasil.dibuang

        if args.list:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for url in pisahkan_baris(f.readlines())[1]:
                    print("  - " + url)

        if args.dry_run:
            print(f"{path}: {hasil.dibuang} URL .html akan dibuang, "
                  f"{hasil.disimpan} baris tersisa (dry-run)")
        elif hasil.ditulis is None:
            print(f"{path}: tidak ada URL .html — file tidak disentuh")
        else:
            catatan = "" if args.no_backup or args.output else f", cadangan di {path}.bak"
            print(f"{path}: {hasil.dibuang} URL .html dibuang, "
                  f"{hasil.disimpan} baris ditulis ke {hasil.ditulis}{catatan}")

    return 0 if total_dibuang or args.dry_run else 0


if __name__ == "__main__":
    sys.exit(main())
