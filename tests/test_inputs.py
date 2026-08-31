"""Pembacaan input: tanggal relatif, keyword, allowlist penerbit."""

from datetime import date

import pytest

from linktaker.inputs import parse_date, read_keywords, read_news_domains, resolve_data_path

HARI_INI = date(2026, 8, 31)


@pytest.mark.parametrize("nilai, harapan", [
    ("2026-08-18", date(2026, 8, 18)),
    ("today", HARI_INI),
    ("yesterday", date(2026, 8, 30)),
    ("1d", date(2026, 8, 30)),
    ("7d", date(2026, 8, 24)),
    ("w", date(2026, 8, 24)),          # satuan telanjang berarti satu
    ("2w", date(2026, 8, 17)),
    ("3m", date(2026, 5, 31)),
    ("1y", date(2025, 8, 31)),
])
def test_tanggal_relatif_dihitung_dari_hari_ini(nilai, harapan):
    assert parse_date(nilai, "--from", today=HARI_INI) == harapan


def test_tanggal_ngawur_ditolak_dengan_jelas():
    with pytest.raises(ValueError):
        parse_date("kemarin lusa", "--from", today=HARI_INI)


def test_keyword_dibaca_tanpa_komentar_dan_duplikat(tmp_path):
    f = tmp_path / "keywords.txt"
    f.write_text("# daftar\n\nkarhutla\nKARHUTLA\nbanjir\n", encoding="utf-8")

    assert read_keywords(str(f)) == ["karhutla", "banjir"]


def test_format_lama_dengan_pipe_masih_terbaca(tmp_path):
    f = tmp_path / "keywords.txt"
    f.write_text("karhutla | 2026-08-01 | nws\n", encoding="utf-8")

    assert read_keywords(str(f)) == ["karhutla"]


def test_allowlist_penerbit_dinormalkan(tmp_path):
    f = tmp_path / "news_domains.txt"
    f.write_text("# penerbit\ntribunnews.com\nwww.detik.com\nhttps://tempo.co/\n",
                 encoding="utf-8")

    assert read_news_domains(str(f)) == {"tribunnews.com", "detik.com", "tempo.co"}


def test_file_lama_di_root_masih_dipakai_selama_masa_pindahan(tmp_path, monkeypatch):
    """Mesin yang sudah jalan belum tentu sempat memindahkan file ke data/;
    run terjadwal tidak boleh mati karenanya."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "keywords.txt").write_text("karhutla\n", encoding="utf-8")

    assert resolve_data_path("data/keywords.txt") == "keywords.txt"
    assert read_keywords("data/keywords.txt") == ["karhutla"]


def test_file_di_data_lebih_diutamakan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "keywords.txt").write_text("lama\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "keywords.txt").write_text("baru\n", encoding="utf-8")

    assert read_keywords("data/keywords.txt") == ["baru"]
