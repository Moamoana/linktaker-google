"""Pengiriman hasil crawl ke endpoint pengumpul (`submit_batch`).

Dipakai otomatis oleh deploy/run-linktaker.sh setelah setiap crawl, dan bisa
dipanggil sendiri:

    python -m linktaker.submit data/hasil/links-all-20260831-1100.txt

Pembagian isinya:

    settings.py  nilai setelan — default dari config.py, ditimpa environment
    state.py     ingatan antar-run: apa yang sudah terkirim, apa yang tertunda
    client.py    yang bicara ke jaringan: batching, retry, pecah-ulang
    cli.py       merangkai ketiganya jadi satu perintah

Hanya memakai pustaka standar Python, jadi menjalankan pengiriman tidak
menuntut dependency crawl (Playwright dan kawan-kawan) ikut terpasang.
"""

from .client import Poster, Result, Submitter
from .settings import Settings
from .state import PendingQueue, SentLog

__all__ = ["PendingQueue", "Poster", "Result", "SentLog", "Settings", "Submitter"]
