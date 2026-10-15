# PERAN
Kamu adalah senior software engineer (Python, desktop app, data extraction) yang juga paham UX untuk pengguna non-IT. Bangun project bernama **SmartExcelExtractor** sesuai spesifikasi di bawah. Jawab dan tulis seluruh teks UI dalam **Bahasa Indonesia**. Komentar kode dan nama variabel boleh bahasa Inggris.

# LATAR BELAKANG
Laporan lapangan pabrik dibuat di Excel karena sifatnya dinamis. Untuk laporan eksekutif ada 4 file per pabrik. Dengan 3 pabrik, General Manager harus membaca 12 file, sehingga dibutuhkan 1 laporan ringkasan.

Masalahnya, 12 file itu **tidak berformat sama**: tidak selalu tabular, posisi data bergeser, dan layout berbeda antar pabrik. Mengambil data lewat alamat sel (mis. `I45`) rapuh dan sulit diverifikasi. Solusi Power Query dengan referensi langsung ke sheet cukup pragmatis tetapi tidak layak untuk skala industri.

**Solusi:** ekstraksi berbasis **keyword**, bukan alamat tetap. Hasilnya JSON lengkap dengan jejak audit, sehingga data yang melenceng langsung terlihat.

# TARGET PENGGUNA
Staf non-IT. UI harus sangat sederhana, tanpa istilah teknis (tidak ada "regex", "index", "path", "payload" di permukaan UI), berupa wizard bertahap dengan tooltip bahasa awam, dan tidak butuh edit JSON manual.

# STACK (ikuti kecuali ada alasan kuat, jelaskan jika menyimpang)
- Python 3.11+
- `openpyxl` untuk .xlsx/.xlsm (mode normal, `data_only=True`, supaya merged cells terbaca). Dukungan .xls opsional via `xlrd`.
- UI desktop: **PySide6** (dialog pilih folder native). CustomTkinter boleh sebagai alternatif.
- Pydantic v2 untuk validasi konfigurasi, pytest untuk test.
- Dikemas jadi `.exe` dengan PyInstaller. Sertakan instruksi dan spec file.
- **Wajib arsitektur terpisah:** `core/` (engine, tanpa dependensi UI), `ui/`, dan `cli.py`. Engine harus bisa dijalankan headless (`python cli.py run --profile pabrik_a.json`) agar bisa dijadwalkan lewat Task Scheduler.

# KONSEP DATA (hierarki)
`Profil` → `Sumber (sub-folder)` → `Sheet` → `Field (aturan ekstraksi)`

## 1. Profil
Satu profil = satu set konfigurasi (misal "Pabrik A"). Disimpan sebagai file JSON. Wajib ada: buat baru, duplikasi (karena 3 pabrik mirip tapi tidak sama), ubah nama, hapus, impor/ekspor.

## 2. Sumber (folder)
- Input satu **folder induk** (mis. `C:\Document\Kerja\Laporan_data_harian\input`) dengan tombol "Pilih Folder".
- Aplikasi memindai dan menampilkan sub-folder yang ada sebagai **daftar centang** (mis. `lap_harian`, `prod_harian`, `penjualan_harian`). User mencentang sub-folder yang dipakai. Tidak perlu mengetik path berulang.
- Tiap sub-folder diasumsikan berisi 1 file Excel (nama file berubah tiap hari).
  - Jika ada lebih dari 1 file, ambil yang **terakhir dimodifikasi** dan beri **peringatan** di audit.
  - Jika kosong atau tidak bisa dibuka (rusak, terkunci, file sementara `~$`), catat sebagai **error** di audit dan lanjutkan ke sumber lain. Jangan crash.
  - Abaikan file `~$*.xlsx`.

## 3. Sheet
Per sub-folder, user bisa menambah **banyak sheet**. Pilih nama sheet dari dropdown yang diisi otomatis dari file sampel, atau ketik manual. Pencocokan nama sheet ikut mode yang sama dengan keyword (poin 5), karena nama sheet kadang berubah (mis. "Produksi 01-10").

