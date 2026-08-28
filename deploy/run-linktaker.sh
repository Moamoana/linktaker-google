#!/usr/bin/env bash
# Satu kali crawl LinkTaker, aman dipanggil dari cron / systemd timer.
#
# Yang diurus script ini dan tidak diurus `python linktaker.py` sendiri:
#   - cd ke folder project (semua path di tool ini relatif: keywords.txt,
#     news_domains.txt, .browser_profile/)
#   - rentang tanggal dihitung dari hari ini, bukan tanggal mati di run.txt
#   - output diberi timestamp, karena cli.py menulis dengan mode "w" alias
#     menimpa file lama
#   - display virtual (Xvfb), karena browser.py memakai headless=False
#   - flock, supaya run jam berikutnya tidak menabrak run yang belum selesai
#     dan merusak .browser_profile/

set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/linktaker-google}"
# Interpreter Python yang dipakai. Untuk conda, isi dengan path absolut ke
# python di dalam env (conda run -n NAMA python -c "import sys; print(sys.executable)").
# conda activate tidak dipakai karena butuh shell interaktif, yang tidak ada di cron.
PYTHON_BIN="${PYTHON_BIN:-$HOME/miniconda3/envs/linktaker/bin/python}"
OUT_DIR="${OUT_DIR:-$APP_DIR/hasil}"
LOG_DIR="${LOG_DIR:-$APP_DIR/logs}"

ENGINE="${ENGINE:-all}"        # google | yahoo | bing | all
MODE="${MODE:-both}"           # web | nws | both
SORT="${SORT:-latest}"
DAYS_BACK="${DAYS_BACK:-1}"    # --from = hari ini dikurangi sekian hari
MAX_PAGES="${MAX_PAGES:-5}"    # kosongkan untuk crawl semua halaman
GEO="${GEO:-}"                 # mis. my / malaysia; kosong = default browser
PROXY="${PROXY:-}"
KEEP_DAYS="${KEEP_DAYS:-14}"   # umur maksimum file hasil & log

# Tidak ada yang menunggu di depan laptop jam 3 pagi, jadi run terjadwal
# berjalan tanpa jendela dan melewati halaman yang kena CAPTCHA. Menunggu
# CAPTCHA_WAIT_TIMEOUT per halaman hanya menghabiskan jatah jadwal.
HEADED="${HEADED:-0}"          # 1 = paksa pakai jendela sepanjang run
ON_CAPTCHA="${ON_CAPTCHA:-skip}"   # skip | headed

cd "$APP_DIR"
mkdir -p "$OUT_DIR" "$LOG_DIR"

# Gagal cepat dan jelas kalau path conda salah — tanpa ini errornya baru muncul
# 3 jam sekali di dalam log sebagai "command not found".
if [ ! -x "$PYTHON_BIN" ]; then
    echo "$(date -Is) PYTHON_BIN tidak ditemukan: $PYTHON_BIN" >&2
    echo "  cari dengan: conda run -n linktaker python -c 'import sys; print(sys.executable)'" >&2
    exit 127
fi

STAMP="$(date +%Y%m%d-%H%M)"
FROM="$(date -d "-${DAYS_BACK} day" +%F)"
UNTIL="$(date +%F)"
OUT="$OUT_DIR/links-${ENGINE}-${STAMP}.txt"
LOG="$LOG_DIR/run-${STAMP}.log"

# Jangan tumpang tindih dengan run sebelumnya yang masih jalan.
# flock yang hilang membuat setiap run terlihat "terkunci" dan dilewati diam-diam
# selamanya — kegagalan yang jauh lebih sulit dilacak daripada berhenti di sini.
if ! command -v flock >/dev/null 2>&1; then
    echo "$(date -Is) flock tidak ada — pasang dengan: sudo apt install -y util-linux" >&2
    exit 1
fi

exec 9>"$APP_DIR/.linktaker.lock"
if ! flock -n 9; then
    echo "$(date -Is) run sebelumnya masih berjalan — dilewati" >>"$LOG_DIR/skipped.log"
    exit 0
fi

ARGS=(--input keywords.txt --engine "$ENGINE" --mode "$MODE" --sort "$SORT"
      --from "$FROM" --until "$UNTIL" --output "$OUT"
      --on-captcha "$ON_CAPTCHA")
if [ "$HEADED" = "1" ]; then ARGS+=(--headed); else ARGS+=(--headless); fi
[ -n "$MAX_PAGES" ] && ARGS+=(--max-pages "$MAX_PAGES")
[ -n "$GEO" ]       && ARGS+=(--geo "$GEO")
[ -n "$PROXY" ]     && ARGS+=(--proxy "$PROXY")

# Sebuah jendela hanya perlu ada kalau run ini memang akan membukanya. Pada
# setelan default (headless + skip) Chromium tidak butuh X sama sekali, jadi
# Xvfb tidak dipasang dan tidak dijalankan.
RUNNER=()
if [ "$HEADED" = "1" ] || [ "$ON_CAPTCHA" = "headed" ]; then
    if [ -z "${DISPLAY:-}" ]; then
        if command -v xvfb-run >/dev/null 2>&1; then
            RUNNER=(xvfb-run -a -s "-screen 0 1920x1080x24")
        else
            echo "$(date -Is) butuh jendela (HEADED=$HEADED ON_CAPTCHA=$ON_CAPTCHA)" \
                 "tapi tidak ada DISPLAY dan xvfb-run belum terpasang." >&2
            echo "  pasang dengan: sudo apt install -y xvfb" >&2
            exit 1
        fi
    fi
fi

{
    echo "=== $(date -Is) | engine=$ENGINE mode=$MODE $FROM..$UNTIL -> $OUT ==="
} >>"$LOG"

status=0
"${RUNNER[@]}" "$PYTHON_BIN" linktaker.py "${ARGS[@]}" >>"$LOG" 2>&1 || status=$?

if [ "$status" -ne 0 ]; then
    echo "$(date -Is) GAGAL (exit $status), lihat $LOG" >>"$LOG"
elif [ -s "$OUT" ]; then
    echo "$(date -Is) SELESAI — $(wc -l <"$OUT") link di $OUT" >>"$LOG"
else
    echo "$(date -Is) SELESAI tapi 0 link (kemungkinan kena CAPTCHA)" >>"$LOG"
fi

# Buang hasil dan log yang sudah lewat umur.
find "$OUT_DIR" -name 'links-*.txt' -mtime +"$KEEP_DAYS" -delete 2>/dev/null || true
find "$LOG_DIR" -name 'run-*.log'   -mtime +"$KEEP_DAYS" -delete 2>/dev/null || true

exit "$status"
