# SmartExcelExtractor

Ambil angka penting dari banyak file Excel laporan pabrik **tanpa menulis alamat sel**.
Anda memberi tahu aplikasi tulisan apa yang menandai baris dan kolom (misalnya baris bertuliskan
"Produksi Harian" dan kolom bertuliskan "Total"), lalu aplikasi mencari kombinasinya di setiap file.
Hasilnya satu file JSON berisi angka **beserta sumbernya** (file, sheet, alamat sel) dan catatan
pemeriksaan, sehingga data yang melenceng langsung terlihat.

Aplikasi ini punya dua wajah, memakai mesin yang sama:
- **jendela aplikasi** (untuk menyiapkan dan memeriksa hasil),
- **mode tanpa tampilan / CLI** (untuk dijalankan otomatis oleh penjadwal Windows).

---

## 1. Yang dibutuhkan

- Python 3.11 atau lebih baru ([python.org](https://www.python.org/downloads/)) — saat memasang di
  Windows, centang **"Add python.exe to PATH"**.
- Folder laporan berisi sub-folder per pabrik (misalnya `input\lap_harian`, `input\prod_harian`).
- Aplikasi ini tidak butuh Microsoft Excel untuk bekerja.

## 2. Cara memasang (sekali saja)

Buka Command Prompt / PowerShell, masuk ke folder aplikasi, lalu:

```
cd "C:\Document\Kerja\SmartExcelExtractor"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Di macOS / Linux, baris aktivasi diganti:

```
cd "/path/ke/SmartExcelExtractor"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Semua perintah berikutnya dijalankan di jendela yang sudah aktif venv ini.

## 3. Cara memakai jendela aplikasi

```
python main.py
```

Di macOS / Linux bisa juga `./.venv/bin/python main.py` tanpa mengaktifkan venv.

**Profil** adalah satu set pengaturan untuk satu pabrik (misalnya "Pabrik A"), tersimpan sebagai
file di folder `profiles\`. Tombol di bagian atas: **Baru, Salin, Ubah Nama, Hapus, Impor, Ekspor**.
Profil "Salin" berguna karena tiap pabrik mirip tetapi tidak sama. Setiap perubahan langsung
tersimpan (tidak ada tombol Simpan).

Isi tiga langkah wizard:

**Langkah 1 - Sumber data**
1. Tekan **"Pilih Folder..."** dan arahkan ke **folder induk** (folder yang berisi sub-folder
   pabrik). Folder terakhir diingat untuk lain kali.
2. Aplikasi menampilkan sub-folder yang ditemukan. **Centang** yang ingin diambil datanya.

**Langkah 2 - Data yang diambil**
1. Tekan **"+ Tambah Sheet"**, pilih nama sheet dari file contoh yang ditemukan aplikasi
   (atau ketik sendiri) dan tentukan cara mencocokkan nama sheet.
2. Pilih sheet, lalu tekan **"+ Tambah Data"** untuk membuat satu data yang mau diambil.
   Isi form berbahasa awam: *"Nama untuk hasil ini"*, *"Cari baris yang bertuliskan..."*,
   *"Cari kolom yang bertuliskan..."*, dan centang *"Tulisan ini hanya muncul satu kali di sheet"*
   kalau memang hanya ada satu.
3. Bila tulisan muncul lebih dari sekali, pilih cara memilih: **yang paling dekat** dengan tulisan
   lain, **berdasarkan alamat sel acuan** yang Anda tulis, atau **hitung sendiri** (pilih dari
   daftar kandidat secara manual).
4. **Preview** di bagian bawah form langsung menunjukkan nilai yang ditemukan, alamat selnya,
   jumlah kemunculan tulisan, dan cuplikan kecil sheet di sekitar hasil (baris, kolom, dan nilai
   disorot warna). Jadi Anda bisa mencocokkan dengan Excel tanpa membuka Excel.
5. Tombol lain di pohon data: **Ubah, Duplikat, Hapus** (Hapus selalu minta konfirmasi).

**Langkah 3 - Jalankan dan periksa**
1. Tekan **"Jalankan Ekstraksi"**. Aplikasi tetap responsif (proses berjalan di latar belakang).
2. Lihat ringkasan: jumlah data, berapa **OK**, berapa **perlu dicek**, berapa **gagal**.
   Tabel hasil menampilkan nilai, status berwarna, file, sheet, dan alamat sel.
   Daftar **"Catatan pemeriksaan"** menjelaskan setiap masalah dengan kalimat biasa.
3. File JSON otomatis tersimpan di folder `output\`. Tombol **"Simpan Salinan JSON..."** menyalin
   hasil ke lokasi pilihan Anda (misalnya untuk dikirim ke atasan).

Tombol wizard: **Kembali / Lanjut / Selesai**, dan **Tutup** untuk keluar.

## 4. Cara menjalankan tanpa tampilan (untuk dijadwalkan)

Mode ini memakai profil yang sudah dibuat di jendela aplikasi tadi. Di Windows, ketik
`python cli.py` di Command Prompt; di macOS / Linux pakai `./.venv/bin/python cli.py`.

```
python cli.py list-profiles                      # daftar profil yang ada
python cli.py validate --profile "Pabrik A"      # periksa profil, tanpa mengambil data
python cli.py run --profile "Pabrik A"           # ambil data, tulis JSON ke output\
```

Tambahan yang berguna:
- `--input "D:\Laporan\input"` menimpa folder induk (kalau folder laporan berpindah/berganti nama).
- `--output "D:\Hasil"` menyimpan JSON ke folder lain.
- `--profile` menerima **nama profil** (mis. `"Pabrik A"`) atau **lokasi file profil lengkap**
  (mis. `"D:\Pengaturan\Pabrik A.json"`).

Contoh keluaran (dijalankan pada data latihan di bagian 6):

```
Profil : Contoh Pabrik A
Waktu  : 2026-10-14T13:11:45+08:00
Hasil  : 15 data - 9 OK, 5 perlu dicek, 1 gagal
  [CEK  ] prod_formula: Rumus di J45 belum dihitung oleh Excel, nilainya kosong.
  [CEK  ] prod_util: Nilai di L57 berasal dari sel gabungan K57:L57.
  ... (catatan lain menyusul, urut dari yang paling penting)
  [GAGAL] prod_unique: Tulisan 'Produksi Harian' diatur hanya muncul sekali, tetapi ditemukan 2 kali: I45, I94.
File   : D:\...\output\Contoh Pabrik A_20261014_131145.json
```

**Kode keluar** (dipakai penjadwal untuk tahu hasilnya):
- `0` = berhasil (data yang hanya "perlu dicek" tetap dianggap 0),
- `1` = ada data yang gagal diambil, atau proses berhenti karena masalah besar,
- `2` = profil atau pengaturannya belum benar (profil tidak ditemukan, folder induk kosong,
  belum ada sub-folder yang dicentang).

Menjadwalkan di **Task Scheduler** (Windows):
1. Create Task → Triggers → New (misalnya tiap hari pukul 07:00).
2. Actions → New: Program/script = `C:\Document\Kerja\SmartExcelExtractor\.venv\Scripts\python.exe`,
   Add arguments = `cli.py run --profile "Pabrik A"`,
   Start in = `C:\Document\Kerja\SmartExcelExtractor`.
3. Hasil tiap run jadi file baru di folder `output\` (file lama tidak pernah ditimpa; nama file
   memakai tanggal dan jam).

## 5. File disimpan di mana

| Isi | Lokasi |
| --- | --- |
| Profil (pengaturan) | `profiles\` di samping aplikasi, satu file `.json` per profil |
| Hasil ekstraksi | `output\`, nama `Nama Profil_TANGGAL_JAM.json` |
| Catatan teknis / pesan galat | `logs\app.log` (dipotong otomatis bila sudah besar) |
| Ingatan aplikasi (profil & folder terakhir) | `settings.json` di samping aplikasi |

## 6. Data contoh untuk latihan (aman, tidak mengganggu data asli)

Buat file Excel latihan yang sengaja "berantakan" (keyword muncul dua kali, sel gabungan, rumus
yang belum dihitung Excel, baris tersembunyi, data bergeser, file sementara `~$`):

```
python tools/generate_samples.py --out samples
```

Hasilnya `samples\input_a`, `samples\input_b`, `samples\input_c`, masing-masing berisi
`lap_harian`, `prod_harian`, `penjualan_harian` (sheet mis. `Produksi`, `Laporan 01-10`).
Lalu di jendela aplikasi: **Baru** → Langkah 1 pilih folder `samples\input_a` → centang ketiga
sub-folder → Langkah 2 tambah sheet dan data → Langkah 3 **Jalankan Ekstraksi**.
Untuk mencoba lewat CLI dengan profil yang sama (lihat namanya dengan `python cli.py list-profiles`):

```
python cli.py run --profile "Nama Profil Anda"
```

## 7. Kalau ada masalah

Semua masalah ditulis di **"Catatan pemeriksaan"** (Langkah 3) dalam kalimat biasa, dan versi
lengkapnya di `logs\app.log`. Satu data yang gagal tidak menghentikan data lain.

| Yang terlihat | Artinya & tindakan |
| --- | --- |
| Status **Gagal**: "Tulisan '...' muncul lebih dari sekali" | Tulisan itu diatur hanya muncul sekali, tetapi ada beberapa. Buka datanya (**Ubah**), lalu pilih cara memilih: paling dekat / alamat sel acuan / hitung sendiri. Kandidatnya terlihat di preview. |
| Status **Gagal**: "Tulisan '...' tidak ditemukan" | Tulisan di profil tidak ada di file itu (mungkin beda huruf, spasi, atau beda bulan). Perbaiki tulisannya. |
| Status **Gagal**: "Sheet '...' tidak ada di file" | Nama sheet berubah/berbeda antar pabrik. Sesuaikan cara mencocokkan nama sheet di Langkah 2. |
| Perlu dicek: "Rumus di ... belum dihitung oleh Excel" | File disimpan oleh mesin/program lain sehingga nilai hasil rumus tidak tersimpan. Buka file itu di Excel, simpan sekali, lalu jalankan ulang. |
| Perlu dicek: "Sel ... berisi kesalahan Excel #REF!" | Rumus di file Excel-nya rusak. Perbaiki di file aslinya. |
| Perlu dicek: "Nilai ... berasal dari sel gabungan" | Peringatan saja, nilainya tetap diambil. |
| Perlu dicek: "Nilai ... bukan angka" | Isinya teks, bukan angka (mis. "belum ada"). Nilai aslinya tetap disimpan. |
| Perlu dicek: "Tidak ada nilai di ..." | Titik temunya benar, tetapi selnya kosong. |
| "File tidak bisa dibaca" / file terlewat | Filenya sedang dibuka di Excel oleh orang lain, atau rusak. Tutup file di Excel lalu jalankan ulang. |
| "Profil '...' tidak ditemukan" (kode keluar 2) | Nama profil salah, atau profilnya belum pernah dibuat di jendela aplikasi. Cek dengan `python cli.py list-profiles`. |
| "Belum ada sumber (folder) yang dicentang" (kode keluar 2) | Buka Langkah 1 dan centang sub-folder yang dipakai. |

Catatan kecil: nama folder atau file boleh mengandung spasi, tetapi di Command Prompt selalu
pakai tanda kutip, mis. `--input "D:\Laporan Harian\input"`.

## 8. Untuk pengembang

Susunan folder: `core/` = mesin (tanpa UI, bisa jalan headless), `ui/` = jendela PySide6,
`cli.py` = mode tanpa tampilan, `main.py` = titik masuk jendela, `tests/` = test pytest,
`tools/generate_samples.py` = pembuat file contoh. `docs/SPEC.md` adalah sumber kebenaran,
`docs/PROGRESS.md` mencatat kemajuan per fase.

```
pip install -r requirements-dev.txt
pytest -q          # seluruh test (108 passed)
ruff check .
mypy core
python tools/generate_samples.py --out samples
```

Aturan yang dipegang mesin ini: hasil harus sama untuk input yang sama (deterministik);
satu data/sheet/file yang gagal tidak boleh menghentikan yang lain; kalau ada beberapa kandidat,
mesin tidak menebak diam-diam tetapi mencatat semuanya di audit; setiap nilai menyimpan alamat
sel dan asalnya (file, sheet); kode isu baru harus dimasukkan ke `docs/SPEC.md` lebih dulu.

## 9. Belum ada (rencana berikutnya)

- Tombol **"Simpan Laporan Audit"** (CSV/HTML berisi semua catatan, urut dari yang paling parah) —
  belum ada; sementara pakai **"Simpan Salinan JSON..."**.
- **Perbandingan antar run**: peringatan otomatis kalau nilai berubah melebihi ambang tertentu.
- **Kemasan `.exe`** dengan PyInstaller (rencananya memakai satu spec file; sesudah itu aplikasi
  bisa dijalankan tanpa memasang Python).
- **File `.xls` lama** (Excel 97-2003); saat ini baru `.xlsx` dan `.xlsm`.
