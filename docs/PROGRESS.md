# PROGRESS

## Done
- Fase 0: pemahaman, asumsi, struktur folder, skema konfigurasi profil.
  Konfirmasi user: penyimpanan di samping aplikasi; perbandingan antar run dikerjakan di Fase 3;
  dukungan `.xls` menyusul (fokus .xlsx/.xlsm dulu); dependensi wajib pakai venv (`.venv`).
- Fase 1 (lengkap):
  - `core/`: models.py (Pydantic v2), matcher.py, cell_index.py, disambiguator.py,
    extractor.py, audit.py, json_writer.py, profiles.py (CRUD), logging_config.py, paths.py.
  - `cli.py`: `run` / `validate` / `list-profiles`, exit code 0/1/2 untuk Task Scheduler.
  - `tools/generate_samples.py`: 3 varian "pabrik" sengaja berantakan (duplikat keyword,
    merged, rumus tanpa cache, baris/kolom tersembunyi, data bergeser, file `~$`).
  - 105 test pytest; quality gate lolos: `pytest` (105 passed), `ruff check .` (clean),
    `mypy core` (strict, 11 file, no issues).
- `docs/SPEC.md`: tambah kode `SHEET_AMBIGUOUS` & `INTERNAL_ERROR` + tabel tingkat isu (sesuai aturan: kode baru masuk spesifikasi dulu).
- Setup: `.venv`, `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` (pytest/ruff/mypy), `.gitignore`.
  `.gitignore` dirapikan: data lokal (profiles, settings.json, logs, output, samples), `.env`,
  `build`/`dist`/`*.spec.bak`, dan `.DS_Store` diabaikan; `init` (dokumen brief) tetap dilacak.
  Pola diuji di repo git sementara: 13/13 berkas lokal terabaikan, hanya sumber proyek yang dilacak.

- Fase 2 (lengkap):
  - `ui/`: `main_window.py` (bar profil + wizard 3 langkah, auto-save), `step1_sources.py`
    (folder induk + daftar sub-folder bercentang), `step2_fields.py` (pohon folder > sheet > data,
    tambah/ubah/duplikat/hapus), `step3_run.py` (jalankan, tabel hasil berwarna, daftar catatan,
    simpan salinan JSON), `field_form.py` (form berbahasa awam + preview), `preview.py`
    (mini-grid), `worker.py` (QThread untuk run & preview), `settings.py`, `sample_files.py`,
    `main.py` (entry point di root juga menyusul: `python main.py`).
  - `tests/test_ui_smoke.py`: 5 test asap (Qt `offscreen`) — window terbuka, halaman wizard
    mengikuti profil, tombol "Jalankan Ekstraksi" mengisi tabel hasil + menulis JSON,
    tombol "+ Tambah Data" membuka form dan menyimpan keyword, mode "Lanjutan" tetap tersembunyi.
  - 110 test pytest; quality gate lolos: `pytest` (110 passed), `ruff check .` (clean),
    `mypy core` (strict, 11 file, no issues).
- Perbaikan bug yang ketemu saat Fase 2: `core/profiles.py` belum mengimpor `SourceConfig`
  (F821 / mypy name-defined), `QToolTip` salah diimpor dari `QtGui` (ada di `QtWidgets`),
  impor `range_boundaries` tak terpakai di `ui/worker.py`.
- Perbaikan bug Fase 2 (dilaporkan user sebagai "tidak bisa menambah data/keyword"):
  `ui/field_form.py` memanggil `QStandardItem.setVisible(False)` untuk menyembunyikan mode
  "Lanjutan". Qt6 tidak punya API itu, jadi tiap kali form "+ Tambah Data"/"Ubah" dibuka,
  `AttributeError` naik di dalam slot Qt: form tidak pernah muncul, pesan error hanya ke
  terminal (bukan ke UI maupun log). Diganti dengan cara Qt6: sembunyikan baris popup
  `self.mode_combo.view().setRowHidden(HIDDEN_MODE_INDEX, True)`. Dijaga 2 test baru di
  `tests/test_ui_smoke.py` (alur klik tombol + mode "Lanjutan" tetap ada di daftar).
- Perbaikan bug Fase 2 (dilaporkan user sebagai banjir traceback
  `libshiboken: Internal C++ object (PreviewWorker) already deleted`): kedua worker thread
  memakai `deleteLater()` saat selesai, tapi referensi Python (`self._worker`) dibiarkan
  menunjuk ke objek C++ yang sudah dihapus. Setiap suntingan berikutnya menyentuh referensi
  itu di `ui/preview.py:_start_pending` → `RuntimeError` di dalam slot timer (ratusan kali),
  dan `ui/step3_run.py:stop()` kena pola sama saat jendela ditutup setelah ekstraksi selesai.
  Akar masalah diperbaiki sekali di kedua tempat: referensi dilepas tepat saat thread selesai
  (`ui/preview.py:_on_finished`, `ui/step3_run.py:_on_worker_finished`). Dijaga 1 test baru
  `test_preview_survives_a_second_run`; kedua skrip repro di `/tmp` membuktikan 2 traceback
  sebelum perbaikan, 0 sesudahnya.
