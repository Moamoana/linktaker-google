"""Pemetaan --geo: kode negara, nama negara, dan saran saat salah ketik."""

import pytest

from linktaker import geo


def test_kode_dan_nama_menghasilkan_negara_yang_sama():
    assert geo.resolve("my").code == geo.resolve("malaysia").code == "my"


def test_negara_membawa_bahasa_pencariannya():
    assert geo.resolve("my").language == "ms"


def test_penulisan_bebas_huruf_besar_kecil_dan_spasi():
    assert geo.resolve("  MALAYSIA  ").code == "my"


def test_negara_tak_dikenal_ditolak():
    with pytest.raises(Exception):
        geo.resolve("wakanda")


def test_salah_ketik_mendapat_saran():
    assert "Malaysia" in geo.suggest("malaysa")
