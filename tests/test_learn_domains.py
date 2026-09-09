"""Memungut penerbit baru saat crawl dan menuliskannya ke allowlist."""

from datetime import date

import pytest

from linktaker import news_filter
from linktaker.inputs import append_news_domains, normalise_domain, read_news_domains
from linktaker.url_utils import is_valid_result_url

# cli.py menarik pustaka crawl (curl_cffi, playwright), yang sengaja tidak
# dituntut oleh test suite ini. Di mesin tanpa pustaka itu, hanya bagian CLI
# yang dilewati — logika filter dan penulisan file tetap diuji.
try:
    from linktaker.cli import build_parser, parse_args, save_learned_domains
    CLI_TERSEDIA = True
except ImportError:
    CLI_TERSEDIA = False

butuh_cli = pytest.mark.skipif(not CLI_TERSEDIA,
                               reason="cli.py butuh dependency crawl")

ARTIKEL_BARU = "https://portalbaru.co.id/2026/08/12/judul-berita-yang-panjang"
ARTIKEL_TERDAFTAR = "https://detik.com/news/d-123456/judul-berita-yang-panjang"


@pytest.fixture(autouse=True)
def gate_bersih():
    """Setiap tes memasang gate-nya sendiri, dan mengembalikannya setelah selesai."""
    yield
    news_filter.configure("smart")


def test_host_di_luar_allowlist_dicatat():
    news_filter.configure("smart", {"detik.com"})

    assert is_valid_result_url(ARTIKEL_BARU)

    assert news_filter.learned.domains() == ["portalbaru.co.id"]


def test_host_yang_sudah_terdaftar_tidak_dicatat():
    news_filter.configure("smart", {"detik.com"})

    assert is_valid_result_url(ARTIKEL_TERDAFTAR)

    assert news_filter.learned.domains() == []


def test_subdomain_dicatat_sebagai_domain_utamanya():
    news_filter.configure("smart", set())

    is_valid_result_url("https://surabaya.portalbaru.co.id/2026/08/12/judul-berita-panjang")

    assert news_filter.learned.domains() == ["portalbaru.co.id"]


def test_yang_ditolak_gate_tidak_ikut_dicatat():
    news_filter.configure("smart", set())

    assert not is_valid_result_url("https://wikipedia.org/wiki/Korupsi")
    assert not is_valid_result_url("https://kpk.go.id/2026/08/12/judul-berita-panjang")

    assert news_filter.learned.domains() == []


def test_mode_strict_dan_off_tidak_memungut_apa_pun():
    """Di strict tidak ada host baru yang lolos; di off tidak ada penilaian."""
    for mode in ("strict", "off"):
        news_filter.configure(mode, {"detik.com"})
        is_valid_result_url(ARTIKEL_BARU)
        assert news_filter.learned.domains() == [], mode


def test_ambang_min_hits_menyaring_domain_yang_cuma_lewat_sekali():
    news_filter.configure("smart", set())

    is_valid_result_url("https://sering.co.id/2026/08/12/judul-berita-satu")
    is_valid_result_url("https://sering.co.id/2026/08/13/judul-berita-dua")
    is_valid_result_url("https://sekali.co.id/2026/08/12/judul-berita-tiga")

    assert news_filter.learned.domains(min_hits=2) == ["sering.co.id"]


def test_configure_mengosongkan_catatan_run_sebelumnya():
    news_filter.configure("smart", set())
    is_valid_result_url(ARTIKEL_BARU)

    news_filter.configure("smart", set())

    assert news_filter.learned.domains() == []


# --- menulis ke file ------------------------------------------------------

def test_append_menambahkan_di_bawah_komentar_bertanggal(tmp_path):
    berkas = tmp_path / "news_domains.txt"
    berkas.write_text("detik.com\ntempo.co\n", encoding="utf-8")

    ditulis = append_news_domains(
        ["portalbaru.co.id"], str(berkas), today=date(2026, 9, 9))

    assert ditulis == ["portalbaru.co.id"]
    isi = berkas.read_text(encoding="utf-8")
    assert "# ditemukan otomatis saat crawl 2026-09-09" in isi
    assert isi.endswith("portalbaru.co.id\n")
    assert read_news_domains(str(berkas)) == {
        "detik.com", "tempo.co", "portalbaru.co.id"}


