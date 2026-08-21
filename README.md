# LinkTaker Google

> **Google Search Result Link Extractor** — Tool otomatis untuk mengekstrak URL dari hasil pencarian Google secara massal, dengan dukungan input CLI dinamis, filter pintar, anti-deteksi, dan multi-mode fetching.

---

## Daftar Isi

- [Tentang Project](#tentang-project)
- [Fitur Utama](#fitur-utama)
- [Arsitektur & Alur Kerja](#arsitektur--alur-kerja)
- [Struktur Kode (Package Modules)](#struktur-kode-package-modules)
- [Prasyarat](#prasyarat)
- [Instalasi](#instalasi)
- [Penggunaan](#penggunaan)
- [File Input & Output](#file-input--output)
- [Anti-Deteksi & Stealth](#anti-deteksi--stealth)
- [Proxy & Autentikasi](#proxy--autentikasi)
- [Filter Cerdas (Media & Sosial)](#filter-cerdas-media--sosial)
- [Troubleshooting](#troubleshooting)
- [Lisensi](#lisensi)

---

## Tentang Project

**LinkTaker Google** adalah scraper Python yang dirancang untuk mengekstrak semua URL hasil pencarian dari Google Search secara otomatis. Tool ini telah diperbarui untuk mendukung:

- **Input Dinamis CLI** — masukkan parameter langsung dari terminal (seperti `--from`, `--until`, `--tab`).
- **Tab Filter Fleksibel** — mencari dari tab "Berita" (News) atau tab "Semua" (All).
- **Extreme News Filter** — membuang otomatis situs non-berita dan halaman video/galeri dari hasil pencarian.
- **Paginasi otomatis** — menelusuri halaman 1 hingga N dari hasil pencarian.
- **Anti-bot detection** — fingerprint browser realistis dan stealth mode.
- **Filter media sosial** — otomatis mengecualikan domain media sosial populer.
- **Struktur modular** — kode dipecah jadi package Python (`linktaker/`).

---

## Fitur Utama

| Fitur | Deskripsi |
|---|---|
| **Input Fleksibel (CLI)** | Baca keyword dari file txt biasa, lalu atur parameter langsung dari argumen CLI. |
| **Smart Tab Search** | Menarik artikel dari tab `news` atau mengekstrak portal berita baru dari tab `all`. |
| **Anti-Video & Extreme Filter** | Membuang tautan non-teks (seperti Youtube, Galeri Foto, atau e-Commerce). |
| **Multi-mode Fetch** | `curl` (cepat), `playwright` (akurat), `auto` (fallback otomatis). |
| **Browser Fingerprinting** | Menggunakan `browserforge` untuk generate fingerprint browser yang realistis. |
| **Stealth Mode** | `playwright-stealth` menyembunyikan tanda-tanda bot/automation. |
| **Cloudflare Bypass** | `cloudscraper` + `curl_cffi` impersonation untuk melewati proteksi. |
| **Social Media Filter** | Otomatis mengecualikan 40+ platform media sosial. |
| **Proxy Rotation** | Dukungan proxy via CLI (`--proxy`) untuk menghindari rate limiting. |

---

## Arsitektur & Alur Kerja

```text
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│ keyword.txt  │────▶│  linktaker/  │────▶│   output.txt     │
│ + Argumen CLI│     │   (package)  │     │ (extracted links)│
└──────────────┘     └──────┬───────┘     └──────────────────┘
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
         │  ├── Filter Extreme & Anti-Video    │
         │  ├── Filter social media            │
         │  └── Deduplicate URLs               │
         └─────────────────────────────────────┘
```

---

## Struktur Kode (Package Modules)

`linktaker/` dipecah menjadi beberapa file dengan satu tanggung jawab:

| Modul | Tanggung Jawab |
|---|---|
| `cli.py` | `main()` — menangani argumen `--input`, `--tab`, dll. merangkai semua modul. |
| `url_utils.py` | Strip AMP, filter Extreme News, Anti-Video, filter social media, validasi link. |
| `keywords.py` | Parsing keyword dan merakit URL Google dari argumen CLI. |
| `fetchers.py` | Fetch via `curl_cffi`, orkestrasi per-URL (`process_one_url`). |
| `browser.py` | `BrowserManager` — lifecycle browser Playwright, CAPTCHA, paginasi. |
| `news_rss.py` | Decode/bangun/fetch Google News RSS. |
| `config.py` & `deps.py`| Konstanta, path file, timeout, daftar sosmed, dependensi opsional. |

---

## Prasyarat

- **Python** 3.8 atau lebih baru
- **pip** (Python package manager)
- **Koneksi internet** yang stabil

---

## Instalasi

1. **Clone Repository**
   ```bash
   git clone https://github.com/perusahaan-anda/linktaker-google.git
   cd linktaker-google
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Chromium untuk Playwright**
   ```bash
   playwright install chromium
   ```

---

## Penggunaan

Tool ini dijalankan sebagai modul Python (`-m linktaker`) dan sepenuhnya dikendalikan lewat argumen CLI.

### 1. Ekstraksi Dasar (Otomatis masuk ke Google News)
Cukup siapkan file `keyword1.txt` berisi daftar kata kunci murni (satu kata per baris), lalu jalankan:
```bash
python -m linktaker --input keyword1.txt
```

### 2. Pencarian Tanggal Spesifik & Paginasi
Untuk membatasi berita dari rentang waktu tertentu dan membatasi jumlah halaman yang di-scrape:
```bash
python -m linktaker --input keyword1.txt --from 2026-08-08 --until 2026-08-16 --max-pages 2 --output hasil.txt
```

### 3. Mode Tab "Semua" (Mencari Portal Berita Baru)
Untuk mencari artikel yang mungkin belum masuk indeks News resmi Google, paksa sistem mencari di tab Semua (Web):
```bash
python -m linktaker --input keyword1.txt --tab all
```
*Catatan: Sistem secara otomatis mengaktifkan Filter Anti-Video & Extreme News untuk membuang link perusahaan, Wikipedia, dan galeri/video.*

### 4. Menggunakan Proxy
```bash
python -m linktaker --input keyword1.txt --proxy http://user:password@proxy.com:2570
```

---

## File Input & Output

### `keyword.txt` (File Input)
Berisi daftar kata kunci mentah, cukup satu baris per entri:
```text
teknologi indonesia
kasus korupsi
pilkada jakarta
```

### `output.txt` (File Hasil)
Berisi daftar link artikel murni hasil saringan:
```text
https://example.com/artikel-satu-panjang
https://berita.co.id/news/berita-dua
```

---

## Filter Cerdas (Media & Sosial)

LinkTaker memiliki kecerdasan berlapis untuk membuang link non-berita:
1. **Extreme News Filter**: Jika mencari di tab `all`, URL yang tidak punya minimal 3 strip (`-`) atau tidak memiliki kata kunci berita (`/news`, `/berita`, `/2026`) akan dibuang.
2. **Anti-Video Filter**: Membuang URL yang terdeteksi sebagai halaman `video`, `foto`, `gallery`, atau `podcast`.
3. **Filter Sosmed**: Otomatis membuang 40+ domain seperti `facebook.com`, `youtube.com`, `instagram.com`, `twitter.com`, dll.

---

## Troubleshooting

- **`playwright not installed`**: Jalankan `pip install playwright && playwright install chromium`.
- **CAPTCHA Timeout / 0 Links di tab All**: Jika Anda menggunakan mode tab `all`, Google mungkin memblokir IP Anda. Jika peramban Chrome otomatis terbuka menampilkan teka-teki gambar CAPTCHA, segera klik dan selesaikan secara manual dalam waktu 120 detik.
- **Hasil 0 Link**: Pastikan `--from` dan `--until` diatur ke tanggal yang masuk akal, atau coba matikan filter tanggal.

---

## Lisensi
Project ini bersifat internal/open-source. Silakan gunakan sesuai kebutuhan.
