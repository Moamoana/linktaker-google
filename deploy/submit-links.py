#!/usr/bin/env python3
"""Shim — isinya sudah pindah ke paket `linktaker.submit`.

Tetap ada supaya perintah lama yang terlanjur tertulis di catatan, cron, atau
riwayat shell tidak mati begitu saja. Yang baru:

    python -m linktaker.submit data/hasil/links-all-20260831-1100.txt
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from linktaker.submit.cli import main  # noqa: E402

if __name__ == "__main__":
    print("catatan: deploy/submit-links.py sekarang cuma pembungkus — "
          "pakai `python -m linktaker.submit`", file=sys.stderr)
    sys.exit(main())
