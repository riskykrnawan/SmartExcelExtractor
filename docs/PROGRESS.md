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

