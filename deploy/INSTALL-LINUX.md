# Menjalankan LinkTaker otomatis tiap 3 jam di laptop Linux

Contoh di bawah memakai user `nolimit` (Ubuntu, ThinkPad). Ganti kalau
username-nya beda.

## 1. Siapkan project di laptop Linux

```bash
sudo apt update
sudo apt install -y git
# xvfb hanya perlu kalau Anda mau menjalankan mode berjendela tanpa desktop
# (HEADED=1 atau ON_CAPTCHA=headed). Setelan default tidak membutuhkannya.
# sudo apt install -y xvfb

cd ~
git clone https://github.com/Moamoana/linktaker-google.git
cd linktaker-google

conda create -n linktaker python=3.12 -y
conda run -n linktaker pip install -r requirements.txt
conda run -n linktaker playwright install chromium
sudo $(conda run -n linktaker which playwright) install-deps chromium
```

> Kalau `conda` belum ada di PATH untuk shell non-interaktif, jalankan sekali
> `conda init bash` lalu buka ulang terminal.

Script pemanggil tidak memakai `conda activate` — itu butuh shell interaktif dan
tidak tersedia di cron/systemd. Sebagai gantinya ia memanggil interpreter env
secara langsung. Cari path-nya:

```bash
conda run -n linktaker python -c "import sys; print(sys.executable)"
# contoh keluaran: /home/nolimit/miniconda3/envs/linktaker/bin/python
```

Lalu set di `deploy/linktaker.service` (dan saat tes manual):

```
Environment=PYTHON_BIN=/home/nolimit/miniconda3/envs/linktaker/bin/python
```

`keywords.txt` tidak ikut ke repo (di-`.gitignore`), jadi salin manual dari
laptop Windows lalu taruh di `~/linktaker-google/keywords.txt`.

## 2. Tes manual dulu

```bash
cd ~/linktaker-google
./deploy/run-linktaker.sh
cat logs/run-*.log | tail -30
ls -l hasil/
```

Kalau ini belum menghasilkan link, jadwal otomatis juga tidak akan menghasilkan
apa-apa — perbaiki di sini dulu.

## 3. Pasang timer systemd (cara yang dipakai)

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
| `DAYS_BACK` | `1`     | `--from` = hari ini dikurangi sekian hari          |
| `MAX_PAGES` | `5`     | kosongkan untuk semua halaman (lebih rawan CAPTCHA)|
| `GEO`       | –       | `my`, `malaysia`, dst.                             |
| `PROXY`     | –       | `http://user:pass@host:2570`                       |
| `HEADED`    | `0`     | `1` = pakai jendela sepanjang run (butuh desktop/xvfb) |
| `ON_CAPTCHA`| `skip`  | `skip` untuk run terjadwal, `headed` kalau ditunggui   |
| `KEEP_DAYS` | `14`    | umur maksimum file hasil dan log                   |

```bash
ENGINE=google GEO=malaysia MAX_PAGES=3 ./deploy/run-linktaker.sh
```

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
