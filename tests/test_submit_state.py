"""Riwayat kirim, antrean, dan penyaringan duplikat."""

from datetime import datetime, timedelta

from linktaker.submit.state import PendingQueue, SentLog, read_url_file, select_new


def test_read_url_file_membuang_komentar_dan_baris_kosong(tmp_path):
    f = tmp_path / "hasil.txt"
    f.write_text("# catatan\n\nhttps://contoh.id/a\n  https://contoh.id/b  \nbukan-url\n",
                 encoding="utf-8")

    assert read_url_file(str(f)) == ["https://contoh.id/a", "https://contoh.id/b"]


def test_file_yang_tidak_ada_bukan_error():
    assert read_url_file("tidak/ada.txt") == []


def test_link_yang_sudah_terkirim_tidak_dikirim_lagi(tmp_path):
    log = SentLog(str(tmp_path / "sent.txt"), keep_days=30)
    log.load()
    log.add(["https://contoh.id/berita/satu"])
    log.save()

    lagi = SentLog(str(tmp_path / "sent.txt"), keep_days=30).load()
    assert "https://contoh.id/berita/satu" in lagi


def test_beda_penulisan_alamat_dihitung_sama(tmp_path):
    """http/https, www., dan garis miring di ujung bukan berita yang berbeda."""
    log = SentLog(str(tmp_path / "sent.txt"), keep_days=30).load()
    log.add(["https://www.contoh.id/berita/satu/"])

    sisa = select_new([
        "http://contoh.id/berita/satu",       # sama, beda skema dan www
        "https://contoh.id/berita/satu",      # sama
        "https://contoh.id/berita/dua",       # baru
    ], log)

    assert sisa == ["https://contoh.id/berita/dua"]


def test_duplikat_di_dalam_satu_kiriman_ikut_disaring(tmp_path):
    log = SentLog(str(tmp_path / "sent.txt"), keep_days=30).load()

    sisa = select_new(["https://contoh.id/a", "https://www.contoh.id/a/",
                       "https://contoh.id/b"], log)

    assert sisa == ["https://contoh.id/a", "https://contoh.id/b"]


def test_riwayat_kedaluwarsa_dibuang(tmp_path):
    path = tmp_path / "sent.txt"
    lama = (datetime.now() - timedelta(days=40)).isoformat(timespec="seconds")
    baru = datetime.now().isoformat(timespec="seconds")
    path.write_text("%s\t//contoh.id/lama\n%s\t//contoh.id/baru\n" % (lama, baru),
                    encoding="utf-8")

    log = SentLog(str(path), keep_days=30).load()

    assert "https://contoh.id/baru" in log
    assert "https://contoh.id/lama" not in log


def test_baris_riwayat_dengan_tanggal_rusak_tetap_dipegang(tmp_path):
    """Lebih baik menahan satu link daripada mengirim ulang seluruh riwayat."""
    path = tmp_path / "sent.txt"
    path.write_text("bukan-tanggal\t//contoh.id/a\n", encoding="utf-8")

    assert "https://contoh.id/a" in SentLog(str(path), keep_days=30).load()


def test_antrean_dipotong_di_batas_maksimum(tmp_path):
    queue = PendingQueue(str(tmp_path / "pending.txt"), max_items=3)
    queue.save(["https://contoh.id/%d" % i for i in range(10)])

    tersimpan = queue.load()
    assert tersimpan == ["https://contoh.id/7", "https://contoh.id/8", "https://contoh.id/9"]


def test_penulisan_state_tidak_meninggalkan_file_sementara(tmp_path):
    queue = PendingQueue(str(tmp_path / "pending.txt"), max_items=100)
    queue.save(["https://contoh.id/a"])

    assert [p.name for p in tmp_path.iterdir()] == ["pending.txt"]