def test_append_melewati_yang_sudah_ada(tmp_path):
    berkas = tmp_path / "news_domains.txt"
    berkas.write_text("detik.com\nwww.tempo.co\n", encoding="utf-8")

    ditulis = append_news_domains(
        ["detik.com", "https://tempo.co/rubrik", "portalbaru.co.id"], str(berkas))

    assert ditulis == ["portalbaru.co.id"]


def test_append_dua_kali_tidak_menghasilkan_baris_ganda(tmp_path):
    berkas = tmp_path / "news_domains.txt"
    berkas.write_text("detik.com\n", encoding="utf-8")

    append_news_domains(["portalbaru.co.id"], str(berkas))
    kedua = append_news_domains(["portalbaru.co.id"], str(berkas))

    assert kedua == []
    assert berkas.read_text(encoding="utf-8").count("portalbaru.co.id") == 1


def test_append_pada_file_tanpa_newline_terakhir(tmp_path):
    berkas = tmp_path / "news_domains.txt"
    berkas.write_text("detik.com", encoding="utf-8")

    append_news_domains(["portalbaru.co.id"], str(berkas))

    assert read_news_domains(str(berkas)) == {"detik.com", "portalbaru.co.id"}


def test_append_tanpa_domain_baru_tidak_menyentuh_file(tmp_path):
    berkas = tmp_path / "news_domains.txt"
    isi = "detik.com\n"
    berkas.write_text(isi, encoding="utf-8")

    assert append_news_domains([], str(berkas)) == []
    assert berkas.read_text(encoding="utf-8") == isi


def test_normalise_domain():
    assert normalise_domain("https://www.Tempo.co/rubrik/x") == "tempo.co"
    assert normalise_domain("*.tribunnews.com") == "tribunnews.com"
    assert normalise_domain("detik.com:443") == "detik.com"
    assert normalise_domain("# catatan") == ""
    assert normalise_domain("   ") == ""


@butuh_cli
def test_save_learned_domains_menulis_hasil_run(tmp_path):
    berkas = tmp_path / "news_domains.txt"
    berkas.write_text("detik.com\n", encoding="utf-8")
    news_filter.configure("smart", {"detik.com"})
    is_valid_result_url(ARTIKEL_BARU)
    is_valid_result_url(ARTIKEL_TERDAFTAR)

    ditulis = save_learned_domains(str(berkas))

    assert ditulis == ["portalbaru.co.id"]
    assert read_news_domains(str(berkas)) == {"detik.com", "portalbaru.co.id"}


# --- flag CLI -------------------------------------------------------------

@butuh_cli
def test_flag_learn_domains_mati_secara_default():
    args = parse_args(["--input", "data/keywords.txt"])

    assert args.learn_domains is False


@butuh_cli
def test_flag_learn_domains_bisa_dinyalakan_dan_dimatikan():
    assert parse_args(["--learn-domains"]).learn_domains is True
    assert parse_args(["--learn-domains", "--no-learn-domains"]).learn_domains is False


@butuh_cli
def test_learn_domains_ditolak_di_luar_mode_smart(tmp_path, capsys):
    # Allowlist sendiri, supaya `strict` tidak lebih dulu gagal karena file
    # bawaan project kebetulan kosong di mesin yang menjalankan tes.
    berkas = tmp_path / "news_domains.txt"
    berkas.write_text("detik.com\n", encoding="utf-8")

    for mode in ("strict", "off"):
        with pytest.raises(SystemExit):
            parse_args(["--learn-domains", "--news-filter", mode,
                        "--news-domains", str(berkas)])
        assert "--news-filter smart" in capsys.readouterr().err


@butuh_cli
def test_learn_min_harus_positif():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--learn-min", "0"])