## 4. Field (aturan ekstraksi)
Tiap sheet punya **banyak field**. Satu field berisi:
- **Nama hasil** (`output_name`): nama sendiri yang bebas ditentukan user, mis. "Produksi Harian" disimpan sebagai `prod_hi`. Validasi: unik di dalam satu sheet (boleh sama nama di sheet lain — kasus laporan harian), hanya huruf/angka/underscore, tidak boleh kosong.
- **Keyword Baris** dan **Keyword Kolom**.
  - Nilai diambil dari **titik temu**: baris tempat keyword-baris ditemukan dan kolom tempat keyword-kolom ditemukan.
  - Keyword Kolom boleh dikosongkan. Pada kasus itu sediakan opsi sederhana "Ambil nilai di sel sebelah kanan keyword" (dan variasi: kiri/bawah/atas, geser N sel) untuk data non-tabular berbentuk "label: nilai".
- Tiap keyword punya pengaturan:

### 5. Mode pencocokan (UX penting, bukan sintaks `=Produksi Harian`)
Dropdown dengan label awam dan contoh langsung:
| Label UI | Arti |
|---|---|
| **Sama persis** | Isi sel harus persis keyword (abaikan huruf besar/kecil dan spasi berlebih) |
| **Mengandung** | Sel mengandung keyword di mana saja |
| **Diawali dengan** | Sel diawali keyword |
| **Diakhiri dengan** | Sel diakhiri keyword |

(Regex hanya di mode "Lanjutan" yang disembunyikan secara default.)
Default: "Sama persis". Tampilkan teks bantu dinamis, contoh: *"Akan cocok dengan: 'Produksi Harian', 'produksi  harian' — Tidak cocok dengan: 'Produksi Harian Total'"*.
Normalisasi: trim, kecilkan huruf, rapikan spasi ganda, hilangkan newline di dalam sel. Sediakan opsi "Bedakan huruf besar/kecil".

### 6. Checkbox "Keyword ini hanya muncul sekali (unik)"
- **Centang (unik):** user hanya mengisi teks keyword.
  - Jika saat ekstraksi ternyata ditemukan >1 kemunculan → **jangan diam-diam ambil yang pertama**. Tandai status `warning`/`error` "dianggap unik tapi ditemukan N kali", sebutkan semua alamat kandidat di audit.
- **Tidak dicentang:** muncul 3 input tambahan:
  1. **Dropdown cara memilih** dengan 3 opsi:
     - **"Berdasarkan alamat sel"**: pilih kemunculan yang paling dekat ke alamat yang diisi user (mis. `I45`).
     - **"Yang dekat dengan keyword lain"**: pilih kemunculan yang jaraknya paling dekat ke keyword pembanding (mis. "SECTION PRODUKSI").
     - **"Yang TIDAK dekat dengan keyword lain"**: buang kemunculan yang dekat dengan keyword pembanding (mis. "SUMMARY") lalu ambil sisanya.
  2. **Isian pembanding**: alamat sel atau keyword (sesuai opsi). Keyword pembanding juga punya mode pencocokan sendiri.
  3. (Lanjutan, ada default) **Radius "dekat"** dalam jumlah baris, default 10, untuk opsi "tidak dekat".
- Definisi jarak: jarak Chebyshev atau Manhattan pada grid sel (pilih satu, dokumentasikan alasannya). Tie-break deterministik: prioritaskan baris lebih kecil, lalu kolom lebih kecil.
- Jika setelah disambiguasi masih >1 kandidat, atau 0 kandidat → `error` dengan penjelasan jelas. **Jangan menebak diam-diam.**
- Mode "Berdasarkan alamat": jika kandidat terpilih **tidak berada tepat di alamat** (mis. data bergeser dari I45 ke I48), jangan gagal, tetapi catat `address_drift` (alamat acuan, alamat sebenarnya, selisih baris/kolom) sebagai **warning**. Ini sinyal dini bahwa format laporan berubah.

### 7. Pengaturan tambahan per field (sederhana, dengan default aman)
- **Tipe data yang diharapkan:** `Angka`, `Teks`, `Tanggal`, `Apa saja` (default). Jika nilai tidak sesuai (mis. teks "N/A" di field Angka) → warning dan simpan `raw_value` apa adanya.
- **Boleh kosong?** (default: tidak → kosong = warning)

