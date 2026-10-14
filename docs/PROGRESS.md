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


