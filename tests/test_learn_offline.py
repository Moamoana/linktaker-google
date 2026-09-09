"""Memanen penerbit dari file hasil yang sudah ada (`python -m linktaker.learn`)."""

import pytest

from linktaker import news_filter
from linktaker.inputs import read_news_domains
from linktaker.learn import baca_url, main, pungut

HASIL = """\
# hasil crawl kemarin
https://detik.com/news/d-123456/judul-berita-yang-panjang
https://portalbaru.co.id/2026/08/12/judul-berita-yang-panjang
https://portalbaru.co.id/2026/08/13/judul-berita-yang-lain

https://sekali.co.id/2026/08/12/judul-berita-sekali-lewat
https://wikipedia.org/wiki/Korupsi
https://twitter.com/akun/status/1
https://blog.contoh.id/2026/08/judul-berita.html
"""


@pytest.fixture(autouse=True)
def gate_bersih():
    yield
    news_filter.configure("smart")


@pytest.fixture
def hasil(tmp_path):
    berkas = tmp_path / "hasil.txt"
    berkas.write_text(HASIL, encoding="utf-8")
    return berkas


@pytest.fixture
def allowlist(tmp_path):
    berkas = tmp_path / "news_domains.txt"
    berkas.write_text("detik.com\n", encoding="utf-8")
    return berkas


def test_baca_url_melewati_komentar_dan_baris_kosong(hasil):
    urls = list(baca_url(str(hasil)))

    assert len(urls) == 7
    assert not any(u.startswith("#") for u in urls)


def test_pungut_hanya_domain_yang_lolos_gate(hasil):
    diperiksa, catatan = pungut([str(hasil)], {"detik.com"})

    assert diperiksa == 7
    # detik.com sudah terdaftar; wikipedia, twitter dan URL .html ditolak gate.
    assert catatan.domains() == ["portalbaru.co.id", "sekali.co.id"]
    assert catatan.by_domain["portalbaru.co.id"] == 2


def test_ambang_min_menyaring_yang_cuma_lewat_sekali(hasil):
    _, catatan = pungut([str(hasil)], {"detik.com"})

    assert catatan.domains(min_hits=2) == ["portalbaru.co.id"]


def test_tanpa_write_file_allowlist_tidak_disentuh(hasil, allowlist, capsys):
    isi_awal = allowlist.read_text(encoding="utf-8")

    kode = main([str(hasil), "--news-domains", str(allowlist)])

    assert kode == 0
    assert allowlist.read_text(encoding="utf-8") == isi_awal
    assert "--write" in capsys.readouterr().out


def test_write_menambahkan_ke_allowlist(hasil, allowlist):
    kode = main([str(hasil), "--news-domains", str(allowlist), "--write"])

    assert kode == 0
    assert read_news_domains(str(allowlist)) == {
        "detik.com", "portalbaru.co.id", "sekali.co.id"}


def test_write_menghormati_ambang_min(hasil, allowlist):
    main([str(hasil), "--news-domains", str(allowlist), "--min", "2", "--write"])

    assert read_news_domains(str(allowlist)) == {"detik.com", "portalbaru.co.id"}


def test_write_dua_kali_tidak_menghasilkan_baris_ganda(hasil, allowlist):
    main([str(hasil), "--news-domains", str(allowlist), "--write"])
    main([str(hasil), "--news-domains", str(allowlist), "--write"])

    isi = allowlist.read_text(encoding="utf-8")
    assert isi.count("portalbaru.co.id") == 1


def test_beberapa_file_sekaligus(tmp_path, allowlist):
    satu = tmp_path / "satu.txt"
    dua = tmp_path / "dua.txt"
    satu.write_text("https://a-portal.co.id/2026/08/12/judul-berita-panjang\n",
                    encoding="utf-8")
    dua.write_text("https://b-portal.co.id/2026/08/12/judul-berita-panjang\n",
                   encoding="utf-8")

    main([str(satu), str(dua), "--news-domains", str(allowlist), "--write"])

    assert read_news_domains(str(allowlist)) == {
        "detik.com", "a-portal.co.id", "b-portal.co.id"}


def test_file_yang_tidak_ada_dilewati_bukan_menggagalkan(hasil, allowlist, capsys):
    kode = main([str(hasil), str(hasil.parent / "tidak-ada.txt"),
                 "--news-domains", str(allowlist)])

    assert kode == 0
    assert "tidak ditemukan" in capsys.readouterr().out


def test_semua_file_hilang_berakhir_dengan_kode_gagal(tmp_path, allowlist):
    assert main([str(tmp_path / "tidak-ada.txt"),
                 "--news-domains", str(allowlist)]) == 2


def test_min_nol_ditolak(hasil, allowlist):
    assert main([str(hasil), "--news-domains", str(allowlist), "--min", "0"]) == 2
