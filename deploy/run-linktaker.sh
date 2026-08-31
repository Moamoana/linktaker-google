#!/usr/bin/env bash
# Satu kali crawl LinkTaker, aman dipanggil dari cron / systemd timer.
#
# Yang diurus script ini dan tidak diurus `python linktaker.py` sendiri:
#   - cd ke folder project (semua path di tool ini relatif: keywords.txt,
#     news_domains.txt, .browser_profile/)
#   - rentang tanggal dihitung dari hari ini, bukan tanggal mati di argumen
#   - output diberi timestamp, karena cli.py menulis dengan mode "w" alias
#     menimpa file lama
#   - --on-captcha skip, karena tidak ada yang menyelesaikan CAPTCHA jam 3 pagi
#   - flock, supaya run jam berikutnya tidak menabrak run yang belum selesai
#     dan merusak .browser_profile/

set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/linktaker-google}"

# Setelan khusus mesin ini. File-nya di-.gitignore, jadi mengubah setelan di
# sana tidak pernah bentrok dengan `git pull` — beda dengan mengedit script ini
# langsung, yang membuat setiap tarikan berikutnya ditolak.
# Lihat deploy/linktaker.env.example untuk isinya.
ENV_FILE="${ENV_FILE:-$APP_DIR/deploy/linktaker.env}"
if [ -f "$ENV_FILE" ]; then
    # shellcheck source=/dev/null
    . "$ENV_FILE"
fi
# Interpreter Python yang dipakai — path absolut ke python di dalam venv.
# Dipanggil langsung, bukan lewat "source .venv/bin/activate": activate butuh
# shell interaktif, dan cron maupun systemd tidak menyediakannya.
# Untuk conda, arahkan saja ke python di dalam env-nya; script tidak peduli.
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/.venv/bin/python}"
OUT_DIR="${OUT_DIR:-$APP_DIR/hasil}"
LOG_DIR="${LOG_DIR:-$APP_DIR/logs}"

ENGINE="${ENGINE:-all}"        # google | yahoo | bing | all
MODE="${MODE:-both}"           # web | nws | both
SORT="${SORT:-latest}"
# Rentang tanggal, diserahkan apa adanya ke --from/--until. Boleh relatif
# (1d, w, 2w, 3m, 1y, today, yesterday) atau tanggal pasti (2026-08-18).
# Bentuk relatif dihitung ulang tiap run oleh linktaker sendiri, jadi jadwal
# yang dibiarkan jalan berhari-hari ikut bergeser bersama kalender.
DATE_FROM="${DATE_FROM:-${DAYS_BACK:+${DAYS_BACK}d}}"
DATE_FROM="${DATE_FROM:-1d}"
DATE_UNTIL="${DATE_UNTIL:-today}"
MAX_PAGES="${MAX_PAGES:-5}"    # kosongkan untuk crawl semua halaman
GEO="${GEO:-}"                 # mis. my / malaysia; kosong = default browser
PROXY="${PROXY:-}"
KEEP_DAYS="${KEEP_DAYS:-14}"   # umur maksimum file hasil & log

# Tidak ada yang menunggu di depan laptop jam 3 pagi, jadi run terjadwal
# berjalan tanpa jendela dan melewati halaman yang kena CAPTCHA. Menunggu
# CAPTCHA_WAIT_TIMEOUT per halaman hanya menghabiskan jatah jadwal.
HEADED="${HEADED:-0}"          # 1 = paksa pakai jendela sepanjang run
ON_CAPTCHA="${ON_CAPTCHA:-skip}"   # skip | headed

# Kirim hasil ke endpoint submit_batch setelah crawl selesai — lihat
# deploy/submit-links.py. SUBMIT_ENABLED=0 mematikannya (hasil tetap ditulis
# ke file seperti biasa).
SUBMIT_ENABLED="${SUBMIT_ENABLED:-1}"
# Riwayat "sudah pernah dikirim" dan antrean kiriman yang gagal. Absolut,
# bukan relatif, supaya isinya tidak berpindah kalau APP_DIR diubah.
export SUBMIT_STATE_DIR="${SUBMIT_STATE_DIR:-$APP_DIR/state}"
# Sisanya (SUBMIT_URL, SUBMIT_BATCH_SIZE, SUBMIT_RETRIES, SUBMIT_TIMEOUT,
# SUBMIT_KEEP_DAYS, SUBMIT_QUEUE_MAX) hanya diteruskan kalau memang diisi di
# linktaker.env; kalau tidak, submit-links.py memakai default-nya sendiri —
# jadi nilai bawaan tidak perlu ditulis di dua tempat.
for _v in SUBMIT_URL SUBMIT_BATCH_SIZE SUBMIT_RETRIES SUBMIT_TIMEOUT \
          SUBMIT_KEEP_DAYS SUBMIT_QUEUE_MAX; do
    eval "[ -n \"\${$_v:-}\" ]" && export "$_v"
