"""Perilaku pengiriman batch — tanpa menyentuh jaringan.

Yang diuji di sini persis kegagalan yang pernah terjadi di produksi: server
menolak batch 200 link dengan "Batch size cannot exceed 100 URLs", dan seluruh
303 link hari itu dibuang. Sejak itu batch yang ditolak dipecah dua dan dicoba
lagi; test di bawah yang menjaga perilaku tersebut tetap ada.
"""

from linktaker.submit.client import OK, REJECT, RETRY, Submitter
from linktaker.submit.settings import Settings


class FakePost:
    """Endpoint palsu: menerima batch sampai `limit` link, sisanya ditolak."""

    def __init__(self, limit=100, always=None):
        self.limit = limit
        self.always = always          # paksa satu status untuk semua batch
        self.calls = []               # ukuran tiap batch yang masuk
        self.accepted = []            # link yang benar-benar diterima

    def __call__(self, links):
        self.calls.append(len(links))
        if self.always:
            return self.always
        if len(links) <= self.limit:
            self.accepted.extend(links)
            return OK
        return REJECT


def links(n, prefix="https://contoh.id/berita/"):
    return ["%s%d" % (prefix, i) for i in range(n)]


def settings(**kwargs):
    return Settings(url="http://endpoint/submit_batch/", state_dir="state", **kwargs)


def test_batch_dipecah_sesuai_ukuran():
    post = FakePost()
    result = Submitter(settings(batch_size=100), post=post, log=lambda *_: None).send(links(250))

    assert post.calls == [100, 100, 50]
    assert result.sent == 250
    assert result.ok


def test_batch_kebesaran_dipecah_lalu_terkirim_semua():
    """Kasus 31 Agustus: batch 200 ditolak server yang membatasi 100."""
    post = FakePost(limit=100)
    result = Submitter(settings(batch_size=200), post=post, log=lambda *_: None).send(links(200))

    assert result.sent == 200, "tidak boleh ada link yang hilang karena batas ukuran"
    assert result.dropped == 0
    assert sorted(post.accepted) == sorted(links(200))
    assert max(post.calls) == 200 and min(post.calls) <= 100  # ditolak, lalu dipecah


def test_penolakan_menyeluruh_tidak_membombardir_server():
    """Endpoint salah/format salah: berhenti, bukan mengecil sampai satu-satu."""
    post = FakePost(always=REJECT)
    result = Submitter(settings(batch_size=100), post=post, log=lambda *_: None).send(links(20))

    assert result.sent == 0
    assert result.dropped == 20
    assert len(post.calls) <= 6, "seharusnya berhenti setelah satu link pun ditolak"


def test_gagal_jaringan_diantrekan_bukan_dibuang():
    post = FakePost(always=RETRY)
    result = Submitter(settings(batch_size=100), post=post, log=lambda *_: None).send(links(250))

    assert result.sent == 0
    assert result.dropped == 0
    assert len(result.queued) == 250, "semua link harus tersimpan untuk run berikutnya"
    assert len(post.calls) == 1, "batch sesudah kegagalan jaringan tidak perlu dicoba lagi"


def test_batch_yang_sudah_terkirim_dicatat_meski_sisanya_gagal():
    """Server mati di tengah jalan: yang terlanjur terkirim tidak boleh terkirim ulang."""
    catatan = []
    status = [OK, RETRY]

    def post(batch):
        return status.pop(0) if status else RETRY

    result = Submitter(settings(batch_size=100), post=post, log=lambda *_: None,
                       on_sent=catatan.extend).send(links(250))

    assert result.sent == 100
    assert catatan == links(100)
    assert len(result.queued) == 150
