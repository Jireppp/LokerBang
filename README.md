# LokerBang — Job Scraper to Google Sheets

Skrip automasi Python untuk mengambil lowongan kerja terbaru (**<= 14 hari terakhir**) dari **LinkedIn Jobs**, **Jobstreet Indonesia**, dan **Glints Indonesia**, lalu menyinkronkannya ke Google Sheets (`Job_Tracker`) secara otomatis dengan deduplikasi URL dan batch update.

## Target Pencarian
- **Role A — System Analyst**: Entry Level / Fresh Graduate / Junior / 0–2 tahun (lowongan tanpa keterangan level tetap disertakan sebagai `"Not specified"` agar tidak ada peluang yang terlewat).
- **Role B — IoT Engineer**: `"IoT Engineer"`, `"Internet of Things Engineer"`, `"Hardware & IoT"` (semua level).
- **Lokasi**: Bandung, Jakarta, dan Bodetabek (Tangerang, Tangerang Selatan, BSD, Serpong, Bekasi, Cikarang, Depok, Bogor).

---

## 1. Instalasi Dependencies

Pastikan **Python 3.10+** sudah terpasang, lalu jalankan di PowerShell / Terminal pada folder proyek ini:

```powershell
pip install -r requirements.txt
playwright install chromium
```

> Catatan: `playwright install chromium` dipakai sebagai fallback otomatis untuk Glints karena endpoint API Glints dilindungi Cloudflare/WAF. LinkedIn dan Jobstreet diambil langsung via HTTP cepat (`httpx`).

---

## 2. Panduan Setup Service Account Google Sheets

Agar skrip dapat menulis ke Google Sheets tanpa login manual di browser:

1. **Buka Google Cloud Console**
   - Kunjungi [https://console.cloud.google.com/](https://console.cloud.google.com/) dan buat project baru (atau pilih project yang sudah ada).

2. **Aktifkan API yang Dibutuhkan**
   - Masuk ke menu **APIs & Services > Library**.
   - Cari dan klik **Enable** pada dua API berikut:
     1. **Google Sheets API**
     2. **Google Drive API**

3. **Buat Service Account & Unduh File JSON**
   - Masuk ke menu **APIs & Services > Credentials**.
   - Klik **+ CREATE CREDENTIALS > Service account**.
   - Isi nama bebas (misalnya `lokerbang-bot`), lalu klik **Create and Continue** hingga **Done**.
   - Klik Service Account yang baru dibuat pada daftar, buka tab **Keys**.
   - Klik **Add Key > Create new key**, pilih **JSON**, lalu klik **Create**.
   - File `.json` akan terunduh otomatis. Simpan file tersebut di folder proyek ini dengan nama `service_account.json` (jangan pernah di-upload ke Git publik).

4. **Bagikan (Share) Spreadsheet ke Email Service Account**
   - Buka file `service_account.json` dengan teks editor, salin nilai pada field `"client_email"` (contoh: `lokerbang-bot@project-id.iam.gserviceaccount.com`).
   - Buat atau buka Google Spreadsheet Anda di browser.
   - Klik tombol **Share** (Bagikan) di kanan atas, tempelkan alamat `"client_email"` tadi, pastikan aksesnya **Editor**, lalu klik **Send / Share**.

5. **Salin `SPREADSHEET_ID` ke File `.env`**
   - Lihat URL Google Spreadsheet Anda di browser:
     ```
     https://docs.google.com/spreadsheets/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890/edit
     ```
   - Bagian di antara `/d/` dan `/edit` adalah `SPREADSHEET_ID`.
   - Salin `.env.example` menjadi `.env`:
     ```powershell
     Copy-Item .env.example .env
     ```
   - Isi nilai `SERVICE_ACCOUNT_FILE` dan `SPREADSHEET_ID` di dalam `.env`.

---

## 3. Cara Menjalankan

### A. Tes tanpa menulis ke Google Sheets (`--dry-run`)
Gunakan mode ini untuk memastikan ketiganya berjalan dan melihat daftar lowongan di layar:

```powershell
python scraper.py --dry-run
```

### B. Sinkronisasi penuh ke Google Sheets
Menjalankan seluruh portal dan menambahkan hanya lowongan baru ke tab `Job_Tracker`:

```powershell
python scraper.py
```

Jika tab `Job_Tracker` belum ada di spreadsheet Anda, skrip akan membuatnya otomatis lengkap dengan header:
`[Timestamp_Scraped, Job_Title, Company, Location, Platform, Date_Posted, Experience_Level, Job_URL, Status]`

Kolom `Status` diisi `"New"` untuk baris baru. Baris lama yang sudah pernah masuk **tidak akan pernah ditimpa**, sehingga Anda bebas mengubah kolom `Status` (misalnya menjadi `Applied`, `Interview`, atau `Skip`).

### C. Opsi CLI Tambahan
```powershell
# Hanya portal tertentu
python scraper.py --portals linkedin,jobstreet

# Hanya salah satu role
python scraper.py --roles system_analyst

# Matikan fallback Playwright (hanya HTTP)
python scraper.py --no-playwright

# Ubah batas umur lowongan (default 14 hari)
python scraper.py --days 7
```

Log eksekusi disimpan otomatis di `logs/scraper.log` (maks. 1 MB × 3 file rotasi).

---

## 4. Menjalankan Web Dashboard UI & FastAPI Bridge

Proyek ini dilengkapi **Web Dashboard UI** (React + TypeScript + Vite + Tailwind CSS) dan **FastAPI Bridge** (`backend/api.py`) agar Anda dapat menjalankan scraper dengan 1 klik dan memantau lowongan langsung dari browser.

### Cara 1: Jalankan Sekaligus via Skrip PowerShell
```powershell
.\start-dashboard.ps1
```

### Cara 2: Jalankan di 2 Terminal Terpisah

**Terminal 1 — Backend API (Port 8000):**
```powershell
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — Frontend Dashboard (Port 5173):**
```powershell
cd frontend
npm run dev
```
Lalu buka **`http://localhost:5173`** di browser Anda.

---

## 5. Menjadwalkan Otomatis di Windows Task Scheduler (Opsional)

Saat nanti Anda ingin menjalankannya terjadwal otomatis setiap hari:
- **Program/script**: path ke `python.exe` Anda (cek dengan `where.exe python` di PowerShell).
- **Add arguments**: `scraper.py`
- **Start in**: `C:\Users\penap\Documents\Project_Fik\LokerBang`