# PERILAKU ENGINE
- Muat setiap sheet sekali lalu bangun **indeks sel** (`dict normalized_text → list[(row, col)]`) supaya pencarian cepat, bukan scan ulang per field.
- **Merged cells:** jika sel target ada dalam merge range, baca nilai dari sel kiri-atas range, dan catat `merged: true` serta range-nya.
- **Rumus:** baca nilai hasil (cached). Jika `None` karena file tidak pernah dihitung/disimpan oleh Excel → warning "rumus belum terhitung".
- **Baris/kolom tersembunyi:** catat flag `hidden` pada hasil, tetapi tetap boleh diekstrak.
- **Error Excel** (`#REF!`, `#DIV/0!`, dll.): ekstrak sebagai raw string dan beri status `warning`.
- **Tanggal:** konversi ke ISO 8601. **Angka:** pertahankan numerik. Jangan memaksa format lokal Indonesia secara diam-diam.
- Satu field gagal tidak boleh menghentikan field lain. Semua error ditangkap per field dan dicatat.
- Engine harus deterministik: input sama → output identik.
- Konfigurasi divalidasi sebelum eksekusi, dengan pesan error berbahasa awam, mis. "Field 'prod_hi': Keyword Baris belum diisi".

# OUTPUT JSON
Satu file hasil per eksekusi, mis. `output/{profil}_{YYYYMMDD_HHMMSS}.json`. Struktur kira-kira (boleh disempurnakan, jelaskan perubahan):

```json
{
  "meta": {
    "app_version": "1.0.0",
    "profile": "Pabrik A",
    "run_at": "2026-10-14T08:30:00+07:00",
    "input_root": "C:\\Document\\Kerja\\Laporan_data_harian\\input",
    "summary": {"total_fields": 24, "ok": 21, "warning": 2, "error": 1}
  },
  "data": {
    "prod_hi": {
      "value": 1523.5,
      "status": "ok",
      "source": {
        "folder": "prod_harian",
        "file": "Prod_14Okt2026.xlsx",
        "file_modified": "2026-10-14T07:55:10+07:00",
        "sheet": "Produksi"
      },
      "location": {
        "value_address": "L45",
        "row_keyword_address": "I45",
        "col_keyword_address": "L12"
      },
      "value_meta": {"raw_value": "1523.5", "type_found": "number", "merged": false, "hidden": false, "from_formula": true}
    }
  },
  "audit": {
    "fields": [
      {
        "field": "prod_hi",
        "status": "ok",
        "row_keyword": {"text": "Produksi Harian", "match_mode": "exact", "is_unique": false, "candidates": ["I45", "I94"], "selected": "I45", "disambiguation": "by_address", "reference": "I45", "drift": null},
        "col_keyword": {"text": "Total", "match_mode": "exact", "is_unique": true, "candidates": ["L12"], "selected": "L12"},
        "warnings": [],
        "errors": []
      }
    ],
    "issues": [
      {"field": "...", "level": "warning", "code": "ADDRESS_DRIFT", "message": "Keyword 'Produksi Harian' ditemukan di I48, acuan I45 (bergeser 3 baris)."}
    ]
  }
}
```

Daftar kode isu minimal: `FILE_NOT_FOUND`, `FILE_UNREADABLE`, `MULTIPLE_FILES`, `SHEET_NOT_FOUND`, `KEYWORD_NOT_FOUND`, `UNIQUE_VIOLATION`, `AMBIGUOUS_AFTER_DISAMBIGUATION`, `ADDRESS_DRIFT`, `EMPTY_VALUE`, `TYPE_MISMATCH`, `FORMULA_NOT_CALCULATED`, `EXCEL_ERROR_VALUE`, `MERGED_CELL`.

Penambahan (Fase 1, ditambahkan ke spesifikasi lebih dulu sesuai aturan):
- `SHEET_AMBIGUOUS`: satu nama sheet cocok ke beberapa sheet di file (dipakai bersama aturan "jangan menebak diam-diam").
- `INTERNAL_ERROR`: kesalahan tak terduga pada satu field; detail lengkap ditulis ke file log, UI tetap menampilkan pesan ramah.

Tingkat isu (dipakai engine): `error` → `FILE_NOT_FOUND`, `FILE_UNREADABLE`, `SHEET_NOT_FOUND`, `SHEET_AMBIGUOUS`, `KEYWORD_NOT_FOUND`, `UNIQUE_VIOLATION`, `AMBIGUOUS_AFTER_DISAMBIGUATION`, `INTERNAL_ERROR`; `warning` → sisanya (`MULTIPLE_FILES` dicatat per sumber, bukan per field).

Tambahan di UI: tombol **"Simpan Laporan Audit"** (CSV atau HTML sederhana) berisi semua isu, diurutkan dari yang paling parah.
**Fase lanjutan (opsional):** bandingkan dengan hasil run sebelumnya dan beri peringatan jika nilai berubah melebihi ambang yang ditentukan user (deteksi data melenceng).

