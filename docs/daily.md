# Operasional harian LinkTaker di PM2

Untuk mesin yang jadwalnya sudah dipegang PM2. Pemasangannya ada di
[INSTALL-LINUX.md](INSTALL-LINUX.md) — dokumen ini hanya soal pemakaian
sehari-hari: menyalakan setelah laptop dimatikan, memastikan jadwalnya hidup,
membaca log, dan melihat hasil.

Semua perintah dijalankan dari folder project:

```bash
cd ~/linktaker-google
```

## 1. Menyalakan setelah laptop dimatikan

Tidak ada yang perlu dinyalakan. Setelah `pm2 startup` terpasang, systemd
menjalankan `pm2 resurrect` saat boot — cukup login seperti biasa.

Karena crawl terakhir sudah lewat lebih dari setengah interval (1,5 jam),
`RUN_ON_START=1` membuat loop langsung crawl sekali tanpa menunggu jam bulat.
Jadi laptop yang dimatikan sore dan dinyalakan pagi akan langsung bekerja.

Kalau ternyata tidak hidup — `pm2 status` kosong atau `linktaker` tidak ada di
daftar:

```bash
pm2 resurrect                       # muat ulang dari ~/.pm2/dump.pm2
```

Kalau itu pun tidak menolong, jalankan dari config-nya lagi:

```bash
pm2 start deploy/ecosystem.config.js
pm2 save
```

Selalu `deploy/ecosystem.config.js`, **jangan** `deploy/pm2-loop.sh` langsung.
Menjalankan script-nya langsung membuat seluruh setelan di
[`ecosystem.config.js`](../deploy/ecosystem.config.js) dilewati — termasuk
`kill_timeout` 30 detik, yang mencegah crawl ditinggal sebagai proses yatim
saat `pm2 stop`.

## 2. Melihat status

```bash
pm2 status                              # linktaker harus "online", kolom ↺ tetap 0
pgrep -af linktaker.py                  # ada isinya = sedang crawl
date -d @$(cat data/state/last-run)     # kapan crawl terakhir selesai
```

Cara membacanya:

| Yang terlihat | Artinya |
|---|---|
| `online` + `pgrep` ada isinya | sedang crawl sekarang |
| `online` + `pgrep` kosong | sehat, sedang menunggu slot berikutnya |
| kolom `↺` naik terus | loop mati berulang — lihat `pm2 logs linktaker --err` |
| `errored` / `stopped` | mati; `pm2 restart linktaker` |

`pgrep` yang kosong **bukan** tanda masalah. Di antara crawl, loop-nya memang
sedang `sleep` — statusnya tetap `online`.

Jadwal crawl berikutnya:

```bash
pm2 logs linktaker --nostream --lines 200 | grep 'crawl berikutnya' | tail -1
```

## 3. Melihat log

Ada dua lapis log, dan keduanya dipakai untuk hal yang berbeda.

**Log loop** — jadwal, mulai/selesai crawl, error PM2:

```bash
pm2 logs linktaker                          # ikuti langsung (Ctrl+C untuk keluar)
pm2 logs linktaker --lines 50 --nostream    # 50 baris terakhir, tidak menempel
pm2 logs linktaker --err                    # khusus error
```

Filenya di `data/logs/pm2-out.log` dan `data/logs/pm2-err.log`.

**Log per-run** — detail crawl tiap keyword, CAPTCHA, dan hasil pengiriman:

```bash
ls -lt data/logs/run-*.log | head -5                # daftar run terbaru
tail -f "$(ls -t data/logs/run-*.log | head -1)"    # ikuti run terbaru
```

Yang biasa dicari di dalamnya:

```bash
LOG=$(ls -t data/logs/run-*.log | head -1)

grep -c 'CAPTCHA hit' "$LOG"        # berapa halaman kena CAPTCHA
grep -iE 'SELESAI|GAGAL' "$LOG"     # hasil akhir run
tail -20 "$LOG"                      # termasuk ringkasan pengiriman
```

Log lebih tua dari `KEEP_DAYS` (default 14 hari) dihapus sendiri tiap akhir run.

## 4. Melihat hasil

```bash
ls -lt data/hasil/ | head -10                    # file hasil terbaru di atas

HASIL=$(ls -t data/hasil/links-*.txt | head -1)
wc -l "$HASIL"                                   # jumlah link
head -20 "$HASIL"                                # contoh isinya
```

Nama filenya bertimestamp (`links-all-20260903-0944.txt`) karena `cli.py`
menulis output dengan mode `"w"` — tanpa timestamp, run berikutnya akan
menimpa hasil sebelumnya.

Total link unik hari ini dari seluruh run:

```bash
cat data/hasil/links-*-$(date +%Y%m%d)-*.txt | sort -u | wc -l
```

Status pengiriman ke endpoint `submit_batch`:

```bash
wc -l data/state/sent-urls.txt       # total yang pernah terkirim
wc -l data/state/pending-urls.txt    # antrean gagal kirim — idealnya 0
```

`pending-urls.txt` yang terus membesar berarti endpointnya sedang tidak bisa
dihubungi. Isinya tidak hilang: antrean itu ikut dicoba lagi setiap run
berikutnya, termasuk saat crawl-nya sendiri gagal.