- 111 test pytest; quality gate lolos: `pytest` (111 passed), `ruff check .` (clean),
  `mypy core` (strict, 11 file, no issues).
- Perbaikan bug (dilaporkan user: `python main.py` → `zsh: segmentation fault`, macOS bilang
  "Python berhenti mendadak"):
  Akar masalah: `SheetDialog` dan `FieldFormDialog` (ui/step2_fields.py) adalah subclass QDialog
  buatan Python. Setelah `exec()` selesai, wrapper Python-nya dibiarkan jadi sampah, dan bentuknya
  siklus (dialog → PreviewPane → bound method dialog). Saat garbage collector berjalan — termasuk
  di dalam thread `RunWorker`/`PreviewWorker` yang mengalokasi banyak objek — PySide6 membongkar
  pohon widget itu menurut urutan GC dan memanggil destruktor C++ untuk objek yang sudah dihapus
  (stack crash: `gc_collect_main` → `SbkObject_tp_clear` → `callCppDestructor<QWidget>`) → SIGSEGV.
  Ini versi dialog dari catatan lama "window harus dimatikan eksplisit".
  Perbaikan (kode terkecil, tanpa fitur baru): setelah `exec()`, baca hasilnya lalu
  `dialog.deleteLater()` supaya Qt yang membongkar dialog di GUI thread — di kedua tempat.
  Bukti: repro cocoa baru membuka form lewat kode aplikasi lalu memaksa GC di dalam thread
  RunWorker — kode lama crash 1/1 (exit 138), sesudah perbaikan 0/4; kontrol `plain_drop`
  di `/tmp/probe5.py` crash 3/3, varian `deleteLater`/`break_cycle` 0/3. Crash ini hanya
  tereproduksi dengan plugin cocoa (offscreen tidak), jadi tes regresi baru
  `test_closed_dialogs_are_torn_down_by_qt_not_the_gc` menjaga panggilan teardown eksplisitnya,
  bukan segfault-nya.
- 112 test pytest; quality gate lolos: `pytest` (112 passed), `ruff check .` (clean),
  `mypy core` (strict, 11 file, no issues).

## Lokalisasi (Indonesia + Inggris, tanpa mengubah fitur)
- `ui/i18n.py`: satu sumber untuk semua teks UI. `t(key, **kwargs)` + `set_language()` +
  `LANGUAGES` (id/en). Bahasa default Indonesia → perilaku & test lama tetap hijau.
  Placeholder `{...}` diisi lewat `t(**kwargs)`; key tak dikenal dikembalikan apa adanya.
- Pemilih bahasa di bar atas `MainWindow` (combo "Bahasa:"), disimpan di `settings.json`
  (kunci `language`) dan diterapkan saat aplikasi dibuka. Ganti bahasa langsung me-retranslate
  window + 3 halaman wizard (pola `retranslate()`), termasuk header tabel hasil.
- Teks UI dipindahkan ke kunci i18n di: `main_window.py`, `step1_sources.py`, `step2_fields.py`,
  `step3_run.py`, `field_form.py` (konstanta label → fungsi `*_labels()`), `preview.py`
  (`_STATUS_TEXT`/`_DISAMBIGUATION_TEXT` → fungsi), `worker.py`. Logika/aturan ekstraksi tidak disentuh.
  Pesan error `core/` & `cli.py` tetap Indonesia (engine tidak mengimpor UI, sesuai arsitektur).
- `tests/test_i18n.py`: 9 test (bahasa default Inggris, ganti bahasa, kode tak dikenal,
  placeholder id/en, key tak dikenal, setiap key punya id+en tak kosong, placeholder konsisten
  antar bahasa, label status pakai emoji asli bukan entity HTML).
- 121 test pytest; quality gate lolos: `pytest` (121 passed), `ruff check .` (clean),
  `mypy core` (strict, 11 file, no issues).

### Perbaikan kontras & emoji status (usulan user)
- Default bahasa diganti ke **Inggris** (`DEFAULT_LANGUAGE = "en"`); Indonesia tetap bisa dipilih
  dan tetap fallback bila ada key yang belum diterjemahkan. Test yang dulu berasumsi teks Indonesia
  (`perlu dicek`, `Lanjutan`) disesuaikan ke padanan Inggris.
- Bug: status pakai HTML entity `&#128994;` (🟢) yang **tidak** dirender QLabel teks-biasa → muncul
  literal `&#128994;`. Diganti karakter emoji asli 🟢🟡🔴.
- Bug kontras: di dark mode, teks `QTableWidgetItem` (step 3) & status preview mengikuti warna font
  tema sistem (putih) di atas latar terang → tak terbaca. Kini teks diberi warna gelap eksplisit
  (`#212121`); status preview jadi "pill" latar terang + teks gelap, konsisten dengan tabel hasil.
  Terverifikasi: fg lum≈33 di atas bg lum≈239.

### Kontras panel Pratinjau Langkah 2 (keluhan user) + sisa lokalisasi
- Laporan user: di Langkah 2 kotak nilai tampak putih berteks putih, dan sel bersorot krem berteks
  putih. Sebabnya sisa perbaikan sebelumnya yang belum menjangkau panel ini: `_fill_grid` memberi
  latar terang (`#FFE0B2` krem, `#BBDEFB`, `#C8E6C9`) dan `value_label` berlatar `#F5F5F5` **tanpa**
  warna teks eksplisit → di dark mode Qt memakai teks putih tema (putih di atas putih, kontras ≈ 1).