# UI/UX (wajib)
Wizard / layout 3 panel yang ramah non-IT:
1. **Langkah 1 – Sumber:** pilih folder induk → centang sub-folder.
2. **Langkah 2 – Data yang diambil:** pohon `Sub-folder > Sheet > Field`,
   dengan tombol "+ Tambah Sheet", "+ Tambah Data", duplikasi field/sheet (duplikasi sheet menyalin semua field-nya ke sheet lain dengan aturan yang sama — kasus laporan harian yang satu tanggal satu sheet — dan salinan memakai nama hasil yang sama dengan sheet aslinya, karena nama hanya perlu unik di dalam satu sheet), hapus.
   Urutan sheet dan field bisa diubah dengan **menggeser barisnya** (drag and drop), tanpa mengubah isi aturannya. Urutan field menentukan urutan hasil (baris pada tabel hasil dan urutan kunci di file JSON). Hanya boleh geser di dalam folder yang sama (untuk sheet) dan di dalam sheet yang sama (untuk field); geseran lain diabaikan tanpa pesan. Baris yang sedang dibuka pengguna (sub-folder/sheet) tetap terbuka setelah setiap perubahan, dan baris yang baru ditambah/diubah selalu ikut terbuka serta tersorot.
3. **Langkah 3 – Jalankan & Periksa:** tombol "Jalankan Ekstraksi", ringkasan status berwarna (🟢 OK / 🟡 Perlu dicek / 🔴 Gagal), tabel hasil, dan tombol simpan JSON.

**Form field** harus berbahasa awam, dengan label seperti "Nama untuk hasil ini", "Cari baris yang bertuliskan…", "Cari kolom yang bertuliskan…", dan checkbox "Tulisan ini hanya muncul satu kali di sheet". Tampilkan ikon bantuan (?) dengan contoh. Pilihan tambahan ("Kalau muncul lebih dari sekali…") hanya muncul bila checkbox tidak dicentang.

**Preview hasil (fitur kunci):**
- User memilih satu **file sampel**. Preview menjalankan field yang sedang diedit secara langsung (real-time, debounce).
- Tampilkan: nilai yang ditemukan, alamat sel, status warna, dan jumlah kemunculan keyword.
- Tampilkan **mini-grid cuplikan sheet** (± 5 baris/kolom di sekitar hasil) dengan sorotan warna: sel keyword baris, sel keyword kolom, sel nilai. Ini membuat user bisa memverifikasi visual tanpa membuka Excel.
- Jika ada kandidat ganda, daftar semuanya dengan alamat, dan tandai mana yang terpilih beserta alasannya.

Tambahan: pesan error ramah (jangan tampilkan stack trace ke user, simpan di log file), auto-save profil, konfirmasi sebelum hapus, ingat folder terakhir, dan UI tidak freeze saat memproses (gunakan worker thread).

# KUALITAS
- Test pytest untuk engine: setiap mode pencocokan, tiga mode disambiguasi, unique violation, address drift, merged cells, rumus tanpa cache, sheet tidak ada, file kosong/rusak, keyword kolom kosong + offset.
- Sertakan **generator file Excel sampel yang sengaja berantakan** (tidak tabular, keyword duplikat di section berbeda, merged cells, data bergeser antar "pabrik") untuk dipakai test dan demo.
- Type hints dan docstring pada API engine. Logging ke file.
- README Bahasa Indonesia: instalasi, cara pakai singkat untuk non-IT, cara build `.exe`, dan cara memakai CLI.

# CARA KERJA (penting, ikuti urutan ini)
Jangan langsung menulis semua kode. Kerjakan bertahap dan **berhenti di akhir tiap fase** menunggu konfirmasi saya:

- **Fase 0:** ringkas pemahamanmu, daftar asumsi, pertanyaan yang benar-benar perlu dijawab (maksimal 5), struktur folder project, dan skema konfigurasi profil (JSON schema / model Pydantic).
- **Fase 1:** `core/` lengkap (model, indeks sel, matcher, disambiguator, extractor, audit, penulis JSON) + CLI + test + generator file sampel.
- **Fase 2:** UI PySide6 (wizard, form field, preview dengan mini-grid).
- **Fase 3:** laporan audit, perbandingan antar run, packaging `.exe`, README.

Mulai dari **Fase 0** sekarang.

---

# REVISI v2 (perilaku ekstraksi, skema output, integrasi)

