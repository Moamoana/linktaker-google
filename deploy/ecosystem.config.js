// Konfigurasi PM2 untuk LinkTaker.
//
// Yang diawasi PM2 adalah deploy/pm2-loop.sh — satu proses yang hidup terus dan
// memanggil deploy/run-linktaker.sh tiap 3 jam. Jangan arahkan `script` ke
// run-linktaker.sh: script itu crawl sekali lalu exit, dan PM2 akan membaca exit
// sebagai mati lalu menjalankannya lagi seketika — crawl beruntun tanpa jeda.
//
//   pm2 start deploy/ecosystem.config.js
//   pm2 save
//
// Semua path dihitung dari letak file ini (__dirname), jadi tidak ada username
// atau home directory yang tertulis di sini dan file ini jalan apa adanya di
// mesin mana pun.

const path = require("path");

// File ini ada di deploy/, jadi akar project adalah satu tingkat di atasnya.
const ROOT = path.join(__dirname, "..");

module.exports = {
  apps: [
    {
      name: "linktaker",
      script: path.join(__dirname, "pm2-loop.sh"),
      interpreter: "bash",
      cwd: ROOT,

      // Loop-nya memang harus hidup terus; kalau mati, hidupkan lagi.
      autorestart: true,
      // Jeda sebelum menghidupkan ulang, supaya kegagalan yang langsung
      // berulang (mis. .venv terhapus) tidak jadi restart-loop rapat.
      restart_delay: 10000,
      // Satu instance. Dua crawl bersamaan akan merusak .browser_profile/,
      // dan flock akan menolak yang kedua.
      instances: 1,

      // Waktu bagi crawl yang sedang berjalan untuk berhenti rapi saat
      // `pm2 stop`/`pm2 restart`, sebelum PM2 memakai SIGKILL.
      kill_timeout: 30000,

      env: {
        APP_DIR: ROOT,
        INTERVAL_HOURS: "3",   // jarak antar-crawl
        JITTER_MAX: "600",     // sebar 0-10 menit sesudah jam bulat
        RUN_ON_START: "1",     // crawl sekali saat PM2 start
        VERBOSE: "1",          // output crawl ikut masuk `pm2 logs`
      },

      out_file: path.join(ROOT, "data/logs/pm2-out.log"),
      error_file: path.join(ROOT, "data/logs/pm2-err.log"),
      merge_logs: true,
      time: true,
    },
  ],
};
