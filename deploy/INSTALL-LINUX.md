# Menjalankan LinkTaker otomatis tiap 3 jam di laptop Linux

Semua perintah di bawah tidak memuat username — dipakai `~`, `$HOME`, atau `%h`
(kode systemd untuk home directory), jadi bisa disalin apa adanya.

Pakai `venv` bawaan Python — tidak perlu conda. Semua dependency project ini
paket PyPI biasa, jadi tidak ada yang bisa dilakukan conda di sini yang `venv`
tidak bisa.

## 1. Pasang paket sistem

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

`xvfb` **tidak** diperlukan untuk setelan default (headless). Pasang hanya kalau
nanti mau menjalankan mode berjendela tanpa desktop — lihat [Catatan
penting](#catatan-penting).

Pastikan Python-nya 3.8 ke atas:

```bash
python3 --version
```

## 2. Ambil project

```bash
cd ~
git clone -b feat/geo-and-headless https://github.com/Moamoana/linktaker-google.git
cd linktaker-google
```

`-b feat/geo-and-headless` diperlukan selama branch ini belum di-merge: `main`
belum memuat `deploy/`, `geo.py`, maupun flag `--headless`/`--on-captcha`.
Setelah di-merge nanti, cukup `git clone` biasa. Pastikan benar:

```bash
git branch --show-current    # harus: feat/geo-and-headless
ls deploy/                   # harus ada 4 file
```

## 3. Buat virtual environment

```bash
python3 -m venv .venv
```

Ini membuat folder `.venv/` di dalam project. Isinya interpreter Python
tersendiri, jadi paket yang dipasang di sini tidak mengotori Python sistem.

## 4. Pasang dependency

```bash
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
```

Perhatikan: perintahnya `.venv/bin/pip`, **bukan** `pip` biasa. Cara ini tidak
butuh `source .venv/bin/activate` sama sekali — dan itu memang disengaja, karena
`activate` tidak tersedia di cron maupun systemd nanti.

## 5. Pasang Chromium untuk Playwright

```bash
.venv/bin/playwright install chromium
sudo .venv/bin/playwright install-deps chromium
```

Baris pertama mengunduh Chromium-nya. Baris kedua memasang library sistem yang
dibutuhkan Chromium (butuh `sudo`, dan hanya sekali per laptop).

## 6. Salin file input

Dua file ini di-`.gitignore` sehingga tidak ikut ter-clone. Salin manual dari
laptop Windows ke `~/linktaker-google/`:

| File | Kalau tidak ada |
|---|---|
| `keywords.txt` | Program berhenti dengan `Input file not found` |
| `news_domains.txt` | `--news-filter strict` ditolak, mode `smart` kehilangan daftar penerbitnya |

## 7. Cek path interpreter

**Tidak perlu diedit maupun tahu username Anda.** `linktaker.service` memakai
`%h`, kode systemd untuk home directory user yang menjalankannya:

```
Environment=PYTHON_BIN=%h/linktaker-google/.venv/bin/python
```

systemd yang menggantinya jadi `/home/<username>/...` saat unit dijalankan, jadi
file yang sama jalan di user mana pun. Cukup pastikan file yang ditunjuk memang
ada:

```bash
ls -l ~/linktaker-google/.venv/bin/python
```

Kalau muncul daftar file, lanjut. Kalau `No such file`, berarti langkah 3–4
belum selesai.

> Kalau suatu saat perlu menulis path lengkapnya secara manual (misal untuk
> cron, yang **tidak** mengenal `%h`), cek username dan home dengan:
>
> ```bash
> whoami        # nama user, mis. nolimit
> echo "$HOME"  # home lengkap, mis. /home/nolimit
> ```

## 8. Tes manual dulu

```bash
cd ~/linktaker-google
./deploy/run-linktaker.sh
cat logs/run-*.log | tail -30
ls -l hasil/
```

Kalau ini belum menghasilkan link, jadwal otomatis juga tidak akan menghasilkan
apa-apa — perbaiki di sini dulu sebelum lanjut.

## 9. Pasang timer systemd

```bash
mkdir -p ~/.config/systemd/user
cp ~/linktaker-google/deploy/linktaker.{service,timer} ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now linktaker.timer

# Supaya tetap jalan walau user belum login ke desktop:
sudo loginctl enable-linger "$(whoami)"
```

Cek dan operasikan:

```bash
systemctl --user list-timers linktaker.timer   # kapan run berikutnya
systemctl --user start linktaker.service       # paksa jalan sekarang
journalctl --user -u linktaker.service -n 50   # log systemd
tail -f ~/linktaker-google/logs/run-*.log      # log crawl
systemctl --user stop linktaker.timer          # matikan jadwal
```

## Alternatif: cron

Kalau lebih suka cron, `crontab -e` lalu:

```
0 */3 * * * $HOME/linktaker-google/deploy/run-linktaker.sh >/dev/null 2>&1
```

Bedanya: cron **tidak** mengejar jadwal yang terlewat saat laptop mati atau
suspend, sedangkan `Persistent=true` di systemd timer mengejarnya. Untuk laptop,
systemd timer lebih tepat.

## Mengubah parameter crawl

Ada tiga tempat, dan urutan menangnya dari atas ke bawah:

**1. Di depan perintah — untuk sekali jalan**

```bash
ENGINE=google MODE=web MAX_PAGES=2 ./deploy/run-linktaker.sh
```

**2. `deploy/linktaker.env` — setelan tetap mesin ini**

```bash
cp deploy/linktaker.env.example deploy/linktaker.env
nano deploy/linktaker.env
```

Hapus `#` di depan baris yang ingin diaktifkan. File ini di-`.gitignore`,
jadi tidak akan bentrok saat `git pull`. Berlaku untuk run manual maupun
terjadwal.

**3. `~/.config/systemd/user/linktaker.service` — khusus run terjadwal**

```bash
nano ~/.config/systemd/user/linktaker.service
systemctl --user daemon-reload
```

> **Jangan mengedit `deploy/run-linktaker.sh` langsung.** File itu di-track git,
> jadi setiap perubahan di sana membuat `git pull` berikutnya ditolak dengan
> *"local changes would be overwritten by merge"*. Pakai `linktaker.env`.

Daftar variabelnya:

| Variabel    | Default | Arti                                              |
|-------------|---------|---------------------------------------------------|
| `ENGINE`    | `all`   | `google` / `yahoo` / `bing` / `all`               |
| `MODE`      | `both`  | `web` (tab Semua) / `nws` (Berita) / `both`       |
| `SORT`      | `latest`| urutan hasil                                       |
| `DATE_FROM` | `1d`    | Awal rentang. Relatif (`1d`, `w`, `2w`, `3m`, `1y`) atau tanggal pasti |
| `DATE_UNTIL`| `today` | Akhir rentang, format sama                         |
| `DAYS_BACK` | –       | Cara lama, masih jalan: `DAYS_BACK=7` sama dengan `DATE_FROM=7d` |
| `MAX_PAGES` | `5`     | kosongkan untuk semua halaman (lebih rawan CAPTCHA)|
| `GEO`       | –       | `my`, `malaysia`, dst.                             |
| `PROXY`     | –       | `http://user:pass@host:2570`                       |
| `HEADED`    | `0`     | `1` = pakai jendela sepanjang run (butuh desktop/xvfb) |
| `ON_CAPTCHA`| `skip`  | `skip` untuk run terjadwal, `headed` kalau ditunggui   |
| `KEEP_DAYS` | `14`    | umur maksimum file hasil dan log                   |

```bash
ENGINE=google GEO=malaysia MAX_PAGES=3 ./deploy/run-linktaker.sh
DATE_FROM=w ./deploy/run-linktaker.sh          # jendela seminggu terakhir
```

Rentang tanggalnya sengaja ditulis relatif (`1d`, `w`, `3m`), bukan tanggal
pasti. Bedanya baru terasa setelah beberapa hari: `DATE_FROM=2026-08-27` akan
terus melebar setiap hari sampai crawl-nya makin lambat dan makin rawan CAPTCHA,
sedangkan `DATE_FROM=1d` menjaga lebar jendelanya tetap. Perhitungannya
dilakukan `linktaker` sendiri di setiap run, bukan saat file ini disalin.

## Kirim otomatis ke submit_batch

Setiap run, setelah crawl selesai, `run-linktaker.sh` memanggil
`deploy/submit-links.py` yang mengirim link ke endpoint `submit_batch`:

```
POST http://103.191.17.47:8001/submit_batch/
Content-Type: application/json

{"links": ["https://...", "https://..."]}
```

Tidak perlu langkah pemasangan tambahan: script itu hanya memakai pustaka
standar Python, jadi tidak ada tambahan di `requirements.txt`, dan sudah aktif
sejak run pertama. Untuk mematikannya, `SUBMIT_ENABLED=0`.

Yang dikerjakannya, dan alasannya:

- **Hanya link baru yang dikirim.** Dengan `DATE_FROM=1d` dan jadwal 3 jam
  sekali, satu berita yang sama muncul di sekitar delapan run berturut-turut.
  Link yang sudah pernah terkirim dicatat di `state/sent-urls.txt` dan tidak
  dikirim lagi selama `SUBMIT_KEEP_DAYS` (30 hari). Perbandingannya memakai
  bentuk URL yang sudah dinormalkan — `http`/`https`, ada/tidaknya `www.`, dan
  garis miring di ujung tidak dianggap sebagai berita yang berbeda; yang
  dikirim tetap URL aslinya.
- **Dipecah per 100 link** — batas endpoint-nya memang 100 URL per batch. Batch
  yang tetap ditolak dipecah dua lalu dicoba lagi, jadi batas sisi server yang
  berubah sewaktu-waktu tidak berujung pada link yang dibuang.
- **Server mati tidak menghilangkan hasil crawl.** Batch yang gagal dicoba
  ulang 3 kali (jeda 2 lalu 4 detik), setelah itu link masuk
  `state/pending-urls.txt` dan ikut terkirim di run berikutnya. Antrean juga
  ikut dikosongkan pada run yang crawl-nya gagal atau menghasilkan 0 link.
- **Kegagalan kirim tidak menandai run sebagai gagal.** Link-nya sudah masuk
  antrean, jadi tidak ada yang perlu dikerjakan orang; cukup terbaca di log.
  Yang *tidak* diantrekan adalah penolakan 4xx (mis. URL endpoint salah ketik):
  mengulangnya tidak akan mengubah hasil, jadi link-nya dibuang dan alasannya
  ditulis di log.

Setelannya, semuanya lewat `deploy/linktaker.env` seperti setelan crawl:

| Variabel            | Default | Arti                                        |
|---------------------|---------|---------------------------------------------|
| `SUBMIT_ENABLED`    | `1`     | `0` = jangan kirim, hasil tetap ditulis ke `hasil/` |
| `SUBMIT_URL`        | endpoint di atas | tujuan POST                        |
| `SUBMIT_BATCH_SIZE` | `100`   | link per satu POST (batas server: 100)      |
| `SUBMIT_RETRIES`    | `3`     | percobaan per batch sebelum masuk antrean   |
| `SUBMIT_TIMEOUT`    | `30`    | batas waktu per POST, dalam detik           |
| `SUBMIT_KEEP_DAYS`  | `30`    | berapa lama sebuah link diingat "sudah dikirim" |
| `SUBMIT_QUEUE_MAX`  | `20000` | batas antrean saat server mati berhari-hari |
| `SUBMIT_STATE_DIR`  | `state/`| lokasi riwayat kirim & antrean              |

Memeriksa dan menguji:

```bash
grep kirim logs/run-*.log | tail          # ringkasan tiap run
wc -l state/sent-urls.txt                 # sudah berapa link terkirim
wc -l state/pending-urls.txt              # sisa antrean; 0 baris = beres

# Lihat apa yang akan dikirim tanpa benar-benar mengirim:
.venv/bin/python deploy/submit-links.py hasil/links-all-*.txt --dry-run

# Kirim ulang satu file hasil secara manual (yang sudah pernah terkirim tetap dilewati):
.venv/bin/python deploy/submit-links.py hasil/links-all-20260831-1100.txt
```

Kalau memang perlu mengirim ulang semuanya dari nol, hapus riwayatnya:
`rm state/sent-urls.txt`.

## Catatan penting

- **Run terjadwal jalan headless dan melewati CAPTCHA.** Defaultnya
  `ON_CAPTCHA=skip`, karena tidak ada yang menyelesaikan CAPTCHA jam 3 pagi —
  menunggu `CAPTCHA_WAIT_TIMEOUT` (120 detik) per halaman hanya menghabiskan
  jatah jadwal. Halaman yang kena CAPTCHA dilewati, sisanya tetap terkumpul.
- **Menekan frekuensi CAPTCHA** lebih penting daripada menanganinya: `MAX_PAGES=5`
  dan profil browser persisten (`.browser_profile/`) adalah dua pengaruh
  terbesar. Kalau hasil terus kosong, jalankan sekali manual sambil ditunggui:

  ```bash
  cd ~/linktaker-google
  HEADED=1 ON_CAPTCHA=headed ./deploy/run-linktaker.sh
  ```

  Selesaikan CAPTCHA-nya sekali; tiketnya tersimpan di `.browser_profile/` dan
  ikut terpakai oleh run terjadwal berikutnya. Kalau profil itu sendiri sudah
  ter-flag, jalankan sekali dengan `--fresh-profile`.
- **`xvfb` hanya untuk mode berjendela tanpa desktop.** Setelan default tidak
  memerlukannya. Kalau Anda menyetel `HEADED=1` atau `ON_CAPTCHA=headed` dari
  cron/ssh, script akan minta `sudo apt install -y xvfb` dan berhenti.
- **Output tidak menumpuk sendiri.** `cli.py` menulis output dengan mode `"w"`,
  jadi script memberi nama file bertimestamp di `hasil/`. Untuk menggabungkan
  seluruh hasil unik: `cat hasil/links-*.txt | sort -u > semua-link.txt`.
- **Jangan copy `.browser_profile/`** dari laptop Windows. Profil itu berisi
  cookie dan fingerprint yang terikat mesin; biarkan dibuat ulang di Linux.