- Perbaikan (satu file, `ui/preview.py`): konstanta `_TEXT_ON_LIGHT` = `#212121` dipakai bersama oleh
  pil status, sel bersorot grid, dan kotak nilai (`_BOX_BG`); dua hardcoded `#666666` (abu-abu tema
  terang) pada label detail dan status "membaca file" dihapus supaya ikut warna teks tema.
  Terukur (palet dark disimulasikan, offscreen): sel `1523.5` 1.27 → 12.70, sel `Produksi Harian`
  1.40 → 11.47, kotak nilai 14.77.
- Bug ikutan di fungsi yang sama: sorotan sel gabungan (merged) memakai nomor kolom mutlak
  (`col_idx + 1`), padahal cuplikan bisa mulai di kolom lain → sel gabungan tak pernah tersorot bila
  grid tidak mulai dari kolom A. Kini memakai `column_index_from_string(col_letters[col_idx])`.
- Sisa lokalisasi: satu-satunya kalimat UI yang masih hardcoded (`"Membaca file sampel..."`) pindah ke
  kunci `pv.loading` (id/en); docstring `ui/i18n.py` dikoreksi (default = Inggris). Bahasa tersimpan
  di `settings.json` user sudah `"language": "en"`.
- Tes regresi: `test_preview_text_stays_readable_on_its_light_fills` (palet dark disimulasikan → setiap
  sel berlatar terang wajib kontras ≥ 4.5). Diuji menggigit: pada kode lama gagal
  (`'Total' unreadable: contrast 1.34`), sesudah perbaikan lolos.
- 122 test pytest; quality gate lolos: `pytest` (122 passed), `ruff check .` (clean),
  `mypy core` (strict, 11 file, no issues); boot cocoa nyata (`python main.py`) exit 0.


### Fitur duplikat sheet (kasus laporan harian: 1 tanggal = 1 sheet)
- Permintaan user: kalau sebuah sheet (tanggal) sudah punya aturan pengambilan data, sheet tanggal lain
  punya aturan yang sama → tidak perlu memasukkan ulang field satu per satu.
- Implementasi (satu file, `ui/step2_fields.py`, tanpa perubahan di `core/`): tombol **Duplikat** yang
  sudah ada kini aktif juga saat baris **Sheet** dipilih. `_duplicate_selected` mengarahkan ke
  `_duplicate_sheet` (sheet) atau membiarkan `_duplicate_field` (field) seperti sebelumnya. Dialog sheet
  yang sudah ada dipakai ulang untuk memilih **nama sheet baru** + mode pencocokan. Setiap field disalin
  `model_copy(deep=True)` sehingga aturan (baris/kolom, mode pencocokan, disambiguasi, tipe data,
  allow_empty) ikut apa adanya; hanya `output_name` yang berubah karena SPEC mewajibkan nama hasil unik
  per profil. Boilerplate daftar judul sheet yang sama dipakai `_add_sheet` juga → dijadikan
  `_sheet_titles`.
- Aturan nama salinan (`_free_output_name`): `base`, lalu `base_2`, `base_3`, ... mengikuti angka
  terkecil yang belum terpakai. Kalau nama sudah berakhiran angka **dan** nama dasarnya sudah dipakai
  profil, seri dilanjutkan (`prod_hi_2` → `prod_hi_3`); kalau tidak, akhiran ditambah apa adanya
  (`harga_2024` → `harga_2024_2`, tahunnya tidak hilang). Nama tetap bisa diubah lewat tombol Ubah.
- Salinan selalu masuk ke sumber folder yang sama dengan sheet asalnya; duplikasi tidak menyalin ke
  folder lain (belum diminta).
- Uji alur nyata (skrip sekali pakai): sheet kedua berisi layout identik ditambahkan ke file sampel,
  sheet lamanya diduplikat, lalu ekstraksi dijalankan → `prod_hi` ok dari sheet "Produksi" dan
  `prod_hi_2` ok dari "Produksi 02-10" (nilai sama 1523.5), 25 baris hasil, tanpa warning.
- Catatan penting dari uji itu: kalau sheet tanggal memakai pencocokan **"Mengandung"** dan nama
  tanggalnya mengandung nama sheet lama (mis. `Produksi` vs `Produksi 02-10`), dua entri sheet sama-sama
  cocok → field jadi `SHEET_AMBIGUOUS` (memang perilaku SPEC: tidak menebak diam-diam). Dialog sheet
  defaultnya **"Sama persis"**, dan itulah yang tepat untuk sheet tanggal. Sekarang belum ada tombol
  "Ubah" untuk entri sheet itu sendiri (untuk mengganti nama/mode sheet harus hapus lalu tambah lagi) —
  belum diminta, dicatat sebagai kandidat berikutnya.