done

cd "$APP_DIR"
mkdir -p "$OUT_DIR" "$LOG_DIR"

# Gagal cepat dan jelas kalau path interpreter salah — tanpa ini errornya baru muncul
# 3 jam sekali di dalam log sebagai "command not found".
if [ ! -x "$PYTHON_BIN" ]; then
    echo "$(date -Is) PYTHON_BIN tidak ditemukan: $PYTHON_BIN" >&2
    echo "  buat venv-nya: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 127
fi

STAMP="$(date +%Y%m%d-%H%M)"
OUT="$OUT_DIR/links-${ENGINE}-${STAMP}.txt"
LOG="$LOG_DIR/run-${STAMP}.log"

# Dijalankan orang di terminal, atau oleh cron/systemd? Saat dijalankan manual,
# semuanya juga dicetak ke layar — script yang diam total selama 20 menit tidak
# bisa dibedakan dari script yang mati. VERBOSE=1 memaksa tampil meski output
# sedang di-pipe, VERBOSE=0 memaksa senyap.
if [ -n "${VERBOSE:-}" ]; then
    INTERACTIVE="$VERBOSE"
elif [ -t 1 ]; then
    INTERACTIVE=1
else
    INTERACTIVE=0
fi

# Satu baris ke log, dan ke layar juga kalau ada orang yang melihat.
say() {
    echo "$*" >>"$LOG"
    [ "$INTERACTIVE" = "1" ] && echo "$*"
    return 0
}

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
    # Dari cron ini memang harus senyap, tapi orang yang baru menekan Enter
    # perlu tahu kenapa tidak terjadi apa-apa.
    [ "$INTERACTIVE" = "1" ] && \
        echo "Run sebelumnya masih berjalan — dilewati. Cek: pgrep -af linktaker.py"
    exit 0
fi

ARGS=(--input keywords.txt --engine "$ENGINE" --mode "$MODE" --sort "$SORT"
      --from "$DATE_FROM" --until "$DATE_UNTIL" --output "$OUT"
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

say "=== $(date -Is) | engine=$ENGINE mode=$MODE $DATE_FROM..$DATE_UNTIL -> $OUT ==="
say "Log: $LOG"

status=0
if [ "$INTERACTIVE" = "1" ]; then
    # errexit dimatikan sementara: dengan "pipefail" di atas, pipeline ini
    # mewarisi exit code linktaker, dan errexit akan menghentikan script tepat
    # sebelum PIPESTATUS sempat dibaca — sehingga kegagalan berakhir tanpa
    # pesan apa pun. PIPESTATUS juga harus dibaca persis setelah pipeline,
    # karena perintah apa pun sesudahnya menimpanya.
    set +e
    "${RUNNER[@]}" "$PYTHON_BIN" linktaker.py "${ARGS[@]}" 2>&1 | tee -a "$LOG"
    status=${PIPESTATUS[0]}
    set -e
else
    "${RUNNER[@]}" "$PYTHON_BIN" linktaker.py "${ARGS[@]}" >>"$LOG" 2>&1 || status=$?
fi

if [ "$status" -ne 0 ]; then
    say "$(date -Is) GAGAL (exit $status), lihat $LOG"
elif [ -s "$OUT" ]; then
    say "$(date -Is) SELESAI — $(wc -l <"$OUT") link di $OUT"
else
    say "$(date -Is) SELESAI tapi 0 link (kemungkinan kena CAPTCHA)"
fi

# Kirim ke submit_batch. Dijalankan juga saat crawl gagal atau 0 link, karena
# antrean dari run yang gagal kirim sebelumnya baru bisa habis di sini.
#
# Kegagalan kirim sengaja tidak mengubah exit code script: link yang belum
# terkirim sudah masuk antrean dan ikut jalan 3 jam lagi, jadi menandai run
# ini "failed" hanya membuat systemd/cron ribut untuk sesuatu yang sudah
# ditangani sendiri.
if [ "$SUBMIT_ENABLED" = "1" ]; then
    if [ "$INTERACTIVE" = "1" ]; then
        "$PYTHON_BIN" deploy/submit-links.py "$OUT" 2>&1 | tee -a "$LOG" || true
    else
        "$PYTHON_BIN" deploy/submit-links.py "$OUT" >>"$LOG" 2>&1 || true
    fi
fi

# Buang hasil dan log yang sudah lewat umur.
find "$OUT_DIR" -name 'links-*.txt' -mtime +"$KEEP_DAYS" -delete 2>/dev/null || true
find "$LOG_DIR" -name 'run-*.log'   -mtime +"$KEEP_DAYS" -delete 2>/dev/null || true

exit "$status"
