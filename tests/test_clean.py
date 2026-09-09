"""Pembuangan URL berakhiran .html — gate saat crawl dan pembersih file hasil."""

from linktaker.clean import bersihkan_file, pisahkan_baris
from linktaker.url_utils import ends_with_html, is_valid_result_url


def test_url_html_dikenali():
    assert ends_with_html("http://www.carikabar.id/2024/10/enos-resmi-terima.html")
    assert ends_with_html("https://contoh.id/berita.HTML")
    assert ends_with_html("https://contoh.id/berita.html?page=2")
    assert ends_with_html("https://contoh.id/berita.html#isi")


def test_url_bukan_html_dibiarkan():
    assert not ends_with_html("https://detik.com/news/d-123456/judul-berita-yang-panjang")
    assert not ends_with_html("https://contoh.id/berita.htm")
    assert not ends_with_html("https://contoh.id/html/berita-satu-dua-tiga")
    assert not ends_with_html("")


def test_url_html_bukan_hasil_yang_layak():
    """Gate crawl: sekalipun path-nya berbentuk artikel, .html tetap ditolak."""
    assert not is_valid_result_url("https://contoh.id/2026/08/judul-berita-yang-panjang.html")


def test_pisahkan_baris_mempertahankan_yang_lain():
    baris = [
        "# catatan\n",
        "https://detik.com/news/d-123456/judul-berita-panjang\n",
        "http://blog.contoh.id/2026/08/judul-berita.html\n",
        "\n",
        "https://contoh.id/2026/08/12/berita-lain\n",
    ]

    disimpan, dibuang = pisahkan_baris(baris)

    assert dibuang == ["http://blog.contoh.id/2026/08/judul-berita.html"]
    assert disimpan == [
        "# catatan",
        "https://detik.com/news/d-123456/judul-berita-panjang",
        "",
        "https://contoh.id/2026/08/12/berita-lain",
    ]


def test_bersihkan_file_menimpa_dan_menyimpan_cadangan(tmp_path):
    berkas = tmp_path / "hasil.txt"
    berkas.write_text(
        "https://contoh.id/2026/08/12/berita-satu\n"
        "http://blog.contoh.id/2026/08/berita-dua.html\n",
        encoding="utf-8",
    )

    hasil = bersihkan_file(str(berkas))

    assert hasil.dibuang == 1
    assert hasil.disimpan == 1
    assert berkas.read_text(encoding="utf-8") == "https://contoh.id/2026/08/12/berita-satu\n"
    assert (tmp_path / "hasil.txt.bak").exists()


def test_bersihkan_file_tanpa_html_tidak_menyentuh_apa_pun(tmp_path):
    berkas = tmp_path / "hasil.txt"
    isi = "https://contoh.id/2026/08/12/berita-satu\n"
    berkas.write_text(isi, encoding="utf-8")

    hasil = bersihkan_file(str(berkas))

    assert hasil.dibuang == 0
    assert hasil.ditulis is None
    assert not (tmp_path / "hasil.txt.bak").exists()
    assert berkas.read_text(encoding="utf-8") == isi


def test_bersihkan_file_ke_output_lain_membiarkan_aslinya(tmp_path):
    sumber = tmp_path / "hasil.txt"
    isi = (
        "https://contoh.id/2026/08/12/berita-satu\n"
        "http://blog.contoh.id/2026/08/berita-dua.html\n"
    )
    sumber.write_text(isi, encoding="utf-8")
    tujuan = tmp_path / "bersih.txt"

    hasil = bersihkan_file(str(sumber), output=str(tujuan))

    assert hasil.ditulis == str(tujuan)
    assert sumber.read_text(encoding="utf-8") == isi
    assert tujuan.read_text(encoding="utf-8") == "https://contoh.id/2026/08/12/berita-satu\n"


def test_dry_run_tidak_menulis(tmp_path):
    berkas = tmp_path / "hasil.txt"
    isi = "http://blog.contoh.id/2026/08/berita-dua.html\n"
    berkas.write_text(isi, encoding="utf-8")

    hasil = bersihkan_file(str(berkas), dry_run=True)

    assert hasil.dibuang == 1
    assert hasil.ditulis is None
    assert berkas.read_text(encoding="utf-8") == isi