## Perintah lain yang sering dipakai

```bash
pm2 restart linktaker --update-env   # wajib setelah git pull atau ubah linktaker.env
pm2 stop linktaker                   # matikan jadwal sementara
pm2 start linktaker                  # hidupkan lagi

./deploy/run-linktaker.sh            # paksa satu crawl sekarang, di luar jadwal
```

Menjalankan `run-linktaker.sh` manual saat jadwal sedang aktif itu aman —
`flock` menjaga keduanya tidak bertabrakan. Yang datang belakangan dilewati dan
dicatat di `data/logs/skipped.log`.

Dua hal yang mudah mengagetkan:

- **`pm2 restart` saat crawl berjalan akan menghentikan crawl itu.** Disengaja:
  loop meneruskan sinyal ke proses anaknya supaya `data/.linktaker.lock` tidak
  ditinggal proses yatim. Konsekuensinya crawl yang sedang jalan hangus.
- **Restart beruntun tidak jadi crawl beruntun.** Kalau crawl terakhir belum
  lewat 1,5 jam, start/restart tidak memicu crawl baru; log menulis
  *"run terakhir N menit lalu — menunggu slot berikutnya"*. Itu normal.


## Baris log yang perlu dikenali

Tiga pesan ini bukan error, dan artinya beda-beda:

| Baris | Artinya | Tindakan |
|---|---|---|
| `SELESAI tapi 0 link` | crawl jalan sampai habis, tapi tidak ada yang lolos — hampir selalu CAPTCHA | lihat bagian [Kalau hasilnya kosong](#kalau-hasilnya-kosong) |
| `DIHENTIKAN — lewat batas waktu` | ada halaman yang menggantung dan `RUN_TIMEOUT` membunuh prosesnya; link yang sempat terkumpul tetap tersimpan | tidak perlu apa-apa, slot berikutnya jalan normal |
| `[loop] run dilewati — lock masih dipegang proses lain` | ada crawl lain yang masih berjalan | loop mencoba lagi 60 detik kemudian, sampai 3 kali |

Yang **bukan** normal dan perlu ditindak: log yang berhenti bertambah sementara
`pgrep -af linktaker.py` tetap menunjukkan proses hidup dengan `%CPU 0.0`. Itu
gejala hang. Cek umurnya dan bunuh lewat PM2:

```bash
ps -p $(pgrep -f linktaker.py | head -1) -o pid,etime,%cpu,stat
pm2 restart linktaker
```

Sejak `PAGE_TIMEOUT` dan `RUN_TIMEOUT` dipasang, ini seharusnya tidak terjadi
lagi — halaman yang macet gagal dalam 60 detik, dan seluruh run dibatasi 90
menit. Kalau masih terjadi, itu bug baru dan layak dilaporkan.

## Kalau laptop dimatikan

Crawling berhenti — PM2 hanya proses di laptop itu. Yang perlu diketahui:

- **Shutdown/restart**: hidup lagi sendiri saat boot berikutnya, dan langsung
  crawl karena jarak dari run terakhir sudah lewat setengah interval.
- **Suspend (tutup layar)**: proses dibekukan, bukan mati. Jadwalnya bisa
  meleset dari jam bulat sesaat setelah bangun, lalu kembali menempel sendiri
  pada siklus berikutnya karena slot dihitung ulang dari jam dinding.
- **Slot yang terlewat tidak diulang**, tapi tidak berarti link hilang:
  `DATE_FROM=1d` menyapu satu hari ke belakang sementara jaraknya cuma 3 jam,
  jadi overlapnya besar. Mati belasan jam masih tertutup run berikutnya.
  Yang benar-benar merugikan baru mati lebih dari ~24 jam.
- **Mati di tengah crawl**: aman. `flock` dipegang lewat file descriptor dan
  dilepas kernel begitu prosesnya hilang, jadi tidak ada lock nyangkut.

Supaya tidak suspend sendiri saat layar ditutup:

```bash
sudo nano /etc/systemd/logind.conf
#   HandleLidSwitch=ignore
#   HandleLidSwitchExternalPower=ignore
sudo systemctl restart systemd-logind
```

Lalu di Settings → Power: matikan *Automatic Suspend*, set *Screen Blank* ke
Never.

## Kalau hasilnya kosong

Cek dulu apakah penyebabnya CAPTCHA:

```bash
LOG=$(ls -t data/logs/run-*.log | head -1)
grep -c 'CAPTCHA hit' "$LOG"
```

Banyak `CAPTCHA hit in headless and --on-captcha skip` berarti halaman-halaman
itu dilewati dan tidak menyumbang link. Penanganannya ada di [Catatan
penting](INSTALL-LINUX.md#catatan-penting) — ringkasnya: jalankan sekali sambil
ditunggui supaya tiketnya tersimpan di `.browser_profile/`,

```bash
pm2 stop linktaker
HEADED=1 ON_CAPTCHA=headed ./deploy/run-linktaker.sh
pm2 start linktaker
```

turunkan `MAX_PAGES` di `deploy/linktaker.env`, atau pakai `PROXY`.
