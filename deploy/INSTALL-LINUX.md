# Menjalankan LinkTaker otomatis tiap 3 jam di laptop Linux

Contoh di bawah memakai user `nolimit` (Ubuntu, ThinkPad). Ganti kalau
username-nya beda.

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
git clone https://github.com/Moamoana/linktaker-google.git
cd linktaker-google
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

## 7. Arahkan runner ke interpreter venv

Buka `deploy/linktaker.service`, sesuaikan baris `PYTHON_BIN` dengan username
Anda:

```
Environment=PYTHON_BIN=/home/nolimit/linktaker-google/.venv/bin/python
```

Cek dulu path-nya benar:

```bash
ls -l ~/linktaker-google/.venv/bin/python
```

## 8. Tes manual dulu

```bash
cd ~/linktaker-google
PYTHON_BIN=$HOME/linktaker-google/.venv/bin/python ./deploy/run-linktaker.sh
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
sudo loginctl enable-linger nolimit
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
0 */3 * * * /home/nolimit/linktaker-google/deploy/run-linktaker.sh >/dev/null 2>&1
```

Bedanya: cron **tidak** mengejar jadwal yang terlewat saat laptop mati atau
suspend, sedangkan `Persistent=true` di systemd timer mengejarnya. Untuk laptop,
systemd timer lebih tepat.

## Mengubah parameter crawl

Semua lewat environment variable, baik di `linktaker.service` maupun di depan
perintah manual:

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
