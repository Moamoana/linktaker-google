#!/usr/bin/env bash
# Membungkus deploy/proxy-relay.py: baca UPSTREAM_PROXY (dan RELAY_HOST/PORT)
# dari deploy/linktaker.env supaya kredensial proxy tidak pernah tertulis di
# baris perintah atau di file yang di-track git — sama seperti pola
# deploy/run-linktaker.sh membaca setelannya sendiri.
#
# Lihat deploy/proxy-relay.py untuk kenapa relay ini perlu ada sama sekali:
# proxy yang membalas 407 tanpa header Proxy-Authenticate yang sah membuat
# Chromium selalu gagal (ERR_PROXY_AUTH_UNSUPPORTED) walau kredensialnya benar.
#
# Dipakai lewat deploy/ecosystem.config.js sebagai proses PM2 terpisah yang
# hidup terus, supaya proxy relay ikut naik saat mesin di-reboot.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/linktaker-google}"
ENV_FILE="${ENV_FILE:-$APP_DIR/deploy/linktaker.env}"
if [ -f "$ENV_FILE" ]; then
    # shellcheck source=/dev/null
    . "$ENV_FILE"
fi

PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/.venv/bin/python}"

if [ -z "${UPSTREAM_PROXY:-}" ]; then
    echo "$(date -Is) UPSTREAM_PROXY belum diisi di $ENV_FILE — relay tidak dijalankan." >&2
    echo "  Contoh: UPSTREAM_PROXY=http://user:pass@proxycrawler.dashboard.nolimit.id:2570" >&2
    exit 1
fi

export UPSTREAM_PROXY RELAY_HOST RELAY_PORT
exec "$PYTHON_BIN" "$APP_DIR/deploy/proxy-relay.py"
