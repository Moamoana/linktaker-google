"""Setelan pengiriman: default dari config.py, ditimpa environment variable.

Environment dipakai karena penjadwal (systemd, cron, PM2) hanya bisa
menitipkan setelan lewat sana, dan `deploy/linktaker.env` diisi per mesin
tanpa menyentuh kode.
"""

import os
from dataclasses import dataclass

from .. import config


@dataclass
class Settings:
    url: str = config.SUBMIT_URL
    batch_size: int = config.SUBMIT_BATCH_SIZE
    retries: int = config.SUBMIT_RETRIES
    timeout: float = config.SUBMIT_TIMEOUT
    state_dir: str = config.SUBMIT_STATE_DIR
    keep_days: int = config.SUBMIT_KEEP_DAYS
    queue_max: int = config.SUBMIT_QUEUE_MAX

    @classmethod
    def from_env(cls, env=None):
        """Baca SUBMIT_* dari environment; yang tidak diisi memakai default.

        Nilai kosong diperlakukan sebagai "tidak diisi" — script shell yang
        meneruskan variabel yang belum diset mengirim string kosong, dan
        int("") hanya akan menggagalkan run yang sebenarnya baik-baik saja.
        """
        env = os.environ if env is None else env

        def value(name, cast, default):
            raw = env.get("SUBMIT_" + name, "")
            if not str(raw).strip():
                return default
            try:
                return cast(raw)
            except ValueError:
                return default

        return cls(
            url=value("URL", str, cls.url),
            batch_size=value("BATCH_SIZE", int, cls.batch_size),
            retries=value("RETRIES", int, cls.retries),
            timeout=value("TIMEOUT", float, cls.timeout),
            state_dir=value("STATE_DIR", str, cls.state_dir),
            keep_days=value("KEEP_DAYS", int, cls.keep_days),
            queue_max=value("QUEUE_MAX", int, cls.queue_max),
        )

    @property
    def sent_file(self) -> str:
        return os.path.join(self.state_dir, "sent-urls.txt")

    @property
    def queue_file(self) -> str:
        return os.path.join(self.state_dir, "pending-urls.txt")
