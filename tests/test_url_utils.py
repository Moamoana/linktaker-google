"""Pembersihan dan penilaian URL hasil pencarian."""

from linktaker.url_utils import dedup_key, is_social_media, is_valid_result_url, strip_amp


def test_dedup_key_menyamakan_penulisan_yang_berbeda():
    sama = [
        "https://www.contoh.id/berita/satu",
        "http://contoh.id/berita/satu/",
        "https://contoh.id/berita/satu#bagian",
        "  https://WWW.Contoh.id/berita/satu  ",
    ]

    assert len({dedup_key(u) for u in sama}) == 1


def test_dedup_key_membedakan_berita_yang_berbeda():
    assert dedup_key("https://contoh.id/a") != dedup_key("https://contoh.id/b")


def test_dedup_key_mempertahankan_query():
    """Banyak portal lama menaruh id artikel di query, bukan di path."""
    assert dedup_key("https://contoh.id/baca?id=12") != dedup_key("https://contoh.id/baca?id=13")


def test_strip_amp_mengembalikan_alamat_asli():
    bersih = strip_amp("https://amp.contoh.id/berita/satu/amp/?amp=1&x=2")

    assert bersih.startswith("https://contoh.id/berita/satu")
    assert "amp" not in bersih.split("://")[1].split("/")[0]


def test_media_sosial_dikenali():
    assert is_social_media("https://www.facebook.com/halaman")
    assert is_social_media("https://m.youtube.com/watch?v=x")
    assert not is_social_media("https://detik.com/berita")


def test_url_hasil_pencarian_yang_layak():
    assert is_valid_result_url("https://detik.com/news/d-123456/judul-berita-yang-panjang")


def test_media_sosial_bukan_hasil_yang_layak():
    assert not is_valid_result_url("https://twitter.com/akun/status/1")
    assert not is_valid_result_url("")
