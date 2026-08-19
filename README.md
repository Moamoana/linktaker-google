# LinkTaker Google

> **Google Search Result Link Extractor** — Tool otomatis untuk mengekstrak URL dari hasil pencarian Google secara massal, dengan dukungan anti-deteksi, bypass CAPTCHA, dan multi-mode fetching.

---

## Daftar Isi

- [Tentang Project](#tentang-project)
- [Fitur Utama](#fitur-utama)
- [Arsitektur & Alur Kerja](#arsitektur--alur-kerja)
- [Struktur Kode (Package Modules)](#struktur-kode-package-modules)
- [Prasyarat](#prasyarat)
- [Instalasi](#instalasi)
- [Konfigurasi](#konfigurasi)
- [Penggunaan](#penggunaan)
- [File Input & Output](#file-input--output)
- [Mode Fetching](#mode-fetching)
- [Anti-Deteksi & Stealth](#anti-deteksi--stealth)
- [Proxy & Autentikasi](#proxy--autentikasi)
- [Google News RSS](#google-news-rss)
- [Filter Social Media](#filter-social-media)
- [Troubleshooting](#troubleshooting)
- [Lisensi](#lisensi)

---

## Tentang Project

**LinkTaker Google** adalah scraper Python yang dirancang untuk mengekstrak semua URL hasil pencarian dari Google Search secara otomatis. Tool ini mendukung:

- **Input simpel via keyword + tanggal** — cukup tulis kata kunci dan filter tanggal di `keywords.txt`, tidak perlu menyusun URL Google secara manual
- **Paginasi otomatis** — menelusuri halaman 1 hingga N dari hasil pencarian
- **Multi-mode fetching** — `curl_cffi`, `Playwright` (headless browser), atau kombinasi keduanya
- **Anti-bot detection** — fingerprint browser realistis, stealth mode, dan Cloudflare bypass
- **CAPTCHA handling** — deteksi otomatis + jeda manual untuk penyelesaian CAPTCHA
- **Google News RSS** — alternatif tanpa CAPTCHA untuk pencarian berita
- **AMP stripping** — membersihkan URL dari artefak AMP Google
- **Filter social media** — otomatis mengecualikan 40+ domain media sosial
- **Struktur modular** — kode dipecah jadi package Python (`linktaker/`), bukan satu file raksasa, supaya gampang dikembangkan per fitur

---

## Fitur Utama

| Fitur | Deskripsi |
|---|---|
| **Keyword + Date Input** | Cukup isi `keywords.txt` (`keyword \| date_filter \| mode`) — script yang membangun URL Google-nya |
| **Multi-mode Fetch** | `curl` (cepat), `playwright` (akurat), `auto` (fallback otomatis) |
| **Browser Fingerprinting** | Menggunakan `browserforge` untuk generate fingerprint browser yang realistis |
| **Stealth Mode** | `playwright-stealth` menyembunyikan tanda-tanda bot/automation |
| **Cloudflare Bypass** | `cloudscraper` + `curl_cffi` impersonation untuk melewati proteksi Cloudflare |
| **CAPTCHA Handling** | Deteksi CAPTCHA otomatis + waktu tunggu manual hingga 120 detik |
| **Google News RSS** | Fallback RSS feed untuk pencarian berita (tanpa CAPTCHA) |
| **AMP Stripping** | Membersihkan `amp.`, `/amp/`, dan query param AMP dari URL |
| **Social Media Filter** | Otomatis mengecualikan 40+ platform media sosial |
| **Proxy Rotation** | Dukungan rotasi proxy untuk menghindari rate limiting |
| **Parallel Processing** | Multi-thread worker untuk mode `curl`/`auto` |
| **Batch Processing** | Proses banyak keyword/URL pencarian sekaligus dari `keywords.txt` atau `url.txt` |
| **Auto Retry** | Retry otomatis hingga 3x untuk halaman yang gagal |
| **Modular Package** | Kode terpecah per tanggung jawab (`browser.py`, `fetchers.py`, `keywords.py`, dst.) di dalam `linktaker/` |

---

## Arsitektur & Alur Kerja

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│ keywords.txt│────▶│  linktaker/  │────▶│   output.txt     │
│  / url.txt  │     │   (package)  │     │ (extracted links) │
└─────────────┘     └──────┬───────┘     └──────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ curl_cffi│ │Playwright│ │ RSS Feed │
        │  (fast)  │ │ (browser)│ │  (news)  │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             ▼            ▼            ▼
        ┌─────────────────────────────────────┐
        │  BeautifulSoup HTML Parser          │
        │  ├── Extract Google result links    │
        │  ├── Filter social media            │
        │  ├── Strip AMP artifacts            │
        │  └── Deduplicate URLs               │
        └─────────────────────────────────────┘
```

---

## Struktur Kode (Package Modules)

Sejak refactor, `linktaker.py` (dulu 1 file ~1000 baris) sudah dipecah jadi package `linktaker/` — setiap file punya satu tanggung jawab, supaya kontributor bisa kerja di modul yang berbeda tanpa saling tabrakan:

| Modul | Tanggung Jawab | Bergantung Pada |
|---|---|---|
| `deps.py` | Import dependency opsional (`cloudscraper`, `playwright`, `feedparser`, `browserforge`) + flag `*_AVAILABLE` | — |
| `config.py` | Semua konstanta (path file, timeout, `FETCH_MODE`, daftar domain sosmed, dll) | — |
| `url_utils.py` | Strip AMP, filter social media, validasi & parsing link hasil Google | `config` |
| `browser.py` | `BrowserManager` — lifecycle browser Playwright, deteksi CAPTCHA, paginasi klik "Next" | `config`, `deps`, `url_utils` |
| `news_rss.py` | Decode/bangun/fetch Google News RSS | `config`, `deps`, `url_utils` |
| `keywords.py` | Parsing `keywords.txt` + membangun URL Google dari keyword & filter tanggal | — |
| `io_utils.py` | Baca `url.txt`, `proxies.txt`, `auth.json` | `config` |
| `fetchers.py` | Fetch via `curl_cffi`/`cloudscraper`, orkestrasi per-URL (`process_one_url`) | `config`, `deps`, `browser`, `news_rss`, `url_utils` |
| `cli.py` | `main()` — merangkai semua modul di atas jadi alur end-to-end | Semua modul di atas |
| `__main__.py` | Entry point untuk `python -m linktaker` | `cli` |

**Alur import**: `cli.py` ada di lapisan paling atas dan memanggil semua modul lain; modul-modul di bawahnya (`url_utils`, `keywords`, `io_utils`, dst.) tidak saling bergantung kecuali lewat `config`/`deps`, jadi aman diedit paralel di branch berbeda.

> **Untuk kontributor:** kalau mau nambah search engine baru (mis. issue Bing/Yahoo), pola yang konsisten adalah bikin modul fetcher baru (mis. `bing_fetcher.py`) yang meniru bentuk `fetchers.py`, lalu panggil dari `cli.py` — tidak perlu menyentuh `browser.py` atau `url_utils.py` kecuali ada parsing HTML yang beda.

---

## Prasyarat

- **Python** 3.8 atau lebih baru
- **pip** (Python package manager)
- **Koneksi internet** yang stabil

---

## Instalasi

### 1. Clone Repository

```bash
git clone https://github.com/Moamoana/linktaker-google.git
cd linktaker-google
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Chromium untuk Playwright

```bash
playwright install chromium
```

> **Catatan:** Langkah ini wajib jika menggunakan mode `playwright` atau `auto`.

### Instalasi Manual (alternatif)

Jika lebih suka install satu per satu:

```bash
pip install curl_cffi beautifulsoup4 cloudscraper playwright playwright-stealth browserforge feedparser
playwright install chromium
```

---

## Konfigurasi

Semua konfigurasi dilakukan langsung di dalam file [`linktaker/config.py`](linktaker/config.py):

### File Paths

| Variable | Default | Deskripsi |
|---|---|---|
| `KEYWORDS_FILE` | `"keywords.txt"` | File berisi keyword + filter tanggal (satu per baris) — lebih simpel, tidak perlu menyusun URL Google secara manual |
| `URLS_FILE` | `"url.txt"` | File berisi URL pencarian Google (satu per baris), digunakan sebagai fallback jika `keywords.txt` tidak ada |
| `OUT_FILE` | `"output.txt"` | File output untuk menyimpan link hasil ekstraksi |
| `PROXIES_FILE` | `"proxies.txt"` | File berisi daftar proxy |
| `AUTH_FILE` | `"auth.json"` | File kredensial autentikasi (opsional) |

### Pengaturan Scraping

| Variable | Default | Deskripsi |
|---|---|---|
| `MAX_PAGES_PER_SEARCH` | `10` | Jumlah maksimum halaman hasil pencarian per URL |
| `WAIT_SEC` | `20` | Timeout request dalam detik |
| `PARALLEL_WORKERS` | `5` | Jumlah thread paralel (mode `curl`/`auto`) |
| `CONSECUTIVE_EMPTY_PAGES` | `2` | Stop setelah N halaman berturut-turut tanpa link baru |
| `RETRY_FAILED_PAGES` | `3` | Jumlah retry untuk halaman yang gagal |
| `CAPTCHA_WAIT_TIMEOUT` | `120` | Waktu tunggu (detik) untuk user menyelesaikan CAPTCHA |

### Pengaturan Mode

| Variable | Default | Deskripsi |
|---|---|---|
| `FETCH_MODE` | `"playwright"` | Mode fetching: `"curl"`, `"playwright"`, atau `"auto"` |
| `USE_PROXY` | `False` | Aktifkan/nonaktifkan rotasi proxy |
| `USE_CLOUDFLARE_BYPASS` | `True` | Aktifkan bypass Cloudflare via cloudscraper |
| `USE_JAVASCRIPT_RENDERING` | `True` | Aktifkan rendering JavaScript |
| `USE_GOOGLE_RSS` | `False` | Aktifkan Google News RSS sebagai fallback |
| `RSS_DECODE_DELAY` | `2` | Delay (detik) antar decoding URL RSS |
| `RUN_BATCH` | `True` | Jalankan `scrape-onm-list.bat` setelah selesai |

---

## Penggunaan

### Langkah 1: Siapkan File Input

Ada dua cara menyiapkan input pencarian. Jika keduanya ada, `keywords.txt` diprioritaskan.

#### Opsi A — `keywords.txt` (Direkomendasikan, Paling Simpel)

Cukup isi **keyword** dan **tanggal**, tidak perlu menyusun URL Google secara manual:

```text
# keyword | date_filter | mode
teknologi indonesia | w
startup unicorn indonesia | d
artificial intelligence news | 2024-01-01..2024-06-30 | web
```

- **keyword** (wajib): kata kunci pencarian.
- **date_filter** (opsional):
  - `h` / `d` / `w` / `m` / `y` — filter relatif: 1 jam / 1 hari / 1 minggu / 1 bulan / 1 tahun terakhir.
  - `YYYY-MM-DD..YYYY-MM-DD` — rentang tanggal spesifik (bisa salah satu sisi dikosongkan, mis. `2024-01-01..` atau `..2024-06-30`).
  - Kosongkan untuk semua waktu.
- **mode** (opsional): `nws` (Google News, default) atau `web` (pencarian web biasa).

Script otomatis membangun URL pencarian Google (`q`, `tbm`, `tbs`, atau operator `after:`/`before:`) dari baris ini.

#### Opsi B — `url.txt` (Manual/Lanjutan)

Buat file `url.txt` berisi URL pencarian Google yang sudah jadi:

```text
https://www.google.com/search?q=teknologi+indonesia&tbm=nws
https://www.google.com/search?q=startup+unicorn+indonesia&tbs=qdr:w
https://www.google.com/search?q=artificial+intelligence+news&tbm=nws&tbs=qdr:d
```

> **Tips:** Baris yang diawali `#` akan diabaikan (komentar), berlaku untuk kedua file.

### Langkah 2: Jalankan Script

```bash
python -m linktaker
```

### Langkah 3: Lihat Hasil

Semua link yang berhasil diekstrak tersimpan di `output.txt`:

```text
https://example.com/article/1
https://contoh.co.id/berita/2
https://another-site.com/news/3
```

---

## File Input & Output

### `keywords.txt` (Input — Direkomendasikan)

File berisi keyword + filter tanggal, satu entri per baris (`keyword | date_filter | mode`):

```text
# Pencarian berita teknologi, 1 minggu terakhir
teknologi indonesia | w

# Pencarian web biasa, rentang tanggal spesifik
python tutorial | 2024-01-01..2024-06-30 | web
```

### `url.txt` (Input — Alternatif Manual)

File berisi URL pencarian Google yang sudah jadi, satu URL per baris. Dipakai jika `keywords.txt` tidak ditemukan:

```text
# Pencarian berita teknologi
https://www.google.com/search?q=tech+news&tbm=nws

# Pencarian web biasa
https://www.google.com/search?q=python+tutorial
```

### `output.txt` (Output)

File hasil berisi semua URL unik yang ditemukan, sudah dibersihkan dari AMP dan di-sort:

```text
https://example.com/article-1
https://example.com/article-2
```

### `proxies.txt` (Opsional)

Daftar proxy untuk rotasi:

```text
http://proxy1.example.com:8080
http://proxy2.example.com:8080
socks5://proxy3.example.com:1080
```

### `auth.json` (Opsional)

Kredensial autentikasi dalam format JSON:

```json
{
    "username": "user123",
    "password": "pass456"
}
```

---

## Mode Fetching

### 1. `"playwright"` (Default — Paling Akurat)

- Membuka browser Chromium nyata (non-headless)
- Menavigasi ke halaman pencarian, lalu **klik tombol "Next"** untuk paginasi
- Mendeteksi dan menunggu penyelesaian CAPTCHA secara manual
- Dilengkapi stealth mode dan browser fingerprinting
- **Pro:** Paling akurat, bisa handle JavaScript dan CAPTCHA
- **Kontra:** Lebih lambat, butuh resource lebih banyak, sequential processing

### 2. `"curl"` (Paling Cepat)

- Menggunakan `curl_cffi` dengan browser impersonation
- Mendukung parallel processing dengan multi-thread
- Fallback ke `cloudscraper` jika mendeteksi Cloudflare challenge
- **Pro:** Cepat, ringan, bisa parallel
- **Kontra:** Lebih mudah terdeteksi, tidak bisa handle CAPTCHA interaktif

### 3. `"auto"` (Hybrid)

- Mulai dengan `curl_cffi` (cepat)
- Jika tidak mendapat link, otomatis beralih ke Playwright
- **Pro:** Keseimbangan antara kecepatan dan akurasi
- **Kontra:** Sedikit lebih kompleks

---

## Anti-Deteksi & Stealth

LinkTaker menggunakan beberapa lapisan anti-deteksi:

### 1. Browser Fingerprinting (`browserforge`)

- Generate fingerprint browser desktop yang realistis
- User-Agent, locale, dan viewport disesuaikan
- Menolak fingerprint mobile secara otomatis (min. 1024px width)
- Retry hingga 5x untuk mendapatkan fingerprint desktop yang valid

### 2. Stealth Mode (`playwright-stealth`)

- Menyembunyikan properti `navigator.webdriver`
- Memodifikasi API deteksi automation
- Menginjeksi script anti-deteksi ke setiap halaman

### 3. Browser Impersonation (`curl_cffi`)

- Mengimitasi TLS fingerprint browser Chrome asli
- Header HTTP realistis termasuk `Sec-Fetch-*` headers
- 5 variasi User-Agent yang dirotasi secara random

### 4. Cloudflare Bypass (`cloudscraper`)

- Deteksi otomatis Cloudflare challenge page
- Bypass menggunakan `cloudscraper` sebagai fallback

### 5. Randomized Behavior

- Delay acak 1.5–3.5 detik antar halaman (mode curl)
- Delay acak 8–20 detik antar URL pencarian (mode playwright)
- URL pencarian di-shuffle secara acak (mode playwright)

---

## Proxy & Autentikasi

### Mengaktifkan Proxy

1. Set `USE_PROXY = True` di konfigurasi
2. Buat file `proxies.txt`:

```text
http://user:pass@proxy1.com:8080
socks5://proxy2.com:1080
```

3. Proxy akan dirotasi secara acak untuk setiap URL

### Autentikasi

1. Buat file `auth.json`:

```json
{
    "username": "your_username",
    "password": "your_password"
}
```

2. Kredensial akan digunakan secara otomatis untuk semua request

---

## Google News RSS

Fitur opsional untuk mengekstrak link berita melalui RSS feed (tanpa CAPTCHA):

### Mengaktifkan

Set `USE_GOOGLE_RSS = True` di konfigurasi.

### Cara Kerja

1. Mengonversi URL pencarian Google News (`tbm=nws`) ke format RSS
2. Mengambil feed RSS melalui `curl_cffi`
3. Mendecode URL redirect Google News (base64)
4. Fallback ke redirect following jika decode gagal
5. Rate limiting antar URL decode untuk menghindari blokir

### Batasan

- Hanya berfungsi untuk pencarian Google News (`tbm=nws`)
- Jumlah hasil terbatas (biasanya ~20–100 item)
- URL decode mungkin gagal untuk beberapa format baru

### Dukungan Filter Waktu

| Parameter Google | RSS `when` | Deskripsi |
|---|---|---|
| `tbs=qdr:h` | `1h` | 1 jam terakhir |
| `tbs=qdr:d` | `1d` | 1 hari terakhir |
| `tbs=qdr:w` | `7d` | 1 minggu terakhir |
| `tbs=qdr:m` | `30d` | 1 bulan terakhir |
| `tbs=qdr:y` | `1y` | 1 tahun terakhir |

---

## Filter Social Media

LinkTaker secara otomatis mengecualikan URL dari **40+ platform media sosial**, termasuk:

<details>
<summary>Klik untuk melihat daftar lengkap domain yang difilter</summary>

| Kategori | Domain |
|---|---|
| **Social Network** | facebook.com, fb.com, twitter.com, x.com, instagram.com, threads.net, bluesky.social, mastodon.social, myspace.com, nextdoor.com |
| **Video** | youtube.com, youtu.be, tiktok.com, vimeo.com, twitch.tv |
| **Messaging** | telegram.org, t.me, whatsapp.com, discord.com, signal.org, viber.com, wechat.com, kik.com, slack.com |
| **Professional** | linkedin.com |
| **Content** | reddit.com, medium.com, substack.com, tumblr.com, flipboard.com |
| **Developer** | github.com, gitlab.com, bitbucket.org, dev.to, stackoverflow.com |
| **Creative** | behance.net, dribbble.com, pinterest.com |
| **Q&A** | quora.com |
| **Funding** | patreon.com, kickstarter.com |
| **Other** | snapchat.com, omegle.com, lemmy.ml |

</details>

Hal ini memastikan output hanya berisi link artikel/website yang relevan.

---

## Troubleshooting

### `No input found`

Baik `keywords.txt` maupun `url.txt` tidak ditemukan. Buat salah satunya di direktori yang sama dengan folder `linktaker/` — `keywords.txt` untuk input keyword + tanggal, atau `url.txt` untuk URL pencarian Google yang sudah jadi.

### `playwright not installed`

```bash
pip install playwright
playwright install chromium
```

### `cloudscraper not installed`

```bash
pip install cloudscraper
```

### `browserforge not installed`

```bash
pip install browserforge
```

### `feedparser not installed`

```bash
pip install feedparser
```

### CAPTCHA Detected

Jika menggunakan mode `playwright`:
1. Browser Chromium akan terbuka
2. Jika muncul CAPTCHA, selesaikan secara manual di browser
3. Script akan mendeteksi otomatis setelah CAPTCHA diselesaikan (timeout: 120 detik)

### Tidak ada link yang diekstrak

- Pastikan format `keywords.txt` benar (`keyword | date_filter | mode`) atau URL di `url.txt` valid
- Coba ganti `FETCH_MODE` ke `"playwright"`
- Periksa koneksi internet
- Coba kurangi `MAX_PAGES_PER_SEARCH`

### Rate Limiting / IP Blocked

- Aktifkan proxy: set `USE_PROXY = True`
- Tambahkan proxy ke `proxies.txt`
- Tingkatkan delay antar request di konfigurasi

---

## Struktur Project

```
linktaker-google/
├── linktaker/            # Package utama — jalankan dengan `python -m linktaker`
│   ├── __init__.py
│   ├── __main__.py       # Entry point
│   ├── deps.py           # Optional-dependency imports (cloudscraper, playwright, dst.)
│   ├── config.py         # Semua konstanta konfigurasi
│   ├── browser.py        # BrowserManager (Playwright)
│   ├── url_utils.py      # Strip AMP, filter social media, parsing link Google
│   ├── news_rss.py       # Google News RSS decode/build/fetch
│   ├── keywords.py       # Keyword + date -> URL builder (keywords.txt)
│   ├── io_utils.py       # Baca url.txt / proxies.txt / auth.json
│   ├── fetchers.py       # curl_cffi, cloudscraper, orkestrasi fetch per URL
│   └── cli.py            # main() — orkestrasi end-to-end
├── requirements.txt     # Daftar dependencies Python
├── keywords.txt         # (Dibuat user) Input keyword + tanggal (direkomendasikan)
├── url.txt              # (Dibuat user, opsional) Input URL pencarian manual
├── output.txt           # (Auto-generated) Hasil link yang diekstrak
├── proxies.txt          # (Opsional) Daftar proxy
├── auth.json            # (Opsional) Kredensial autentikasi
└── README.md            # Dokumentasi ini
```

---

## Dependencies

| Package | Versi | Fungsi |
|---|---|---|
| `curl-cffi` | 0.14.0 | HTTP client dengan browser TLS impersonation |
| `beautifulsoup4` | 4.14.3 | HTML parser untuk ekstraksi link |
| `cloudscraper` | 1.2.71 | Cloudflare challenge bypass |
| `playwright` | 1.58.0 | Browser automation (Chromium) |
| `playwright-stealth` | 1.0.6 | Anti-detection untuk Playwright |
| `browserforge` | 1.2.4 | Generate fingerprint browser realistis |
| `feedparser` | 6.0.12 | Parser RSS/Atom feed |

---

## Lisensi

Project ini bersifat open-source. Silakan gunakan sesuai kebutuhan dengan mematuhi ketentuan yang berlaku.

---

<p align="center">
  <b>Jangan lupa beri star jika project ini bermanfaat!</b>
</p>
