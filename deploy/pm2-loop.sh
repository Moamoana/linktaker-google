#!/usr/bin/env bash
# Penjadwal untuk PM2: satu proses yang hidup terus dan memanggil
# run-linktaker.sh setiap INTERVAL_HOURS jam.
#
# Kenapa tidak `pm2 start deploy/run-linktaker.sh` langsung: script itu crawl
# sekali lalu selesai dan exit 0. PM2 membaca exit sebagai "mati" dan
# menjalankannya lagi seketika, jadi crawl akan beruntun tanpa jeda sepanjang
# hari — jalan tercepat menuju CAPTCHA. Di sini PM2 mengawasi loop-nya, dan
# loop ini yang memegang jadwalnya; di `pm2 list` statusnya tetap "online".
#
# Yang diurus di sini:
#   - jadwal menempel di jam bulat waktu lokal (00:00, 03:00, 06:00, ...),
#     bukan "3 jam sejak PM2 terakhir di-restart"
#   - restart PM2 yang terjadi tepat setelah sebuah run tidak memicu crawl
#     baru; jarak minimum antar-crawl dijaga setengah interval
#   - `pm2 stop`/`pm2 restart` menghentikan crawl yang sedang jalan, bukan
#     meninggalkannya sebagai proses yatim yang memegang .linktaker.lock

set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"

# Jarak antar-crawl. INTERVAL_SECONDS menang kalau diisi — dipakai untuk
# menguji loop ini tanpa menunggu berjam-jam.
INTERVAL_HOURS="${INTERVAL_HOURS:-3}"
INTERVAL="${INTERVAL_SECONDS:-$((INTERVAL_HOURS * 3600))}"

# Sebar 0..JITTER_MAX detik sesudah jam bulat, supaya request tidak selalu
# jatuh di menit yang sama persis setiap hari. Setara RandomizedDelaySec pada
# systemd timer.
JITTER_MAX="${JITTER_MAX:-600}"

# Crawl langsung saat PM2 baru start, tanpa menunggu slot berikutnya.
RUN_ON_START="${RUN_ON_START:-1}"

# Output run-linktaker.sh ikut tampil di `pm2 logs`, bukan hanya di logs/run-*.log.
export VERBOSE="${VERBOSE:-1}"

STAMP_FILE="$APP_DIR/data/state/last-run"
child=""
sedang_berhenti=0

say() {
    echo "$(date -Is) [loop] $*"
}

# PM2 mengirim SIGINT saat stop/restart. Tanpa ini, `sleep` yang sedang
# berjalan memang ikut mati, tapi crawl yang sedang berjalan tidak — ia jadi
# proses yatim yang masih memegang .linktaker.lock, dan run berikutnya
# dilewati diam-diam sampai crawl itu selesai sendiri.
berhenti() {
    # PM2 mengirim sinyal ke seluruh grup proses, jadi handler ini bisa
    # terpanggil lebih dari sekali; yang kedua tidak perlu berbuat apa-apa.
    [ "$sedang_berhenti" = "1" ] && exit 0
    sedang_berhenti=1
    if [ -n "$child" ]; then
        say "dihentikan — menutup proses yang sedang berjalan"
        kill "$child" 2>/dev/null || true
        wait "$child" 2>/dev/null || true
    else
        say "dihentikan"
    fi
    exit 0
}
trap berhenti INT TERM

# Jalankan di background lalu `wait`, bukan di foreground: bash baru menjalankan
# trap setelah perintah foreground selesai, jadi tanpa pola ini sinyal stop dari
# PM2 baru terasa setelah crawl 20 menit itu kelar.
tunggu_anak() {
    child=$!
    wait "$child" || true
    child=""
}

crawl() {
    say "mulai crawl"
    "$APP_DIR/deploy/run-linktaker.sh" &
    tunggu_anak
    mkdir -p "$(dirname "$STAMP_FILE")"
    date +%s >"$STAMP_FILE"
    say "crawl selesai"
}

tidur() {
    sleep "$1" &
    tunggu_anak
}

# Detik tersisa menuju kelipatan interval berikutnya menurut jam dinding lokal.
# Dihitung dari jam-menit-detik hari ini, bukan dari epoch, karena epoch
# terpatok UTC — kelipatan 3 jam di sana jatuh pukul 07:00/10:00 WIB, bukan
# 00:00/03:00 seperti yang tertulis di jadwal cron sebelumnya.
detik_ke_slot_berikutnya() {
    local h m s lewat
    h=$((10#$(date +%H))); m=$((10#$(date +%M))); s=$((10#$(date +%S)))
    lewat=$(((h * 3600 + m * 60 + s) % INTERVAL))
    echo $((INTERVAL - lewat))
}

say "APP_DIR=$APP_DIR interval=${INTERVAL}s jitter=0..${JITTER_MAX}s"

# Restart PM2 yang beruntun tidak boleh berubah jadi crawl beruntun. Kalau run
# terakhir masih lebih baru dari setengah interval, tunggu slot berikutnya.
if [ "$RUN_ON_START" = "1" ]; then
    terakhir=$(cat "$STAMP_FILE" 2>/dev/null || echo 0)
    selisih=$(( $(date +%s) - terakhir ))
    if [ "$selisih" -ge $((INTERVAL / 2)) ]; then
        crawl
    else
        say "run terakhir $((selisih / 60)) menit lalu — menunggu slot berikutnya"
    fi
fi

while true; do
    jeda=$(detik_ke_slot_berikutnya)
    jitter=$((JITTER_MAX > 0 ? RANDOM % JITTER_MAX : 0))

    # Slot berikutnya bisa jatuh hanya beberapa menit lagi — kalau PM2 baru
    # start pukul 02:55, atau kalau crawl sebelumnya berjalan lama dan hampir
    # menyentuh slot berikutnya. Lewati slot seperti itu: jarak antar-crawl
    # dijaga minimal setengah interval, apa pun yang terjadi.
    sekarang=$(date +%s)
    terakhir=$(cat "$STAMP_FILE" 2>/dev/null || echo 0)
    target=$((sekarang + jeda + jitter))
    while [ "$target" -lt $((terakhir + INTERVAL / 2)) ]; do
        target=$((target + INTERVAL))
    done
    jeda=$((target - sekarang))

    say "crawl berikutnya $(date -d "+${jeda} seconds" +%H:%M 2>/dev/null || echo "dalam $((jeda / 60)) menit")"
    tidur "$jeda"
    crawl
done
