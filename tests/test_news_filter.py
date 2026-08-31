"""Penyaring berita: mana yang artikel, mana yang halaman indeks atau bukan berita."""

import pytest

from linktaker.news_filter import is_news_url, looks_like_article, registrable_domain


@pytest.mark.parametrize("host, harapan", [
    ("bandung.kompas.com", "kompas.com"),
    ("babel.antaranews.com", "antaranews.com"),
    ("www.detik.com", "detik.com"),
])
def test_domain_terdaftar_diambil_dari_subdomain(host, harapan):
    assert registrable_domain(host) == harapan


@pytest.mark.parametrize("url", [
    "https://kompas.com/read/2026/08/26/064634278/karhutla-hanguskan-20-hektar",
    "https://detik.com/news/d-123456/petugas-padamkan-karhutla-di-riau",
])
def test_alamat_artikel_dikenali(url):
    assert looks_like_article(url)


@pytest.mark.parametrize("url", [
    "https://kompas.com/tag/karhutla",
    "https://kompas.com/",
    "https://kompas.com/indeks",
])
def test_halaman_indeks_bukan_artikel(url):
    assert not looks_like_article(url)


def test_mode_strict_hanya_menerima_penerbit_di_allowlist():
    allowlist = frozenset({"kompas.com"})
    artikel = "https://kompas.com/read/2026/08/26/064634278/karhutla-hanguskan-20-hektar"
    lain = "https://portalasing.example/read/2026/08/26/12345/berita-kebakaran-hutan"

    assert is_news_url(artikel, "strict", allowlist)
    assert not is_news_url(lain, "strict", allowlist)


def test_mode_off_menerima_apa_saja():
    assert is_news_url("https://kompas.com/tag/karhutla", "off")