Revisi ini menggantikan aturan berikut di dokumen di atas: merged cell (poin 1),
penanganan tanggal/sheet dinamis (poin 2), penentuan identitas item (poin 3),
bentuk OUTPUT JSON (poin 4), dan integrasi client (poin 5). Sisanya tetap.

## 1. Merged cell
- Nilai sel yang merged **selalu dari sel kiri-atas (anchor)**. Label/keyword yang
  jatuh di sel non-anchor di-resolve ke anchor range itu (dipakai juga untuk alamat
  yang dilaporkan).
- Resolusi anchor **bukan warning**: status `ok`, tidak perlu review.
- Isu hanya bila anchor kosong/tidak valid → tetap `EMPTY_VALUE` / `TYPE_MISMATCH`.
- `merged_range` ditulis di mode `full`, atau di mode `compact` hanya bila sel itu
  punya isu lain. Kode `MERGED_CELL` tidak lagi dipakai engine v2 (disimpan sebagai
  kode lama agar berkas hasil v1 tetap terbaca).

## 2 & 3b. Sheet dinamis, `key`, tanggal
- Profil memetakan field untuk **satu sheet template**, dan opsi `every_sheet: true`
  memakai mapping yang sama untuk **semua sheet yang cocok** dengan pola `name`
  (mis. pola `"DD"`). Tanpa `every_sheet`, satu pola = satu sheet (perilaku lama:
  `SHEET_AMBIGUOUS` bila cocok lebih dari satu).
- **Sheet yang tidak ada bukan error**: template yang tidak cocok sheet mana pun
  tidak menghasilkan item, hanya dicatat `SHEET_ABSENT` (warning, satu kali per template).
  Kode `SHEET_NOT_FOUND` tidak lagi dipakai engine v2 (disimpan seperti `MERGED_CELL`
  agar berkas hasil v1 tetap terbaca): profil yang memetakan sheet 01-16 sementara file
  hari itu baru berisi 01-14 tidak lagi menghasilkan baris "gagal" per sheet.
  Isu tetap ada di `audit.issues` dan dicetak CLI; UI Langkah 3 menyaringnya dari
  daftar catatan karena baris sheet merah di Langkah 2 sudah menandainya (keputusan user).
- Sheet yang tidak memenuhi template mana pun dicatat diam-diam di
  `meta.unmatched_sheets` (`{"folder", "file", "sheet", "reason"}`) tetapi tidak
  menghasilkan isu/warning/error apa pun — sheet yang tidak terpakai biarkan saja
  (keputusan user 2026-10-15). `SHEET_UNMATCHED` hanya untuk sheet yang sudah cocok
  template tetapi gagal pola identitas.
- `key` (di level profil) menentukan identitas item:
  `{"from": "label" | "table_column" | "sheet_name" | "none", "label", "type":
  "date" | "text", "format", "fallback", "file_pattern"}`.
  - `label` / `table_column`: teks sel berlabel (label = judul kolom untuk mode baris).
  - `sheet_name`: hari/bulan dari nama sheet sesuai `format` (`DD`, `D MMM`,
    `DD-MM-YYYY`), bulan/tahun dari urutan prioritas: (1) sel berlabel di sheet,
    (2) nama file sesuai `file_pattern`, (3) input manual per run
    (`--month`/`--year` di CLI, `?month=&year=` di API). Dilarang menebak dari
    `file_modified` atau tanggal hari ini.
  - `fallback` dipakai bila sumber utama tidak terbaca (mis. `sheet_name`).
  - `key` yang tidak terbaca: item **tetap dikeluarkan** tanpa field `key`
    (field `key` hanya ditulis bila identitasnya ada), `status: "error"`,
    plus isu `KEY_NOT_FOUND`. Tidak dilewati diam-diam.
  - Tanggal dari isi sheet ≠ tanggal dari nama sheet → `DATE_CONFLICT` (error),
    tidak memilih salah satu.
  - Hari yang tidak ada di bulan itu (mis. "31" di bulan 30 hari) → item tanpa
    field `key`, `status: "error"`, isu `KEY_NOT_FOUND`.
- Tanggal ISO 8601 dipakai untuk key bertipe `date`.
- `mode: "sheet"` (default): satu sheet = satu item. `mode: "rows"`: setiap baris
  data = satu item; baris dikenali dari isi kolom key (label kolom tabel), bukan
  posisi baris, sehingga berkas tanggal 1-15 dan 1-31 diproses dengan mapping yang
  sama. Di mode `rows`, `col_keyword` wajib dan `row_keyword` tidak dipakai.
