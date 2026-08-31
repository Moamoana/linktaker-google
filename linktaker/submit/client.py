"""Yang bicara ke jaringan: satu POST per batch, retry, dan pecah-ulang.

`Poster` mengurus satu batch (termasuk retry-nya), `Submitter` mengurus seluruh
daftar link (memecah jadi batch, memutuskan mana yang diantrekan dan mana yang
dibuang). Keduanya terpisah supaya `Submitter` bisa diuji tanpa jaringan: yang
disuntikkan cukup sebuah fungsi post palsu — lihat tests/test_submit_client.py.
"""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# Hasil satu batch, dan apa artinya bagi link di dalamnya:
OK = "ok"              # diterima server
RETRY = "retry"        # jaringan/5xx — antrekan, coba lagi run berikutnya
REJECT = "reject"      # 4xx — diulang pun sama saja


@dataclass
class Result:
    sent: int = 0
    dropped: int = 0
    queued: list = field(default_factory=list)
    requests: int = 0

    @property
    def ok(self) -> bool:
        return not self.queued and not self.dropped


class Poster:
    """Mengirim satu batch, dengan retry dan jeda yang menaik."""

    def __init__(self, settings, opener=None, sleep=time.sleep, log=print):
        self.settings = settings
        self.opener = opener or urllib.request.urlopen
        self.sleep = sleep
        self.log = log

    def __call__(self, links):
        body = json.dumps({"links": links}).encode("utf-8")
        request = urllib.request.Request(
            self.settings.url, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )

        delay = 2.0
        for attempt in range(1, self.settings.retries + 1):
            try:
                with self.opener(request, timeout=self.settings.timeout) as resp:
                    resp.read(2000)
                    return OK
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read(300).decode("utf-8", "replace").strip()
                except Exception:
                    pass
                # 4xx selain 429 tidak akan berubah kalau diulang persis sama.
                # Yang bisa berubah adalah ukurannya — itu urusan Submitter.
                if 400 <= e.code < 500 and e.code != 429:
                    self.log("  ditolak HTTP %s: %s" % (e.code, detail))
                    return REJECT
                self.log("  percobaan %d/%d gagal: HTTP %s %s"
                         % (attempt, self.settings.retries, e.code, detail))
            except Exception as e:
                self.log("  percobaan %d/%d gagal: %s"
                         % (attempt, self.settings.retries, e))

            if attempt < self.settings.retries:
                self.sleep(delay)
                delay *= 2

        return RETRY


class Submitter:
    """Mengirim seluruh daftar link, memutuskan nasib batch yang gagal."""

    def __init__(self, settings, post=None, log=print, on_sent=None):
        self.settings = settings
        self.post = post or Poster(settings, log=log)
        self.log = log
        # Dipanggil untuk tiap batch yang diterima server, sebelum batch
        # berikutnya dikirim — cli.py memakainya mencatat ke SentLog, jadi
        # kegagalan di tengah jalan tidak menghapus jejak yang sudah terkirim.
        self.on_sent = on_sent or (lambda batch: None)

    def send(self, links) -> Result:
        result = Result()
        size = max(1, self.settings.batch_size)
        pending = [links[i:i + size] for i in range(0, len(links), size)]
        total = len(pending)
        # Satu link yang ditolak sendirian membuktikan yang salah bukan ukuran
        # batch, melainkan endpoint atau formatnya. Sejak itu memecah apa pun
        # lagi hanya membombardir server dengan kegagalan yang sama.
        single_rejected = False
        n = 0

        while pending:
            batch = pending.pop(0)

            # Setelah satu batch gagal karena jaringan, sisanya tidak perlu
            # ikut menunggu timeout satu per satu: server yang mati akan tetap
            # mati 30 detik lagi.
            if result.queued or single_rejected:
                if single_rejected:
                    result.dropped += len(batch)
                else:
                    result.queued.extend(batch)
                continue

            n += 1
            self.log("batch %d/%d (%d link) -> %s"
                     % (n, total, len(batch), self.settings.url))
            result.requests += 1
            status = self.post(batch)

            if status == OK:
                result.sent += len(batch)
                self.on_sent(batch)
            elif status == RETRY:
                result.queued.extend(batch)
            elif len(batch) > 1:
                # Penolakan 4xx pada batch berisi banyak link biasanya soal
                # ukuran — endpoint ini menolak batch di atas 100 URL. Dipecah
                # dua lalu dicoba lagi, jadi batas sisi server yang berubah
                # sewaktu-waktu tidak pernah berujung pada link yang dibuang.
                half = len(batch) // 2
                self.log("  dipecah jadi %d + %d link, lalu dicoba lagi"
                         % (half, len(batch) - half))
                pending[:0] = [batch[:half], batch[half:]]
                total += 1
            else:
                self.log("  dibuang: %s" % batch[0])
                result.dropped += 1
                single_rejected = True

        return result
