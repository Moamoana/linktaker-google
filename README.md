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
- [Search Engine: Google, Bing & Yahoo](#search-engine-google-bing--yahoo)
- [Pencarian per Negara (`--geo`)](#pencarian-per-negara---geo)
- [File Input & Output](#file-input--output)
- [Mode Fetching](#mode-fetching)
- [Tanggal Relatif](#tanggal-relatif)
- [Headless & CAPTCHA](#headless--captcha)
- [Anti-Deteksi & Stealth](#anti-deteksi--stealth)
- [Proxy & Autentikasi](#proxy--autentikasi)
- [Google News RSS](#google-news-rss)
- [Filter Berita (News Filter)](#filter-berita-news-filter)
- [Filter Social Media](#filter-social-media)
- [Troubleshooting](#troubleshooting)
- [Lisensi](#lisensi)

---

## Tentang Project

**LinkTaker Google** adalah scraper Python yang dirancang untuk mengekstrak semua URL hasil pencarian dari Google, Bing, maupun Yahoo secara otomatis. Tool ini mendukung:

- **Input simpel: cukup keyword** — file txt hanya berisi kata kunci; engine, tanggal, sort, jumlah halaman, dan proxy diatur lewat argumen CLI
- **Tiga search engine** — Google (default), Bing, atau Yahoo lewat `--engine`, dengan alur crawl yang sama
- **Pilih tab pencarian** — tab **Semua** (default), tab **Berita**, atau keduanya sekaligus lewat `--mode`
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
| **Multi Engine** | Google (default), Bing, dan Yahoo — `--engine`, satu alur crawl untuk ketiganya |
| **Gabungan Semua Engine** | `--engine all` menjalankan Google → Yahoo → Bing berurutan, hasilnya digabung ke satu file `--output` |
| **Tab Semua / Berita** | `--mode web` (tab Semua, default), `--mode nws` (tab Berita), `--mode both` (gabungan) — tab Semua menangkap portal baru yang belum diakui Google sebagai news site |
| **Filter Berita** | `--news-filter` menjaga output hanya berisi artikel berita: `smart` (buang host non-berita + URL non-artikel), `strict` (hanya penerbit di `news_domains.txt`), `off` |
| **Pencarian per Negara** | `--geo my` / `--geo malaysia` — cari seolah-olah dari negara tertentu. Google dapat `gl=`, Bing `cc=`, Yahoo situs regionalnya. Lihat [Pencarian per Negara](#pencarian-per-negara---geo) |
| **Tanggal Relatif** | `--from w` / `--from 7d` / `--from 3m` — dihitung ulang tiap run, jadi jadwal berkala tidak terkunci di rentang tanggal yang sama. Lihat [Tanggal Relatif](#tanggal-relatif) |
| **CLI Flags** | `--engine`, `--input`, `--from`, `--until`, `--sort`, `--geo`, `--output`, `--max-pages`, `--proxy`, `--mode`, `--news-filter`, `--news-domains`, `--headless`/`--headed`, `--on-captcha` |
| **Headless + Jendela Saat Perlu** | Crawl jalan tanpa jendela; jendela hanya dibuka saat kena CAPTCHA, lalu balik headless dan **lanjut dari halaman yang sama**. `--on-captcha skip` untuk run terjadwal. Lihat [Headless & CAPTCHA](#headless--captcha) |
| **Multi-mode Fetch** | `curl` (cepat), `playwright` (akurat), `auto` (fallback otomatis) |
| **Browser Fingerprinting** | Menggunakan `browserforge` untuk generate fingerprint browser yang realistis |
| **Stealth Mode** | `playwright-stealth` menyembunyikan tanda-tanda bot/automation |
| **Cloudflare Bypass** | `cloudscraper` + `curl_cffi` impersonation untuk melewati proteksi Cloudflare |
| **CAPTCHA Handling** | Deteksi CAPTCHA otomatis + waktu tunggu manual hingga 120 detik |
| **Google News RSS** | Fallback RSS feed untuk pencarian berita (tanpa CAPTCHA) |
| **AMP Stripping** | Membersihkan `amp.`, `/amp/`, dan query param AMP dari URL |
| **Social Media Filter** | Otomatis mengecualikan 40+ platform media sosial |
| **Laporan Penolakan** | Setiap run melaporkan host apa saja yang dibuang filter berita, supaya allowlist bisa ditumbuhkan |
| **Filter Link Internal** | Link internal search engine dan iklan (mis. `bing.com/aclick`) tidak ikut tersimpan |
| **Redirect Decode** | Membongkar pembungkus `bing.com/ck/a?...&u=a1<base64>` dan `r.search.yahoo.com/.../RU=<url>/RK=` jadi URL artikel aslinya |
| **Proxy** | Proxy manual lewat `--proxy` (mendukung `user:password@host:port`), atau rotasi dari `proxies.txt` |
| **Parallel Processing** | Multi-thread worker untuk mode `curl`/`auto` |
| **Batch Processing** | Proses banyak keyword sekaligus dari satu file txt (atau `url.txt`) |
| **Auto Retry** | Retry otomatis hingga 3x untuk halaman yang gagal |
| **Modular Package** | Kode terpecah per tanggung jawab di dalam `linktaker/`, dengan satu file per search engine di `linktaker/engines/` |

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
        │  ├── Extract search result links    │
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
| `url_utils.py` | Helper URL yang dipakai **semua** engine: strip AMP, filter social media, gerbang filter berita, validasi link | `config`, `news_filter` |
| `news_filter.py` | Menjaga output hanya berisi **artikel berita**: blocklist domain non-berita, aturan bentuk URL artikel, allowlist penerbit, laporan penolakan | — |
| `inputs.py` | Baca file keyword, `url.txt`, `proxies.txt`, `auth.json`, dan parsing tanggal CLI | `config` |
| `geo.py` | Tabel negara ISO 3166-1 + alias (`uk`, `usa`, `jerman`, `singapura`) — mengubah isi `--geo` jadi satu objek `Geo` yang dipakai semua engine | — |
| `engines/base.py` | Kontrak `Engine` — daftar field yang harus disediakan tiap engine | — |
| `engines/google.py` | URL Google (`tbs=cdr`/`sbd`, `gl=`/`hl=`), paginasi `start=`, parsing link, objek `GOOGLE` | `url_utils`, `base` |
| `engines/bing.py` | URL Bing (`filters=ez5`/`sortbydate`, `cc=`/`mkt=`), paginasi `first=`, decode redirect `ck/a`, objek `BING` | `url_utils`, `base` |
| `engines/yahoo.py` | URL Yahoo (`btf=`, host regional per negara), paginasi `b=`, decode redirect `/RU=`, objek `YAHOO` | `url_utils`, `base` |
| `engines/news_rss.py` | Decode/bangun/fetch Google News RSS (edisi mengikuti `--geo`) | `config`, `deps`, `geo`, `url_utils` |
| `engines/__init__.py` | Registry `ENGINES` + `get_engine()` | Semua modul engine |
| `browser.py` | `BrowserManager` — lifecycle browser Playwright, deteksi CAPTCHA, paginasi (klik "Next" atau navigasi URL, tergantung engine) | `config`, `deps`, `engines` |
| `fetchers.py` | Fetch via `curl_cffi`/`cloudscraper`, orkestrasi per-URL (`process_one_url`) | `config`, `deps`, `browser`, `engines` |
| `cli.py` | Argparse (`build_parser`, `parse_args`) + `main()` — merangkai semua modul jadi alur end-to-end | Semua modul di atas |
| `__main__.py` | Entry point untuk `python -m linktaker` | `cli` |
| `linktaker.py` (root) | Entry point untuk `python linktaker.py` | `cli` |

**Alur import**: `cli.py` ada di lapisan paling atas dan memanggil semua modul lain. Di bawahnya, `fetchers.py` dan `browser.py` tidak tahu-menahu soal engine mana yang dipakai — keduanya hanya membaca field dari objek `Engine`. Modul di dalam `engines/` tidak saling bergantung, jadi dua orang bisa menggarap engine berbeda tanpa bentrok.

> **Untuk kontributor:** menambah search engine baru (mis. DuckDuckGo) = **satu file + satu baris**:
>
> 1. Bikin `linktaker/engines/duckduckgo.py` meniru bentuk `bing.py` — URL builder, paginasi, parser link — lalu tutup dengan objek `Engine(...)` di bagian bawah file.
> 2. Tambahkan objek itu ke tuple di `linktaker/engines/__init__.py`.
>
> `--engine` otomatis menerima nama barunya, dan `fetchers.py`/`browser.py` tidak perlu disentuh sama sekali.

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
| `NEWS_DOMAINS_FILE` | `"news_domains.txt"` | Default `--news-domains` — allowlist penerbit berita |

### Pengaturan Scraping

| Variable | Default | Deskripsi |
|---|---|---|
| `MAX_PAGES_PER_SEARCH` | `None` | Default `--max-pages`. `None` = ambil semua halaman |
| `DEFAULT_SORT` | `"relevance"` | Default `--sort` (`relevance` atau `latest`) |
| `DEFAULT_ENGINE` | `"google"` | Default `--engine` (`google`, `bing`, atau `yahoo`) |
| `NEWS_FILTER` | `"smart"` | Default `--news-filter` (`smart`, `strict`, atau `off`) — lihat [Filter Berita](#filter-berita-news-filter) |
| `DEFAULT_GEO` | `None` | Default `--geo`. Isi kode negara (`"my"`) atau namanya (`"malaysia"`) kalau semua run memang menyasar satu negara. `None` = ikut lokasi browser — lihat [Pencarian per Negara](#pencarian-per-negara---geo) |
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

Crawl dari Bing atau Yahoo, bukan Google:

```bash
python linktaker.py --engine bing --input keyword1.txt --from 2026-08-08 --until 2026-08-16 --sort latest
python linktaker.py --engine yahoo --input keyword1.txt --from 2026-08-08 --until 2026-08-16
```

Atau jalankan ketiganya sekaligus (Google → Yahoo → Bing) ke satu file output gabungan:

```bash
python linktaker.py --engine all --input keyword1.txt --from 2026-08-08 --until 2026-08-16 --sort latest --mode both --output hasil.txt
```

Cari dari negara lain — kode ISO maupun nama negaranya, lihat [Pencarian per Negara](#pencarian-per-negara---geo):

```bash
python linktaker.py --input keyword1.txt --geo my
python linktaker.py --input keyword1.txt --geo malaysia
```

Bisa juga dijalankan sebagai module:

```bash
python -m linktaker --input keyword1.txt
```

### Daftar Argumen

| Argumen | Wajib | Default | Deskripsi |
|---|---|---|---|
| `--engine {google,bing,yahoo,all}` | tidak | `google` | Search engine yang di-crawl. `all` menjalankan Google → Yahoo → Bing berurutan dan menggabung hasilnya ke satu `--output` |
| `--input FILE` | tidak | `keywords.txt` | File txt berisi keyword, satu per baris |
| `--from DATE` | tidak | — | Ambil hasil mulai tanggal ini. Terima tanggal pasti (`2026-08-18`) maupun relatif (`w`, `7d`, `3m`). Tanpa `--from`/`--until`, pencarian jalan tanpa filter tanggal. Lihat [Tanggal Relatif](#tanggal-relatif) |
| `--until DATE` | tidak | — | Ambil hasil sampai tanggal ini. Format sama dengan `--from` |
| `--sort {latest,relevance}` | tidak | `relevance` | `latest` = urut terbaru, `relevance` = urutan default engine. Lihat [catatan per engine](#search-engine-google-bing--yahoo) |
| `--geo COUNTRY` | tidak | ikut lokasi browser | Cari seolah-olah dari negara ini. Terima kode ISO (`my`) maupun nama negara (`malaysia`, `jerman`). Lihat [Pencarian per Negara](#pencarian-per-negara---geo) |
| `--output FILE` | tidak | `output.txt` | File tujuan hasil link |
| `--max-pages N` | tidak | semua | Maksimum halaman hasil yang di-crawl per keyword |
| `--proxy URL` | tidak | tanpa proxy | Proxy manual, mis. `http://user:password@proxycrawler.dashboard.nolimit.id:2570` |
| `--mode {web,nws,both}` | tidak | `web` | `web` = tab **Semua/All**, `nws` = tab **Berita**, `both` = crawl kedua tab lalu digabung. Lihat [Tab pencarian](#tab-pencarian-semua-vs-berita) |
| `--news-filter {smart,strict,off}` | tidak | `smart` | Seberapa ketat output disaring jadi link berita saja. Lihat [Filter Berita](#filter-berita-news-filter) |
| `--news-domains FILE` | tidak | `news_domains.txt` | File allowlist penerbit, satu domain per baris |
| `--headless` / `--headed` | tidak | `--headless` | Jalan tanpa / dengan jendela browser. Lihat [Headless & CAPTCHA](#headless--captcha) |
| `--on-captcha {headed,skip}` | tidak | `headed` | Yang dilakukan run headless saat kena CAPTCHA. `skip` untuk run terjadwal |
| `-h`, `--help` | — | — | Tampilkan bantuan |

Contoh lengkap dengan proxy:

```bash
python linktaker.py --input keyword1.txt --from 2026-08-08 --until 2026-08-16 \
    --sort latest --output hasil.txt --max-pages 2 \
    --proxy http://user:password@proxycrawler.dashboard.nolimit.id:2570
```

Setiap keyword diubah jadi URL pencarian, contoh untuk `kpk` dengan perintah di atas:

```text
https://www.google.com/search?q=kpk&tbs=cdr:1,cd_min:8/8/2026,cd_max:8/16/2026,sbd:1
```

URL di atas adalah tab **Semua** (tanpa `tbm`). Dengan `--mode nws` keyword yang sama jadi
`…&q=kpk&tbm=nws&tbs=…` (tab Berita), dan `--mode both` membangun keduanya.

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

## Search Engine: Google, Bing & Yahoo

Alur crawl-nya sama untuk ketiga engine — yang berbeda hanya cara membangun URL, selector hasil, dan cara pindah halaman. Semuanya terkumpul satu file per engine di [`linktaker/engines/`](linktaker/engines/).

```bash
python linktaker.py --engine bing --input keyword1.txt --from 2026-08-08 --until 2026-08-16 --sort latest
```

### Menjalankan Semua Engine Sekaligus (`--engine all`)

```bash
python linktaker.py --engine all --input keyword1.txt --from 2026-08-08 --until 2026-08-16 --sort latest --mode both --output hasil.txt
```

Menjalankan Google, lalu Yahoo, lalu Bing secara berurutan dengan argumen yang sama (`--from`, `--until`, `--sort`, `--mode`, dll), dan menggabung semua link unik dari ketiganya ke satu file `--output`. Kalau `--mode` tidak diberikan, tiap engine tetap memakai default tab-nya masing-masing (`web` untuk Google/Bing, satu-satunya vertical untuk Yahoo). Berguna untuk sekali jalan mendapat cakupan maksimum tanpa menjalankan tiga perintah terpisah dan menggabung filenya secara manual.

### Perbedaan Kemampuan

| | Google | Bing (`--mode web`) | Bing (`--mode nws`) | Yahoo |
|---|---|---|---|---|
| Vertical | tab Semua (default) / tab Berita (`tbm=nws`) | Bing Search | Bing News | Yahoo Search |
| `--from` / `--until` | ✅ `tbs=cdr:1,cd_min,cd_max` | ✅ `filters=ex1:"ez5_<hari>_<hari>"` | ❌ diabaikan Bing | ⚠️ didekati dengan `btf=d/w/m` |
| `--sort latest` | ✅ `tbs=…,sbd:1` | ❌ tidak ada urutan by-date | ✅ `qft=sortbydate="1"` | ❌ tidak ada urutan by-date |
| Paginasi | klik tombol **Next** (`#pnnext`) | navigasi URL `&first=11,21,…` | navigasi URL `&first=11,21,…` | navigasi URL `&b=11,21,…` |
| Default `--mode` | `web` | `web` | — | `web` (nws tidak tersedia) |

### Tab Pencarian: Semua vs Berita

Google punya dua tab yang relevan, dan `--mode` memilih di antaranya:

| `--mode` | Tab | Kapan dipakai |
|---|---|---|
| `web` (default) | **Semua / All** — `https://www.google.com/search?q=…` | Cakupan terluas. Portal berita baru yang belum diakui Google sebagai *news source* tetap muncul di sini |
| `nws` | **Berita** — `…&tbm=nws` | Hasil lebih bersih (murni artikel), tapi terbatas pada portal yang sudah terdaftar sebagai news site |
| `both` | Semua + Berita | Crawl dua-duanya lalu gabung link-nya (duplikat otomatis hilang). Biayanya dua kali pencarian per keyword |

Filter tanggal (`--from`/`--until` → `tbs=cdr:1,…`) dan urutan terbaru (`--sort latest` → `sbd:1`)
berlaku sama di kedua tab, jadi tidak ada yang hilang saat pindah ke tab Semua.

```bash
# cakupan maksimum: tab Semua + tab Berita, rentang tanggal, urut terbaru
python linktaker.py --input keyword1.txt --mode both     --from 2026-08-08 --until 2026-08-16 --sort latest
```

Untuk Bing, `--mode both` juga berguna: Bing Search yang menghormati `--from`/`--until`
dan Bing News yang menghormati `--sort latest` di-crawl sekaligus. Untuk Yahoo tidak ada
efeknya — hanya ada satu vertical, jadi URL-nya di-crawl sekali saja.

Keterbatasan pada kolom Bing dan Yahoo datang dari engine-nya sendiri, bukan dari tool ini:

- **Bing** memisahkan dua kemampuan ke dua vertical: rentang tanggal kustom hanya ada di Bing Search, urutan terbaru hanya ada di Bing News.
- **Yahoo** tidak punya rentang tanggal kustom sama sekali — hanya filter relatif "past day / week / month". Script memilih bucket terdekat yang masih menampung rentang Anda, jadi sebagian hasil bisa jatuh di luar rentang. Yahoo juga tidak punya urutan by-date, dan `news.search.yahoo.com` menolak koneksi sehingga `--mode nws` otomatis memakai web search.

Kalau Anda meminta kombinasi yang tidak didukung, script mencetak catatan di awal run, misalnya:

```text
Note: Bing web search has no date ordering — use --mode nws for newest-first results.
Note: Yahoo has no custom date range — using its 'past month' filter (btf=m) as the closest match; some results may fall outside the requested range.
```

Hasil tetap diambil, hanya bagian yang tidak didukung itu saja yang diabaikan engine-nya.

### Yang Dibuang dari Hasil Bing & Yahoo

- **Link internal engine** — `bing.com`, `bing.net`, `go.microsoft.com` untuk Bing; `search.yahoo.com`, `ads.yahoo.com`, `guce.yahoo.com` untuk Yahoo
- **Iklan** — hanya hasil organik yang dibaca (`li.b_algo` di Bing, `div.algo` di Yahoo), blok iklan dilewati lewat struktur HTML-nya
- **Redirect/tracking URL** dibongkar dulu jadi URL artikel asli: `bing.com/ck/a?…&u=a1<base64>` dan `r.search.yahoo.com/…/RU=<url>/RK=`. Kalau gagal di-decode, link dibuang
- **Social media dan URL tidak valid** — sama seperti Google

---

## Pencarian per Negara (`--geo`)

Secara default setiap engine menebak negara Anda dari IP dan cookie browser, jadi run dari
Jakarta selalu dapat hasil versi Indonesia. `--geo` mengganti tebakan itu: engine diminta
mencari **seolah-olah** permintaan datang dari negara yang Anda sebut.

```bash
# kode ISO
python linktaker.py --input keyword1.txt --geo my

# atau nama negaranya — bahasa Inggris maupun Indonesia
python linktaker.py --input keyword1.txt --geo malaysia
python linktaker.py --input keyword1.txt --geo jerman

# semua engine sekaligus, satu negara
python linktaker.py --engine all --input keyword1.txt --geo singapura --output hasil-sg.txt
```

### Cara Tiap Engine Menerimanya

Tidak ada satu parameter yang berlaku di semua engine, jadi `--geo` diterjemahkan per engine:

| Engine | Yang ditambahkan | Contoh untuk `--geo my` |
|---|---|---|
| **Google** | `gl=<kode>` (negara) + `hl=<bahasa>` (bahasa hasil) | `…/search?q=kpk&gl=my&hl=ms` |
| **Bing** | `cc=<kode>` + `mkt=<bahasa>-<NEGARA>` | `…/search?q=kpk&cc=my&mkt=ms-MY` |
| **Yahoo** | host regionalnya — Yahoo tidak punya parameter negara | `https://malaysia.search.yahoo.com/search?p=kpk` |
| **Google News RSS** | `hl` / `gl` / `ceid` edisi negara itu | `…/rss/search?q=kpk&hl=ms&gl=MY&ceid=MY:ms` |

Negara ikut terbawa saat paginasi, jadi halaman 2, 3, dan seterusnya tetap dari negara yang sama.

### Format yang Diterima

Isi `--geo` boleh salah satu dari:

- **Kode ISO 3166-1 alpha-2** — `my`, `id`, `sg`, `de`. Huruf besar/kecil bebas
- **Nama negara** — `malaysia`, `singapore`, `united states`
- **Alias umum** — `uk` (→ `gb`), `usa`, `uae`, `south korea`
- **Nama Indonesia** — `jerman`, `belanda`, `singapura`, `jepang`, `amerika serikat`, `arab saudi`

Kalau isinya tidak dikenali, run berhenti sebelum pencarian dimulai dan menyebutkan kemungkinan yang dimaksud:

```text
linktaker.py: error: unknown country 'malaysa' — pass an ISO country code (my) or a country name (malaysia). Did you mean: Malaysia, Malta, Malawi?
```

Daftar lengkap negara dan aliasnya ada di `linktaker/geo.py`.

### Catatan Penting

- **`--geo` bukan proxy.** Ini mengubah negara yang *dicari*, bukan asal permintaannya — request tetap keluar dari IP Anda. Untuk hasil yang benar-benar seperti pengguna lokal, pasangkan dengan `--proxy` negara tersebut.
- **Yahoo tidak punya properti untuk semua negara.** Kalau negara yang diminta tidak ada, Yahoo tetap memakai host defaultnya dan mencetak catatan — pakai `--engine google` atau `bing` untuk negara itu:

  ```text
  Note: Yahoo has no Greenland search property — crawling https://id.search.yahoo.com instead, so --geo has no effect here. Use --engine google or bing for Greenland.
  ```

- **Filter berita tetap berjalan seperti biasa.** `news_domains.txt` isinya penerbit Indonesia, jadi `--news-filter strict` akan membuang hampir semua hasil negara lain. Untuk crawl negara lain, pakai `--news-filter smart` (default) atau tambahkan penerbit negara itu ke allowlist.
- **Header run mencantumkan negaranya**, supaya jelas hasil di `--output` itu dari mana:

  ```text
  Geolocation: Malaysia (my)
    --geo sets the country the engine searches as, not where the request comes from — pair it with --proxy for a local IP
  ```

Kalau semua run memang selalu menyasar satu negara, isi `DEFAULT_GEO` di `linktaker/config.py`
supaya tidak perlu mengetik `--geo` setiap kali.

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

## Tanggal Relatif

`--from` dan `--until` menerima tanggal pasti (`2026-08-18`) maupun **tanggal
relatif terhadap hari ini**. Bentuk relatif dihitung ulang **setiap kali program
dijalankan**, jadi jadwal yang dibiarkan berjalan berhari-hari ikut bergeser
bersama kalender — bukan terkunci di rentang yang sama terus.

| Token | Artinya |
|---|---|
| `today`, `now`, `0` | hari ini |
| `yesterday`, `kemarin` | kemarin |
| `d`, `1d`, `7d` | sekian **hari** lalu |
| `w`, `2w` | sekian **minggu** lalu |
| `m`, `3m` | sekian **bulan** lalu |
| `y`, `1y` | sekian **tahun** lalu |

Satuan tanpa angka berarti satu, jadi `w` sama dengan `1w`. Huruf besar juga
diterima, dan tanda minus di depan boleh ditulis (`-7d` sama dengan `7d`).

```bash
python linktaker.py --input keywords.txt --from w                  # seminggu terakhir
python linktaker.py --input keywords.txt --from 3d --until today   # tiga hari terakhir
python linktaker.py --input keywords.txt --from 1m --sort latest   # sebulan terakhir
```

**Inilah bedanya saat dijalankan berulang.** Misalnya crawler dijadwalkan tiap
3 jam dan Anda menulis `--from 2026-08-27`:

| Hari | `--from 2026-08-27` | `--from 1d` |
|---|---|---|
| 28 Agu | 27 Agu → 28 Agu ✅ | 27 Agu → 28 Agu ✅ |
| 29 Agu | 27 Agu → 29 Agu (jendela melebar) | 28 Agu → 29 Agu ✅ |
| 5 Sep | 27 Agu → 5 Sep (9 hari, makin berat) | 4 Sep → 5 Sep ✅ |

Tanggal pasti membuat rentangnya terus melebar setiap hari — makin lambat, makin
banyak halaman, dan makin rawan CAPTCHA. Token relatif menjaga lebar jendelanya
tetap.

Setiap run menampilkan hasil resolusinya, supaya jelas token itu jadi tanggal apa:

```text
Date: 2026-08-21 (dari 'w') .. 2026-08-28 (dari 'today') | Sort: latest | ...
```

> **Catatan pengurangan bulan:** `1m` dari tanggal 31 Maret jadi 28 Februari,
> bukan tanggal yang tidak ada. Tahun kabisat ikut diperhitungkan.

---

## Headless & CAPTCHA

Secara default browser jalan **tanpa jendela**. Jendela hanya dipinjam saat
benar-benar dibutuhkan, yaitu ketika sebuah halaman kena CAPTCHA dan ada orang
yang bisa menyelesaikannya.

Chromium menetapkan headless saat launch dan Playwright tidak bisa mengubahnya
pada browser yang sudah jalan, jadi pergantiannya dilakukan dengan menutup lalu
membuka ulang **profil yang sama**. Ini hanya bisa bekerja karena
`PERSIST_PROFILE` menyimpan cookie ke disk: tiket hasil solve CAPTCHA ikut
terbawa ke browser headless berikutnya.

Urutannya saat `--on-captcha headed` (default):

1. Crawl jalan headless.
2. Kena CAPTCHA di halaman N → browser ditutup, dibuka ulang **dengan jendela**
   langsung di halaman N.
3. Anda selesaikan CAPTCHA-nya (tunggu maksimal `CAPTCHA_WAIT_TIMEOUT`, default 120 detik).
4. Browser ditutup lagi, dibuka ulang headless, dan **melanjutkan dari halaman N** —
   bukan mengulang keyword dari halaman 1.

| Situasi | Perintah |
|---|---|
| Ditunggui orang | `--headless --on-captcha headed` (default) |
| Terjadwal / cron / systemd | `--headless --on-captcha skip` |
| Debugging, mau lihat browsernya | `--headed` |

**Catatan penting:**

- `--on-captcha skip` adalah satu-satunya setelan yang masuk akal untuk run
  terjadwal. Tidak ada yang menyelesaikan CAPTCHA jam 3 pagi, jadi menunggu
  120 detik per halaman hanya menghabiskan jatah jadwal.
- Kalau `PERSIST_PROFILE` dimatikan, hasil solve tidak bisa dibawa kembali ke
  headless (cookie-nya ada di memori dan ikut mati saat browser ditutup).
  Dalam kondisi itu halaman yang kena CAPTCHA akan dilewati, dan programnya
  memberi tahu di awal run.
- `--on-captcha headed` butuh satu browser pada satu waktu, jadi ia hanya
  aktif di jalur sekuensial (`FETCH_MODE = "playwright"`, default). Pada jalur
  paralel setelan ini otomatis turun ke `skip`.
- Headless lebih mudah dikenali mesin pencari daripada headed. Kalau CAPTCHA
  jadi jauh lebih sering sampai crawl bolak-balik relaunch, `--headed` justru
  lebih cepat. Ukur dulu untuk keyword Anda, jangan diasumsikan.

Untuk menjalankan ini otomatis di Linux, lihat [`deploy/INSTALL-LINUX.md`](deploy/INSTALL-LINUX.md).

Jadwal itu juga mengirim hasilnya sendiri: tiap run,
`deploy/submit-links.py` mem-POST link yang belum pernah dikirim ke endpoint
`submit_batch` — lihat [Kirim otomatis ke submit_batch](deploy/INSTALL-LINUX.md#kirim-otomatis-ke-submit_batch).

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

- Hanya berfungsi untuk pencarian tab Berita (`tbm=nws`) — jadi hanya aktif pada `--mode nws` atau `--mode both`
- Jumlah hasil terbatas (biasanya ~20–100 item)
- URL decode mungkin gagal untuk beberapa format baru
- Rentang tanggal `--from`/`--until` belum didukung RSS (hanya filter relatif `qdr:*`)
- Edisi feed mengikuti `--geo` (`hl`/`gl`/`ceid`); tanpa `--geo`, edisi Indonesia yang dipakai

### Dukungan Filter Waktu

| Parameter Google | RSS `when` | Deskripsi |
|---|---|---|
| `tbs=qdr:h` | `1h` | 1 jam terakhir |
| `tbs=qdr:d` | `1d` | 1 hari terakhir |
| `tbs=qdr:w` | `7d` | 1 minggu terakhir |
| `tbs=qdr:m` | `30d` | 1 bulan terakhir |
| `tbs=qdr:y` | `1y` | 1 tahun terakhir |

---

## Filter Berita (News Filter)

Google tab Berita mengembalikan portal yang sudah dia klasifikasikan sebagai sumber berita, jadi hasilnya relatif bersih. **Bing dan Yahoo tidak**: keduanya mengembalikan apa pun yang cocok dengan keyword — kamus, konverter zona waktu, situs booking, halaman produk, portal layanan pemerintah — dan semuanya dulu ikut masuk ke file output.

`news_filter.py` adalah gerbang yang dilewati **setiap** link sebelum boleh ditulis ke output, dan `--news-filter` mengatur seberapa ketat gerbang itu.

### Tiga Level

| Level | Yang Lolos | Kapan Dipakai |
|---|---|---|
| `smart` *(default)* | Semua link yang **berbentuk artikel** dan host-nya bukan domain non-berita yang dikenal | Pemakaian harian. Portal baru yang belum ada di allowlist tetap ikut terjaring |
| `strict` | **Hanya** host yang terdaftar di `news_domains.txt`, dan tetap harus berbentuk artikel | Saat daftar kliping harus bersih di atas segalanya — terutama untuk Bing dan Yahoo |
| `off` | Semua link non-sosmed, seperti perilaku sebelum filter ini ada | Membandingkan hasil, atau saat filter dicurigai membuang link yang valid |

```bash
# default: smart, tidak perlu ditulis
python linktaker.py --engine bing --input keywords.txt

# daftar kliping bersih: hanya penerbit yang sudah didaftarkan
python linktaker.py --engine bing --input keywords.txt --news-filter strict

# matikan filter untuk membandingkan
python linktaker.py --engine bing --input keywords.txt --news-filter off
```

### Apa yang Dibuang `smart`

1. **Host non-berita yang dikenal** — ensiklopedia dan kamus (`wikipedia.org`, `sinonim.com`, `britannica.com`), jam/kalender/kalkulator (`worldtimebuddy.com`, `24timezones.com`, `time.is`), travel dan tiket (`traveloka.com`, `tiket.com`, `agoda.com`), marketplace (`tokopedia.com`, `shopee.co.id`, `lazada.co.id`), lowongan kerja, database hukum, platform blog (`kompasiana.com`, `blogspot.com`), dan **agregator** (`msn.com`, `headtopics.com`, `news.google.com` — berisi berita asli, tapi salinan, bukan sumbernya).
2. **Situs institusi** — apa pun berakhiran `.go.id`, `.gov.my`, `.ac.id`, `.edu`, `.mil`, dan sejenisnya. Mereka menerbitkan siaran pers, bukan jurnalisme.
3. **URL yang bukan artikel** — homepage, `/tag/…`, `/kategori/…` tanpa id, `/indeks`, `/search`, halaman login, sitemap, dan file (`.pdf`, `.jpg`, `.xml`).

Sebuah URL dianggap **berbentuk artikel** kalau path-nya membawa salah satu dari: tanggal terbit (`/2026/08/20/…`), id CMS (5 digit atau lebih, termasuk permalink WordPress lama `?p=112078`), atau slug judul minimal 3 kata (`kpk-tangkap-bupati-sidoarjo`).

> Kata "listing" seperti `kategori` boleh muncul sebagai awalan artikel asli — `infopublik.id/kategori/nasional/985004/kpk-tahan-eks-pejabat` tetap lolos karena membawa id berita. Yang tidak membawa id dianggap halaman daftar dan dibuang.

### `news_domains.txt` — Allowlist Penerbit

Satu domain per baris, subdomain otomatis ikut: `tribunnews.com` sudah mencakup `surabaya.tribunnews.com`, `fajar.co.id` mencakup `harian.fajar.co.id`. Baris kosong dan `#` diabaikan, dan skema/path yang tidak sengaja ikut ter-paste dibersihkan sendiri (`https://tempo.co/` → `tempo.co`).

```text
# news_domains.txt
detik.com
tribunnews.com
kompas.com
theedgemalaysia.com
```

File bawaan berisi **330 penerbit** — dipanen dari crawl tab Berita Google, ditambah desk nasional Indonesia, Malaysia, Singapura, dan kantor berita internasional.

Peranannya berbeda per level: di `strict` file ini adalah satu-satunya pintu masuk; di `smart` dia jalur cepat — domain yang terdaftar melewati semua pemeriksaan negatif, jadi portal dengan pola URL tidak lazim tetap lolos.

`--news-filter strict` **menolak jalan** kalau allowlist-nya kosong atau filenya tidak ada, supaya tidak ada run panjang yang berakhir dengan output kosong.

### Laporan Penolakan

Setiap run menutup dengan daftar host yang dibuang, terbanyak dulu:

```text
News filter dropped 1917 link(s) from 284 host(s):
    185  sinonim.com
    143  msn.com
    106  bekasikab.go.id
     97  wikipedia.org
     46  traveloka.com
  ... and 269 more host(s)
Any real publisher listed above belongs in news_domains.txt.
```

Inilah cara `news_domains.txt` tumbuh: yang benar-benar penerbit dipindahkan ke allowlist, sisanya membuktikan filternya bekerja.

### Efek pada Output Nyata

Diukur dari tiga file output run 2026-08-20:

| File | Sebelum | `smart` | `strict` |
|---|---|---|---|
| `output.txt` (Google) | 661 | 642 (97%) | 627 (95%) |
| `outputbing.txt` (Bing) | 3341 | 1355 (41%) | 833 (25%) |
| `outputyahoo.txt` (Yahoo) | 2206 | 618 (28%) | 274 (12%) |

Google nyaris tidak berubah karena memang sudah bersih — yang dibuang cuma situs pemerintah, Kompasiana, dan agregator. Bing dan Yahoo kehilangan mayoritas isinya, dan itu memang intinya.

Sisa yang masih lolos `smart` di Bing/Yahoo adalah **long tail** situs SEO dan korporat yang mustahil di-blocklist satu per satu (`idezia.com`, `jasapenulisartikel.my.id`, halaman produk perusahaan). Untuk kedua engine ini, `--news-filter strict` adalah level yang benar-benar menjamin "hanya berita".

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

### Yahoo: hasil kosong atau halaman consent

Yahoo kadang menampilkan halaman consent (`guce.yahoo.com`) sebelum hasil muncul. Script memperlakukannya seperti CAPTCHA: browser terbuka, Anda klik persetujuannya, lalu crawl lanjut sendiri.

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
│   ├── __main__.py       # Entry point untuk `python -m linktaker`
│   ├── cli.py            # Argparse + main() — orkestrasi end-to-end
│   ├── config.py         # Semua konstanta konfigurasi
│   ├── deps.py           # Optional-dependency imports (cloudscraper, playwright, dst.)
│   ├── browser.py        # BrowserManager (Playwright) — engine-agnostic
│   ├── fetchers.py       # curl_cffi, cloudscraper, orkestrasi fetch per URL
│   ├── inputs.py         # Baca keyword/url.txt/proxies.txt/auth.json + parsing tanggal
│   ├── url_utils.py      # Helper URL untuk semua engine (AMP, sosmed, validasi)
│   ├── news_filter.py    # Gerbang berita: blocklist, bentuk URL artikel, allowlist
│   ├── geo.py            # Resolusi --geo: kode ISO/nama negara -> objek Geo
│   └── engines/          # Satu file per search engine
│       ├── __init__.py   # Registry ENGINES + get_engine()
│       ├── base.py       # Kontrak Engine
│       ├── google.py     # Google Search / Google News
│       ├── bing.py       # Bing Search / Bing News
│       ├── yahoo.py      # Yahoo Search
│       └── news_rss.py   # Google News RSS (opsional)
├── deploy/              # Jadwal otomatis di Linux (systemd timer + runner)
│   ├── run-linktaker.sh
│   ├── submit-links.py  # Kirim hasil tiap run ke endpoint submit_batch
│   ├── linktaker.service
│   ├── linktaker.timer
│   └── INSTALL-LINUX.md
├── requirements.txt     # Daftar dependencies Python
├── news_domains.txt     # (Dibuat user) Allowlist penerbit — default `--news-domains`
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