- **Mapping massal**: `python cli.py mapping suggest --file F --sheet S` membuat
  daftar field draf dari satu sheet contoh (label yang punya nilai di kanan/bawahnya),
  dan `mapping export` / `mapping import` memindahkan mapping sebagai CSV
  (atau JSON profil seperti sekarang). CSV memuat kolom sederhana
  (`folder, sheet, output_name, row_keyword, col_keyword, direction, offset,
  data_type, allow_empty`); pengaturan lanjutan (mode pencocokan, disambiguasi)
  hanya lewat JSON profil.
## 4. Skema output v2 (mode `compact` = default)
- Berkas hasil: `output/{profil}_{YYYYMMDD_HHMMSS}.json`, isinya `{"meta", "data"}`
  (tanpa `audit`; audit tetap tersedia di aplikasi). `data` dikelompokkan per folder
  sumber, lalu per sheet: `{folder: {sheet: [entri, ...]}}` — berupa daftar karena
  mode `rows` bisa menghasilkan lebih dari satu entri per sheet (keputusan user).
- `input_root` dan path absolut tidak ditulis (tidak boleh bocor ke client).
- `source` ditulis sekali per item. `values` hanya `key: value`; detail masalah
  masuk `issues`. Field yang tidak ada di `issues` berarti `ok`. Status `error`
  berarti nilainya `null` di `values` (tanpa angka tebakan).
- Item: `{key?, status, source: {folder, file, file_modified}, sheet, values,
  issues, content_hash}`; `key` hanya ditulis bila identitas terbaca (tanpa
  identitas field-nya tidak muncul, bukan null); `status` item = `error` bila ada
  nilai error atau key hilang, `warning` bila ada warning, selain itu `ok`.
- Entri `issues`: `{status, code, at, raw?, merged_range?}` — `code` memakai kode
  isu di dokumen ini, `at` = alamat sel, `raw` hanya bila teks tersimpan berbeda
  dari nilai, `merged_range` hanya bila sel itu merged.
- `content_hash`: SHA-256 dari `values` saja (JSON kanonik, kunci terurut) sehingga
  tidak berubah karena `run_at`.
- `meta`: `{app_version, schema_version: 2, mode, profile, run_at, summary:
  {sheets, total_fields, ok, warning, error}, unmatched_sheets}`. `sheets` = jumlah
  sheet yang diproses, hitungan `ok/warning/error` per **nilai** (item x field).
- Mode `full` (flag CLI `--mode full`, parameter API `?mode=full`): tiap item
  menambah `detail: {field: {status, value_address, row_keyword_address,
  col_keyword_address, raw_value, type_found, merged_range, from_formula, hidden}}`.
- JSON Schema untuk validasi client: `docs/schema/result-v2.json` (draft 2020-12),
  berlaku untuk compact maupun full, dilayani di `GET /schema`.

## 5. Integrasi (API, tanpa dependensi baru)
`python cli.py serve --profile P [--input F] [--output O] [--host 127.0.0.1] [--port 8765]`
menjalankan ekstraksi sekali, menyimpan berkas hasil v2, lalu melayani:

- `GET /reports?from=&to=&changed_since=&hashes=` → envelope
  `{meta, items: [...]}` (JSON minified). `from`/`to` menyaring `key` bertipe
  tanggal (ISO, inklusif). `changed_since` menyaring berdasarkan `run_at`
  (satu proses = satu snapshot; jalankan ulang dengan `?refresh` belum ada).
  `hashes=a,b,c` membuang item yang `content_hash`-nya sudah dimiliki client
  (engine tetap stateless: client yang mengirim hash-nya).
- `GET /reports/{key}?mode=full` → `{meta, item}`.
- `GET /schema` → JSON Schema di atas.
- Error: JSON `{"error": "..."}` dengan status 400/404/405; tanpa stack trace.

Kode isu baru (wajib ada di sini sebelum dipakai engine):
`DATE_CONFLICT` (error), `KEY_NOT_FOUND` (error), `SHEET_ABSENT` (warning),
`SHEET_UNMATCHED` (warning, hanya untuk sheet yang cocok template tetapi gagal
  pola identitas; sheet yang tidak diclaim template mana pun tidak menghasilkan isu).
Webhook push ke client **belum dibuat** (opsional di poin 5).
UI belum punya tombol untuk `every_sheet`, mode `rows`, key, dan mapping massal
(dipakai lewat profil JSON/CLI); itu pekerjaan lanjutan.
