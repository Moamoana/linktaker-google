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
- [Search Engine: Google & Bing](#search-engine-google--bing)
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

**LinkTaker Google** adalah scraper Python yang dirancang untuk mengekstrak semua URL hasil pencarian dari Google Search maupun Bing Search secara otomatis. Tool ini mendukung:

- **Input simpel: cukup keyword** — file txt hanya berisi kata kunci; engine, tanggal, sort, jumlah halaman, dan proxy diatur lewat argumen CLI
- **Dua search engine** — Google (default) atau Bing lewat `--engine bing`, dengan alur crawl yang sama
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
| **Keyword Input (txt)** | Cukup isi file txt dengan **keyword saja** (satu per baris) — script yang membangun URL search engine-nya |
| **Multi Engine** | Google (default) dan Bing — `--engine bing`, satu alur crawl untuk keduanya |
| **CLI Flags** | `--engine`, `--input`, `--from`, `--until`, `--sort`, `--output`, `--max-pages`, `--proxy`, `--mode` |
| **Multi-mode Fetch** | `curl` (cepat), `playwright` (akurat), `auto` (fallback otomatis) |
| **Browser Fingerprinting** | Menggunakan `browserforge` untuk generate fingerprint browser yang realistis |
| **Stealth Mode** | `playwright-stealth` menyembunyikan tanda-tanda bot/automation |
| **Cloudflare Bypass** | `cloudscraper` + `curl_cffi` impersonation untuk melewati proteksi Cloudflare |
| **CAPTCHA Handling** | Deteksi CAPTCHA otomatis + waktu tunggu manual hingga 120 detik |
| **Google News RSS** | Fallback RSS feed untuk pencarian berita (tanpa CAPTCHA) |
| **AMP Stripping** | Membersihkan `amp.`, `/amp/`, dan query param AMP dari URL |
| **Social Media Filter** | Otomatis mengecualikan 40+ platform media sosial |
| **Filter Link Internal** | Link internal search engine dan iklan (mis. `bing.com/aclick`) tidak ikut tersimpan |
| **Bing Redirect Decode** | Membongkar pembungkus `bing.com/ck/a?...&u=a1<base64>` jadi URL aslinya |
| **Proxy** | Proxy manual lewat `--proxy` (mendukung `user:password@host:port`), atau rotasi dari `proxies.txt` |
| **Parallel Processing** | Multi-thread worker untuk mode `curl`/`auto` |
| **Batch Processing** | Proses banyak keyword sekaligus dari satu file txt (atau `url.txt`) |
| **Auto Retry** | Retry otomatis hingga 3x untuk halaman yang gagal |
| **Modular Package** | Kode terpecah per tanggung jawab (`browser.py`, `fetchers.py`, `keywords.py`, dst.) di dalam `linktaker/` |

---

## Arsitektur & Alur Kerja

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  --input    │────▶│  linktaker/  │────▶│   --output       │
│ (keyword)   │     │   (package)  │     │ (extracted links) │
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
        │  ├── Extract Google / Bing links    │
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
| `bing.py` | URL pencarian Bing (tanggal & sort), paginasi `first=`, decode redirect `ck/a`, parsing link Bing | `config`, `url_utils` |
| `engines.py` | Adapter `GOOGLE`/`BING` — semua yang berbeda antar engine (URL, selector hasil, tombol next, penanda CAPTCHA) | `bing`, `keywords`, `url_utils` |
| `browser.py` | `BrowserManager` — lifecycle browser Playwright, deteksi CAPTCHA, paginasi (klik "Next" untuk Google, navigasi URL untuk Bing) | `config`, `deps`, `engines` |
| `news_rss.py` | Decode/bangun/fetch Google News RSS | `config`, `deps`, `url_utils` |
| `keywords.py` | Baca file keyword + bangun URL Google dari keyword, `--from`/`--until`, dan `--sort` | — |
| `io_utils.py` | Baca `url.txt`, `proxies.txt`, `auth.json` | `config` |
| `fetchers.py` | Fetch via `curl_cffi`/`cloudscraper`, orkestrasi per-URL (`process_one_url`) | `config`, `deps`, `browser`, `engines`, `news_rss` |
| `cli.py` | `main()` — merangkai semua modul di atas jadi alur end-to-end | Semua modul di atas |
| `cli.py` (argparse) | Definisi semua flag CLI (`build_parser`, `parse_args`) | `config`, `keywords` |
| `__main__.py` | Entry point untuk `python -m linktaker` | `cli` |
| `linktaker.py` (root) | Entry point untuk `python linktaker.py` | `cli` |

**Alur import**: `cli.py` ada di lapisan paling atas dan memanggil semua modul lain; modul-modul di bawahnya (`url_utils`, `keywords`, `io_utils`, dst.) tidak saling bergantung kecuali lewat `config`/`deps`, jadi aman diedit paralel di branch berbeda.

> **Untuk kontributor:** kalau mau nambah search engine baru (mis. Yahoo/DuckDuckGo), ikuti pola Bing: bikin satu modul berisi URL builder + parser link engine tersebut (contoh `bing.py`), lalu daftarkan sebagai `Engine` baru di `engines.py`. `fetchers.py` dan `browser.py` tidak perlu disentuh — keduanya hanya membaca field dari objek `Engine`.

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

Nilai default ada di [`linktaker/config.py`](linktaker/config.py). Sebagian besar bisa ditimpa lewat argumen CLI (lihat [Penggunaan](#penggunaan)) tanpa mengedit file:

### File Paths

| Variable | Default | Deskripsi |
|---|---|---|
| `KEYWORDS_FILE` | `"keywords.txt"` | Default `--input` — file berisi keyword saja, satu per baris |
| `URLS_FILE` | `"url.txt"` | URL pencarian Google siap pakai (satu per baris), fallback kalau file `--input` tidak ada |
| `OUT_FILE` | `"output.txt"` | Default `--output` — file untuk menyimpan link hasil ekstraksi |
| `PROXIES_FILE` | `"proxies.txt"` | Daftar proxy, dipakai hanya kalau `--proxy` tidak diberikan |
| `AUTH_FILE` | `"auth.json"` | File kredensial autentikasi (opsional) |

### Pengaturan Scraping

| Variable | Default | Deskripsi |
|---|---|---|
| `MAX_PAGES_PER_SEARCH` | `None` | Default `--max-pages`. `None` = ambil semua halaman |
| `DEFAULT_SORT` | `"relevance"` | Default `--sort` (`relevance` atau `latest`) |
| `DEFAULT_ENGINE` | `"google"` | Default `--engine` (`google` atau `bing`) |
| `WAIT_SEC` | `20` | Timeout request dalam detik |
| `PARALLEL_WORKERS` | `5` | Jumlah thread paralel (mode `curl`/`auto`) |
| `CONSECUTIVE_EMPTY_PAGES` | `2` | Stop setelah N halaman berturut-turut tanpa link baru |
| `RETRY_FAILED_PAGES` | `3` | Jumlah retry untuk halaman yang gagal |
| `CAPTCHA_WAIT_TIMEOUT` | `120` | Waktu tunggu (detik) untuk user menyelesaikan CAPTCHA |

### Pengaturan Mode

| Variable | Default | Deskripsi |
|---|---|---|
| `FETCH_MODE` | `"playwright"` | Mode fetching: `"curl"`, `"playwright"`, atau `"auto"` |
| `USE_CLOUDFLARE_BYPASS` | `True` | Aktifkan bypass Cloudflare via cloudscraper |
| `USE_JAVASCRIPT_RENDERING` | `True` | Aktifkan rendering JavaScript |
| `USE_GOOGLE_RSS` | `False` | Aktifkan Google News RSS sebagai fallback |
| `RSS_DECODE_DELAY` | `2` | Delay (detik) antar decoding URL RSS |

---

## Penggunaan

### Langkah 1: Siapkan File Keyword

Buat file txt yang **isinya keyword saja**, satu keyword per baris:

```text
# keyword1.txt — baris diawali # diabaikan
kpk
pelni
banjir jakarta
```

Tidak perlu menulis tanggal, mode, atau URL Google di dalam file — semuanya diatur lewat argumen CLI.

### Langkah 2: Jalankan Script

```bash
python linktaker.py --input keyword1.txt --from 2026-08-08 --until 2026-08-16 --sort latest --output hasil.txt --max-pages 2
```

Bentuk paling singkat (tanpa tanggal, langsung search apa adanya dari Google):

```bash
python linktaker.py --input keyword1.txt
```

Crawl dari Bing, bukan Google:

```bash
python linktaker.py --engine bing --input keyword1.txt --from 2026-08-08 --until 2026-08-16 --sort latest
```

Bisa juga dijalankan sebagai module:

```bash
python -m linktaker --input keyword1.txt
```

### Daftar Argumen

| Argumen | Wajib | Default | Deskripsi |
|---|---|---|---|
| `--engine {google,bing}` | tidak | `google` | Search engine yang di-crawl |
| `--input FILE` | tidak | `keywords.txt` | File txt berisi keyword, satu per baris |
| `--from YYYY-MM-DD` | tidak | — | Ambil hasil mulai tanggal ini. Tanpa `--from`/`--until`, pencarian jalan tanpa filter tanggal |
| `--until YYYY-MM-DD` | tidak | — | Ambil hasil sampai tanggal ini |
| `--sort {latest,relevance}` | tidak | `relevance` | `latest` = urut terbaru, `relevance` = urutan default engine. Lihat [catatan Bing](#search-engine-google--bing) |
| `--output FILE` | tidak | `output.txt` | File tujuan hasil link |
| `--max-pages N` | tidak | semua | Maksimum halaman hasil yang di-crawl per keyword |
| `--proxy URL` | tidak | tanpa proxy | Proxy manual, mis. `http://user:password@proxycrawler.dashboard.nolimit.id:2570` |
| `--mode {nws,web}` | tidak | `nws` (google), `web` (bing) | `nws` = pencarian berita, `web` = pencarian web biasa |
| `-h`, `--help` | — | — | Tampilkan bantuan |

Contoh lengkap dengan proxy:

```bash
python linktaker.py --input keyword1.txt --from 2026-08-08 --until 2026-08-16 \
    --sort latest --output hasil.txt --max-pages 2 \
    --proxy http://user:password@proxycrawler.dashboard.nolimit.id:2570
```

Setiap keyword diubah jadi URL pencarian, contoh untuk `kpk` dengan perintah di atas:

```text
https://www.google.com/search?q=kpk&tbm=nws&tbs=cdr:1,cd_min:8/8/2026,cd_max:8/16/2026,sbd:1
```

Dengan `--engine bing`, URL yang dibangun:

```text
https://www.bing.com/search?q=kpk&filters=ex1%3A%22ez5_20673_20681%22
```

### Langkah 3: Lihat Hasil

Semua link yang berhasil diekstrak tersimpan di file `--output` (default `output.txt`):

```text
https://example.com/article/1
https://contoh.co.id/berita/2
https://another-site.com/news/3
```

---

## Search Engine: Google & Bing

Alur crawl-nya sama untuk kedua engine — yang berbeda hanya cara membangun URL, selector hasil, dan cara pindah halaman. Semuanya terkumpul di [`linktaker/engines.py`](linktaker/engines.py).

```bash
python linktaker.py --engine bing --input keyword1.txt --from 2026-08-08 --until 2026-08-16 --sort latest
```

### Perbedaan Kemampuan

| | Google | Bing (`--mode web`) | Bing (`--mode nws`) |
|---|---|---|---|
| Vertical | Google News (`tbm=nws`) / web | Bing Search | Bing News |
| `--from` / `--until` | ✅ `tbs=cdr:1,cd_min,cd_max` | ✅ `filters=ex1:"ez5_<hari>_<hari>"` | ❌ diabaikan Bing |
| `--sort latest` | ✅ `tbs=…,sbd:1` | ❌ tidak ada urutan by-date | ✅ `qft=sortbydate="1"` |
| Paginasi | klik tombol **Next** (`#pnnext`) | navigasi URL `&first=11,21,…` | navigasi URL `&first=11,21,…` |
| Default `--mode` | `nws` | `web` | — |

Keterbatasan pada kolom Bing itu datang dari Bing sendiri, bukan dari tool ini: rentang tanggal kustom hanya berlaku di Bing Search, sedangkan urutan terbaru hanya ada di Bing News. Kalau Anda meminta kombinasi yang tidak didukung, script mencetak catatan di awal run, misalnya:

```text
Note: Bing web search has no date ordering — use --mode nws for newest-first results.
```

Hasil tetap diambil, hanya bagian yang tidak didukung itu saja yang diabaikan engine-nya.

### Yang Dibuang dari Hasil Bing

- Link internal Bing (`bing.com`, `bing.net`, `go.microsoft.com`, `login.live.com`)
- Iklan — hanya `li.b_algo` (hasil organik) yang dibaca, `li.b_ad` dilewati
- Redirect `https://www.bing.com/ck/a?…&u=a1<base64>` dibongkar dulu jadi URL asli; kalau gagal di-decode, link dibuang
- Social media dan URL tidak valid — sama seperti Google

---

## File Input & Output

### File Keyword (Input — via `--input`)

Isinya **keyword saja**, satu per baris. Baris kosong dan baris diawali `#` diabaikan, keyword duplikat otomatis dibuang:

```text
# keyword1.txt
teknologi indonesia
startup unicorn indonesia
python tutorial
```

> Format lama `keyword | date_filter | mode` masih bisa dibaca — bagian setelah `|` diabaikan, karena tanggal & mode sekarang datang dari CLI (`--from`, `--until`, `--sort`, `--mode`).

### `url.txt` (Input — Alternatif Manual)

File berisi URL pencarian Google yang sudah jadi, satu URL per baris. Dipakai hanya jika file `--input` tidak ditemukan:

```text
# Pencarian berita teknologi
https://www.google.com/search?q=tech+news&tbm=nws

# Pencarian web biasa
https://www.google.com/search?q=python+tutorial
```

### File Output (via `--output`, default `output.txt`)

File hasil berisi semua URL unik yang ditemukan, sudah dibersihkan dari AMP dan di-sort:

```text
https://example.com/article-1
https://example.com/article-2
```

### `proxies.txt` (Opsional)

Daftar proxy untuk rotasi. Hanya dipakai kalau `--proxy` **tidak** diberikan:

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

### Menggunakan Proxy

Cara paling langsung — lewat argumen `--proxy` (default: tanpa proxy):

```bash
python linktaker.py --input keyword1.txt --proxy http://user:password@proxycrawler.dashboard.nolimit.id:2570
```

Proxy dipakai baik oleh mode `curl` maupun `playwright`. Kredensial `user:password` otomatis dipisah dari host karena Chromium tidak menerima kredensial yang menempel di URL proxy.

Alternatif — rotasi dari file. Kalau `--proxy` tidak diberikan dan `proxies.txt` ada, proxy diambil acak dari file itu:

```text
http://user:pass@proxy1.com:8080
socks5://proxy2.com:1080
```

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
- Rentang tanggal `--from`/`--until` belum didukung RSS (hanya filter relatif `qdr:*`)

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

### `Input file not found`

File yang ditunjuk `--input` tidak ada (default `keywords.txt`). Buat file txt berisi keyword (satu per baris) di direktori yang sama dengan folder `linktaker/`, atau arahkan `--input` ke lokasi lain. Sebagai fallback, `url.txt` berisi URL pencarian Google yang sudah jadi juga masih dibaca.

### `--from must be in YYYY-MM-DD format`

Tanggal harus ditulis lengkap, mis. `--from 2026-08-08`. `--from` juga tidak boleh lebih besar dari `--until`.

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

### Bing: `One last step / solve the challenge`

Bing menampilkan halaman challenge kalau lalu lintasnya dianggap mencurigakan. Script mendeteksinya dan menunggu Anda menyelesaikannya di jendela browser (timeout 120 detik), sama seperti CAPTCHA Google. Kalau sering muncul: kecilkan `--max-pages`, beri jeda antar run, atau pakai `--proxy`.

### CAPTCHA Detected

Jika menggunakan mode `playwright`:
1. Browser Chromium akan terbuka
2. Jika muncul CAPTCHA, selesaikan secara manual di browser
3. Script akan mendeteksi otomatis setelah CAPTCHA diselesaikan (timeout: 120 detik)

### Tidak ada link yang diekstrak

- Pastikan file `--input` berisi keyword (satu per baris) atau URL di `url.txt` valid
- Coba ganti `FETCH_MODE` ke `"playwright"` di `config.py`
- Rentang `--from`/`--until` mungkin terlalu sempit — coba jalankan tanpa keduanya
- Periksa koneksi internet
- Coba kecilkan `--max-pages`

### Rate Limiting / IP Blocked

- Pakai proxy: `--proxy http://user:password@host:2570`
- Atau tambahkan beberapa proxy ke `proxies.txt` untuk dirotasi
- Kecilkan `--max-pages` dan tingkatkan delay antar request di konfigurasi

---

## Struktur Project

```
linktaker-google/
├── linktaker.py          # Entry point — `python linktaker.py --input keyword1.txt`
├── linktaker/            # Package utama — bisa juga `python -m linktaker`
│   ├── __init__.py
│   ├── __main__.py       # Entry point
│   ├── deps.py           # Optional-dependency imports (cloudscraper, playwright, dst.)
│   ├── config.py         # Semua konstanta konfigurasi
│   ├── browser.py        # BrowserManager (Playwright)
│   ├── url_utils.py      # Strip AMP, filter social media, parsing link Google
│   ├── bing.py           # URL Bing, paginasi first=, decode redirect, parsing link Bing
│   ├── engines.py        # Adapter GOOGLE / BING untuk alur crawl bersama
│   ├── news_rss.py       # Google News RSS decode/build/fetch
│   ├── keywords.py       # Baca file keyword + builder URL Google (tanggal & sort)
│   ├── io_utils.py       # Baca url.txt / proxies.txt / auth.json
│   ├── fetchers.py       # curl_cffi, cloudscraper, orkestrasi fetch per URL
│   └── cli.py            # argparse + main() — orkestrasi end-to-end
├── requirements.txt     # Daftar dependencies Python
├── keywords.txt         # (Dibuat user) Input keyword — default `--input`
├── url.txt              # (Dibuat user, opsional) Input URL pencarian manual
├── output.txt           # (Auto-generated) Hasil link — default `--output`
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