- Tes: `test_duplicate_sheet_copies_every_field_to_a_new_sheet` (duplikat 2× berturut-turut dari sheet
  dan dari salinannya; memeriksa nama sheet, jumlah field, `output_name`, dan bahwa aturan
  baris/kolom ikut tersalin; `QMessageBox.warning` dipantau supaya kegagalan validasi muncul sebagai
  assert, bukan modal yang menggantung) dan `test_free_output_name_skips_a_name_the_profile_already_uses`.
  Diuji menggigit: dengan tombol duplikat dinonaktifkan untuk sheet, tes gagal (`assert False`).
- **Urutan sheet & data bisa diubah dengan drag and drop** (permintaan user: "fitur reorder sheet dan
  data ada gak?" — sebelumnya tidak ada sama sekali: urutan hanya berubah dengan hapus lalu tambah ulang).
  - Tetap satu file UI (`ui/step2_fields.py`, tanpa perubahan `core/`): kelas `OrderTree` (subclass
    `QTreeWidget`) hanya **melaporkan** gesturnya dan tidak membiarkan Qt memindahkan baris sendiri
    (`dropEvent` → `event.ignore()`); `StepData._reorder` menulis urutan baru ke profil lalu memanggil
    `_apply_sources` (validasi + auto-save + `refresh()`).
  - Hanya diizinkan di dalam folder yang sama (sheet) dan di dalam sheet yang sama (data). Geseran lain
    (data ke sheet lain, sheet ke folder lain) diabaikan tanpa pesan: memindahkan data ke sheet lain itu
    *edit*, bukan reorder, dan belum diminta. Baris folder dibuat tidak bisa di-drag.
  - Menjatuhkan pada baris induknya (folder/sheet) = pindah ke urutan terakhir. Urutan inilah yang
    diikuti hasil: baris tabel hasil dan urutan kunci di JSON (dibuktikan dengan run nyata).
  - Teks bantuan halaman ditambah satu kalimat ("Geser barisnya untuk mengubah urutan") di `ui/i18n.py`.
  - Tes: `test_drag_and_drop_reorders_fields_and_sheets` dan
    `test_drag_and_drop_ignores_moves_across_sheets_and_folders`. Gesturnya disimulasikan (`itemAt` dan
    `dropIndicatorPosition` diarahkan, lalu `dropEvent` dipanggil) karena Qt offscreen tidak pernah
    mengirim drag asli. Diuji menggigit: dengan `dropEvent` dibuat langsung `return`, tes reorder gagal.
- 126 test pytest; quality gate lolos: `pytest` (126 passed), `ruff check .` (clean),
  `mypy core` (strict, 11 file, no issues); boot cocoa nyata exit 0; uji gestur dengan koordinat asli di
  jendela nyata: `prod_hi` pindah ke bawah `prod_formula` (profil dan pohon), lalu run nyata →
  `prod_formula` jadi kunci pertama hasil.


## Next
- Fase 3: laporan audit CSV/HTML, perbandingan antar run (ambang %), packaging `.exe` (PyInstaller + spec file), README Bahasa Indonesia.
  (README sudah ditulis lebih awal dari jadwal atas permintaan user: `README.md` di root — instalasi, cara pakai jendela, CLI + Task Scheduler, lokasi file, pemecahan masalah, cara data latihan, catatan pengembang, dan daftar fitur yang belum ada.)
- Uji manual UI oleh user (buka `python main.py`, buat profil, jalankan ekstraksi) — belum dijalankan dengan objek Qt yang terlihat.

## Tes mapping & API (revisi v2)
- `tests/test_mapping.py` (9 test): `suggest_csv` mengusulkan label yang punya nilai di kanan/bawah,
  menolak sheet yang tidak ada (`MappingError`) dan file yang tak bisa dibuka (`ExcelFileError`),
  serta menulis CSV yang sama seperti yang dikembalikan; `export_csv` → `import_csv` → `export_csv`
  menghasilkan berkas identik (semua kolom yang bisa diwakili CSV selamat); pengaturan sederhana
  (arah `down`, offset 2, tipe `number`, `allow_empty`) terbaca apa adanya; pesan galat menyebut
  kolom yang kurang, nomor baris yang salah, berkas kosong, dan berkas tak terbaca.
- `tests/test_api.py` (12 test): server dijalankan di port bebas (thread daemon) dengan penyedia snapshot
  buatan; `/reports` mengembalikan `meta` + `items` (mode `compact`, tanpa `detail`), `/reports/<kunci>?mode=full`
  mengembalikan `meta` + `item` berikut `detail` (alamat sel `L45`), `hashes` menyaring item yang sudah dimiliki
  klien, `from`/`to` menyaring tanggal, `changed_since` yang lebih baru dari `run_at` mengembalikan daftar kosong,
  `/schema` dilayani sebagai `application/schema+json`, dan galat 400 (mode/bulan salah, penyedia tidak dipanggil),
  404 (kunci/alamat tak dikenal), 405 (POST) berisi pesan Bahasa Indonesia. Periode manual (`?month=&year=`)
  terbukti sampai ke penyedia.
- 152 test pytest; quality gate lolos: `pytest` (152 passed), `ruff check .` (clean),
  `mypy core` (strict, 14 file, no issues).
- Uji asap CLI pada pohon sampel sementara (dihapus lagi setelah uji):
  `cli.py run --mode full` menulis `<nama>_<cap waktu>_full.json` berisi `meta`/`data` dengan `meta.mode = full`
  dan `detail` per field; `mapping export`, `mapping suggest` (4 usulan dari sheet `Penjualan`),
  `mapping import` menolak tanpa `--replace` (exit 2) dan menyimpan 14 data dari 3 folder dengan `--replace`;
  `serve` menjawab `/reports` (JSON `meta`+`items`), `/schema` (200 `application/schema+json`), 400 untuk
  mode/bulan salah, 404 untuk alamat tak dikenal, 405 untuk POST.


## Open questions
- Tidak ada (keputusan Fase 0 sudah dikonfirmasi user).

## Keputusan implementasi Fase 1 (untuk Fase 2/Fase 3)
- Jarak disambiguasi: Chebyshev, radius default 10 sel, tie-break baris lalu kolom.
- Tingkat isu: `UNIQUE_VIOLATION` dan `AMBIGUOUS_AFTER_DISAMBIGUATION` = error (tidak menebak);
  `ADDRESS_DRIFT`, `EMPTY_VALUE` (kecuali allow_empty), `TYPE_MISMATCH`,
  `FORMULA_NOT_CALCULATED`, `EXCEL_ERROR_VALUE`, `MERGED_CELL` = warning;
  `MULTIPLE_FILES` = warning per sumber (`field: null` di audit).
- Perubahan kecil terhadap contoh JSON spesifikasi: tambah `meta.schema_version`,
  `value_meta.merged_range`, dan key audit keyword seragam (`disambiguation`/`reference`/`drift` ikut null bila tidak berlaku).
- Engine membuka tiap file dua kali (`data_only=True` + `False`) supaya `from_formula` dan
  `FORMULA_NOT_CALCULATED` bisa diandalkan.
- Folder sumber memindai hanya `.xlsx/.xlsm` (file `~$` diabaikan); `.xls` akan ditambahkan menyusul via `xlrd`.

## Verifikasi Fase 1
```
.venv/bin/python -m pytest -q     # 105 passed
.venv/bin/ruff check .            # All checks passed
.venv/bin/mypy core               # Success: no issues found in 11 source files
.venv/bin/python tools/generate_samples.py --out samples   # sampel demo
```

## Verifikasi Fase 2
```
.venv/bin/python -m pytest -q     # 112 passed (7 test asap UI, mode offscreen)
.venv/bin/ruff check .            # All checks passed
.venv/bin/mypy core               # Success: no issues found in 11 source files
python main.py                    # buka jendela (uji manual user)
python tools/_repro_add_field.py  # skrip sekali pakai: form data bisa dibuka + disimpan
.venv/bin/python /tmp/boot_check.py    # boot seperti main.py + keluar: exit 0
.venv/bin/python /tmp/verify_app.py    # buka form lewat kode aplikasi + GC di thread worker: exit 0
.venv/bin/python /tmp/verify_app.py --control   # kode pra-perbaikan: crash (exit 138)
```
Catatan uji UI: window harus dimatikan eksplisit (close + deleteLater) sebelum dibuang;
kalau tidak, penghapusan Qt dilakukan GC di sembarang waktu dan prosesnya crash (segfault).
Hal yang sama berlaku untuk dialog modal: setelah `exec()`, panggil `deleteLater()`.

## Verifikasi perbaikan kontras Pratinjau (Langkah 2)
```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q     # 122 passed
.venv/bin/ruff check .                                      # All checks passed
.venv/bin/mypy core                                         # Success: no issues found in 11 source files
.venv/bin/python /tmp/probe_contrast.py                     # kontras tiap sel bersorot di palet dark
unset QT_QPA_PLATFORM; .venv/bin/python /tmp/boot_check.py   # boot cocoa asli: exit 0
```
Pemeriksaan permanennya adalah `tests/test_ui_smoke.py::test_preview_text_stays_readable_on_its_light_fills`
(palet dark disimulasikan di dalam tes, jadi ikut jalan di CI/offscreen); `/tmp/probe_contrast.py`
hanya alat ukur sekali pakai yang mencetak angka kontrasnya.

## Verifikasi urutan sheet/data (drag and drop)
```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q     # 126 passed
.venv/bin/ruff check .                                      # All checks passed
.venv/bin/mypy core                                         # Success: no issues found in 11 source files
unset QT_QPA_PLATFORM; .venv/bin/python /tmp/reorder_gui.py  # gestur + koordinat asli di jendela cocoa
.venv/bin/python /tmp/reorder_columns.py                    # hasil mengikuti urutan baru
.venv/bin/python /tmp/boot_check.py                         # boot cocoa asli: exit 0
```
`/tmp/reorder_gui.py` dan `/tmp/reorder_columns.py` memakai profil di folder sementara, jadi profil asli
tidak tersentuh. Pemeriksaan permanennya adalah dua tes asap di `tests/test_ui_smoke.py` di atas.

## Perbaikan: semua sheet tertutup setiap ada perubahan
Dilaporkan user: "kenapa selalu collapse setiap sheet ada perubahan, sangat mengganggu". Akar masalahnya
`ui/step2_fields.py:refresh()`: ia membuang habis pohonnya lalu membangun ulang, dan hanya baris sub-folder
yang dibuka lagi — jadi setiap perubahan (tambah/ubah/duplikat/hapus/geser) menutup semua sheet dan
menghilangkan baris yang sedang tersorot. Perbaikan di satu tempat itu:
- Baris yang terbuka dan baris yang terpilih dibaca dulu (`_open_rows`, `_selection`) lalu dipasang kembali
  setelah pohon selesai dibangun (Qt mengabaikan `setExpanded` sebelum baris punya anak).
- Baris yang baru disentuh (`self._reveal`, di-set di tambah sheet/field, duplikat, dan ubah) menang atas
  sorotan lama dan otomatis dibuka, jadi hasil perubahan selalu terlihat tanpa klik tambahan.
- Dua tes di `tests/test_ui_smoke.py` memakainya: `test_a_change_keeps_rows_open_as_the_user_left_them`
  (diverifikasi "menggigit": mematikan pembacaan keadaan membuat tes ini gagal), dan tes urutan lama kini
  membersihkan seleksi dulu karena `QTreeWidgetItem.setSelected()` memang tidak mengganti baris terpilih
  sebelumnya (Qt single selection).

## Verifikasi perbaikan "sheet selalu tertutup"
```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q      # 127 passed
.venv/bin/ruff check .                                       # All checks passed
.venv/bin/mypy core                                          # Success: no issues found in 11 source files
unset QT_QPA_PLATFORM; .venv/bin/python /tmp/state_gui.py     # jendela cocoa: klik asli + perubahan → sheet tetap terbuka
unset QT_QPA_PLATFORM; .venv/bin/python /tmp/reorder_gui.py   # gestur geser asli tetap jalan (gui drop ok)
QT_QPA_PLATFORM=offscreen .venv/bin/python /tmp/boot_check.py  # boot profil: exit 0
```
`/tmp/state_gui.py` mencetak: sebelum perubahan `True False`, sesudah perubahan `True False`, baris tetap
tersorot, dan baris field pertama masih punya geometri nyata (benar-benar terlihat), bukan tersembunyi.

## Perbaikan: aplikasi mati mendadak (SIGABRT) saat form ditutup / app keluar
Dilaporkan user sebagai crash UI; 6 laporan crash macOS (`~/Library/Logs/DiagnosticReports/Python-2026-10-15-09*.ips`)
semuanya satu keluarga: `QThread: Destroyed while thread '' is still running` → `qFatal` → `abort`.
Akarnya ada di cara worker dijalankan (`ui/preview.py`, `ui/step3_run.py` memanggil `worker.start()` lalu
mengandalkan widget pemiliknya sebagai satu-satunya pemegang referensi):

- Tanda tangan laporan crash membuktikan thread yang mati adalah **worker itu sendiri**, bukan thread UI:
  `QThreadWrapper::run()` → `_Py_Dealloc` → `method_dealloc` → `subtype_dealloc` → `~QThread` → `qFatal`.
  Referensi terakhir ke worker adalah *bound method* `run()` milik thread itu (PySide melepasnya tepat setelah
  `run()` kembali). Jadi begitu UI (form/pane) melepas referensinya selagi worker masih membaca file,
  PySide menghancurkan QThread yang masih jalan → proses dibunuh. Muncul saat user membuka form lalu
  menutupnya sebelum pratinjau selesai membaca workbook besarnya, dan saat keluar aplikasi selagi job jalan.
- Perbaikan di satu tempat bersama, `ui/worker.py`: `start_worker(worker)` menyimpan worker di
  `_LIVE_WORKERS` dan baru melepasnya lewat `_release()` setelah `worker.wait()` (sinyal `finished` bisa
  datang sebelum `run()` benar-benar usai, jadi urutannya penting). Kedua pemanggil lama (`ui/preview.py`,
  `ui/step3_run.py`) memakai `start_worker()`; `deleteLater()` pada worker dihapus dari kedua slot karena
  penghancuran C++ saat thread masih hidup itu justru pemicunya.
- Jalur keluar: `wait_for_workers()` menunggu worker yang masih jalan, dan kalau tetap hidup
  `terminate()` + `wait()` — supaya Thread hidup tidak pernah dilepas. Dipasang di `ui/main.py`
  lewat `app.aboutToQuit` dan `atexit` (menutup juga jalur keluar yang tidak melewati `aboutToQuit`).
- Regresi dijaga `tests/test_ui_smoke.py::test_a_started_worker_outlives_the_widget_that_started_it`
  (menghapus referensi UI selagi thread di dalam `run()`). Regresi UI lain (form dibuka/ditutup, tombol
  Jalankan, hapus/jalan ganda) tetap hijau.

## Verifikasi perbaikan crash worker thread
```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q      # 128 passed
.venv/bin/ruff check .                                       # All checks passed
.venv/bin/mypy core                                          # Success: no issues found in 11 source files
unset QT_QPA_PLATFORM; .venv/bin/python /tmp/diag5.py --nofix # exit 134 (bug lama terulang)
unset QT_QPA_PLATFORM; .venv/bin/python /tmp/diag5.py         # exit 0 (perbaikan)
unset QT_QPA_PLATFORM; .venv/bin/python /tmp/diag6.py --nofix # exit 134 (keluar saat job jalan)
unset QT_QPA_PLATFORM; .venv/bin/python /tmp/diag6.py         # exit 0
unset QT_QPA_PLATFORM; .venv/bin/python /tmp/diag4.py         # form ditutup saat pratinjau baca: exit 0
QT_QPA_PLATFORM=offscreen .venv/bin/python /tmp/ui_walk.py    # alur UI penuh: exit 0
```
`/tmp/diag5.py` dan `/tmp/diag6.py` adalah alat A/B sekali pakai (`--nofix` meniru kode lama) yang mereproduksi
tanda tangan crash di atas; pemeriksaan permanennya adalah tes di `tests/test_ui_smoke.py`.

## Sheet yang belum ada bukan lagi "gagal" (laporan user, revisi v2 poin 2)
- Keluhan: daftar catatan penuh `Sheet '16' tidak ada di file. Sheet yang tersedia: 01..14` — satu baris
  merah per sheet yang belum ada, padahal laporan harian memang bertambah sheetnya dari hari ke hari.
- Akar masalah: `core/extractor.py:_run_source` hanya memakai `SHEET_ABSENT` (warning) untuk template
  `every_sheet`; profil yang memetakan nama sheet satu per satu (01..16) tetap jatuh ke
  `SHEET_NOT_FOUND` (error) lewat `_absorb_failure`, jadi tiap field di sheet itu dapat status "gagal"
  dan baris kosong di hasil.
- Perbaikan satu tempat: cabang "tidak ada sheet yang cocok" disatukan — selalu `SHEET_ABSENT`
  (warning, satu kali per template), **tanpa** item untuk field-nya, pesan tetap menyebut daftar sheet
  yang tersedia. `SHEET_NOT_FOUND` tidak lagi dipakai engine v2 (disimpan seperti `MERGED_CELL` agar
  berkas hasil v1 tetap terbaca); dicatat di `docs/SPEC.md`.
- Bukti (profil memetakan sheet 01-16, file hanya berisi 01-14):
  `SUMMARY {'sheets': 14, 'total_fields': 14, 'ok': 14, 'warning': 0, 'error': 0}` — 14 baris data,
  nol baris gagal, hanya 2 catatan `SHEET_ABSENT` (sheet 15 & 16).
- Tes: `test_missing_sheet_is_only_a_warning_without_a_row` (tanpa baris data, tanpa isu error) dan
  `test_missing_sheet_does_not_stop_the_other_sheets` (sheet lain tetap terbaca) menggantikan
  `test_sheet_not_found_lists_available_sheets`.
- Gerbang: `pytest` 153 passed, `ruff check .` bersih, `mypy core` bersih (14 berkas).

### Penanda merah di pohon Langkah 2 (permintaan lanjutan user)
- Pilihan user: baris sheet di pohon (folder > sheet > data) ditulis **merah** kalau sheet itu
  tidak ada di file contoh — "biar user tau datanya gak ada".
- Aturan warna memakai aturan mesin yang sama, bukan duplikat: `core/extractor._sheet_matches`
  dijadikan publik `sheet_matches` dan diimpor UI, jadi merah mengikuti mode pencocokan
  (termasuk pola/cocok sebagian) yang dipakai ekstraksi. Merah hanya muncul bila file contoh
  terbaca dan daftar sheet-nya tidak kosong; folder tanpa file contoh tidak diberi warna.
- Baris merah juga membawa tooltip penjelasan di kedua bahasa (`s2.sheet_missing`).
- `ui/sample_files.py:sheet_titles` kini di-cache per path + waktu ubah file: pohon meminta
  daftar sheet setiap kali dibangun ulang, dan membuka ulang workbook besar tiap kali bikin
  jendela terasa macet.
- Bukti (probe offscreen sekali pakai, lalu dihapus): file berisi sheet 01-14 → baris 01-14
  hitam, baris 15 & 16 `#c62828` + tooltip; setelah file diperbarui berisi 01-16 → `RED ROWS: []`
  (cache ikut batal karena waktu ubah berubah).
- Tes: `test_a_sheet_that_is_not_in_the_sample_file_is_shown_in_red` (baris hilang merah,
  sheet yang ada tetap normal).
- Gerbang akhir: `pytest` 154 passed, `ruff check .` bersih, `mypy core` bersih (14 berkas).
- Terbuka: warna merah hanya penanda, tidak menghalangi simpan (disengaja).

### Peringatan `SHEET_ABSENT` dibisukan di Langkah 3 (keputusan user)
- Pilihan user: cukup baris sheet merah di Langkah 2 — daftar catatan Langkah 3 tidak
  menampilkan peringatan sheet hilang sama sekali, tanpa baris hasil/N/A.
- Implementasi: `ui/step3_run.py:_fill` menyaring isu berkode `SHEET_ABSENT` saat
  merender daftar catatan. Engine tetap mencatatnya di `audit.issues`, jadi CLI
  (`cli.py cmd_run`) tetap mencetak `[CEK  ] (sumber): Sheet '…' tidak ada di …`
  dan file JSON hasil tidak berubah. Ringkasan Langkah 3 juga tidak terpengaruh
  (isu sumber tidak dihitung di `summary`).
- Tes: `test_missing_sheet_warning_stays_out_of_the_notes` (audit tetap punya
  `SHEET_ABSENT`, isu sheet hilang tidak muncul, isu lain tetap muncul) dan
  `test_run_prints_missing_sheet_notice` (CLI tetap memperingatkan).
- Gerbang: `pytest` 156 passed, `ruff check .` bersih, `mypy core` bersih (14 berkas).

## Struktur JSON per folder + nama data tanpa akhiran (keputusan user)
- Keluhan: `RestanTBS_HI_9` tidak perlu akhiran angka di belakangnya, `key` selalu `null`,
  dan JSON hanya dibedakan per sheet — penamaan datanya mau seperti nama folder.
- Keputusan user (3 klarifikasi): (1) aturan "nama hasil unik per profil" dihapus — cukup unik
  di dalam satu sheet, (2) `data` dikelompokkan per folder sumber lalu per sheet,
  (3) field `key` hilang dari JSON bila tidak ada identitas, bukan `null`.
- Akar masalah suffix: validasi `core/models.py` mewajibkan nama unik se-profil, jadi tombol
  Duplikat sheet selalu memberi akhiran `_2`, `_3`, … (`_free_output_name`). `key` null bukan
  bug: profil memang `"key": {"from": "none"}` dan UI belum punya pengatur identitas (SPEC poin
  "UI belum punya tombol … key").
- Implementasi:
  - `core/models.py`: `seen_outputs` dipindah ke dalam satu sheet; nama sama antar sheet sah.
  - `ui/step2_fields.py`: duplikat sheet menyalin nama apa adanya; `_free_output_name` dan
    `import re` dihapus (tidak punya pemakai lagi).
  - `core/output.py`: `build_document` mengelompokkan `{folder: {sheet: [entri, ...]}}`
    (berupa daftar karena mode `rows` bisa >1 entri per sheet); `item_to_dict` menghapus
    field `key` saat `item.key is None`.
  - `core/api.py`: `GET /reports` membentangkan data berkelompok menjadi daftar entri;
    filter `from`/`to` memakai `entry.get("key")`.
  - `ui/step3_run.py`: tabel Langkah 3 diisi dari `result.items` supaya nama hasil yang sama di
    sheet berbeda tetap tampil semua (peta datar `result.data` hanya menyimpan yang pertama dan
    kini hanya dipakai pratinjau).
  - `docs/SPEC.md` poin 1/2b/4 + `docs/schema/result-v2.json`: aturan baru, `data` object
    berjenjang, `key` tidak wajib.
- Profil lama dengan suffix tetap valid; user bisa menormalkan nama lewat form Ubah di UI
  (tidak ada alat khusus yang dibuat).
- Tes baru/ubah: `test_same_output_name_in_two_sheets_is_allowed`,
  `test_duplicate_output_name_rejected` (kini dalam satu sheet),
  `test_same_name_in_two_sheets_keeps_both_values`,
  `test_data_is_grouped_by_folder_then_sheet`, `test_key_is_omitted_when_the_item_has_none`,
  `test_date_filter_skips_entries_without_a_key`; duplikat sheet di UI kini tanpa suffix.
- Gerbang: `pytest` 160 passed, `ruff check .` bersih, `mypy core` bersih (14 berkas).

## Tabel Langkah 3 per folder + sheet tak terpakai tanpa warning (keputusan user)
- Keluhan: di tampilan hasil file tidak dibedakan sehingga membingungkan — harusnya sama
  seperti JSON: bedah per folder dulu, baru per sheet; dan sheet yang tidak dipakai profil
  jangan memunculkan warning/error.
- `ui/step3_run.py`: baris data kini diawali baris judul membentang (bold, abu) —
  `📁 Folder: … — File: …` lalu `📄 Sheet: …` — diambil dari `result.items` (satu judul per
  perubahan folder/sheet), persis urutan grup `{folder: {sheet: […]}}` di file JSON.
  Kunci i18n baru `s3.group_folder_file`, `s3.group_folder`, `s3.group_sheet` (id + en).
- `core/extractor.py`: sheet yang tidak diclaim template mana pun (mis. `Sheet1` sisa di
  file MPD) hanya dicatat diam-diam di `meta.unmatched_sheets` dan tidak lagi menghasilkan
  isu `SHEET_UNMATCHED` — biarkan tidak terpakai (keputusan user). Sheet yang sudah cocok
  template tetapi gagal pola identitas tetap warning lewat `_mark_unmatched` (parameter
  `key_cfg` kini wajib).
- `docs/SPEC.md`: dua kalimat `SHEET_UNMATCHED`/`unmatched_sheets` disesuaikan (kode tetap
  ada; pemakaiannya menyempit).
- Tes: `test_run_fills_the_result_table` kini memeriksa 3 baris folder + 3 baris sheet +
  15 baris data (bukan `rowCount == 15` lagi); baru
  `test_unclaimed_sheet_is_listed_without_a_warning` (sheet tanpa template → meta saja,
  `SHEET_UNMATCHED` tidak ada di audit).
- Gerbang: `pytest` 161 passed, `ruff check .` bersih, `mypy core` bersih (14 berkas).


