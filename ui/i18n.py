"""Localization: one place for every user-facing string (Indonesian + English).

The engine (``core/``) never imports this; only ``ui/`` does. English is the
default (Indonesian is a full translation of the same keys). Switch the language
with :func:`set_language` (persisted in settings.json by the main window) and read
a string with :func:`t`.

Keys and comments are English; ``{placeholders}`` are filled by ``t(**kwargs)``.
"""
from __future__ import annotations

#: The default language; also the fallback when a key is missing a translation.
DEFAULT_LANGUAGE = "en"

#: (code, name shown in the picker, in its own language).
LANGUAGES: tuple[tuple[str, str], ...] = (
    ("id", "Bahasa Indonesia"),
    ("en", "English"),
)

_current: str = DEFAULT_LANGUAGE


def set_language(code: str) -> None:
    """Select the active language; unknown codes keep the current one."""
    global _current
    if code in {lang for lang, _name in LANGUAGES}:
        _current = code


def current_language() -> str:
    """The active language code."""
    return _current


def t(key: str, **kwargs: object) -> str:
    """Translate ``key`` into the active language, filling any ``{placeholders}``.

    An unknown key returns the key itself so a missing translation is loud.
    """
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_current) or entry[DEFAULT_LANGUAGE]
    return text.format(**kwargs) if kwargs else text


#: key -> {language code -> text}. Keep both languages in sync; a missing
#: language falls back to DEFAULT_LANGUAGE inside :func:`t`.
_STRINGS: dict[str, dict[str, str]] = {
    # ---- main window: profile bar, buttons, wizard nav ----
    "main.label_profile": {"id": "Profil:", "en": "Profile:"},
    "main.btn_new": {"id": "Baru", "en": "New"},
    "main.btn_copy": {"id": "Salin", "en": "Duplicate"},
    "main.btn_rename": {"id": "Ubah Nama", "en": "Rename"},
    "main.btn_delete": {"id": "Hapus", "en": "Delete"},
    "main.btn_import": {"id": "Impor", "en": "Import"},
    "main.btn_export": {"id": "Ekspor", "en": "Export"},
    "main.label_language": {"id": "Bahasa:", "en": "Language:"},
    "wizard.btn_back": {"id": "Kembali", "en": "Back"},
    "wizard.btn_next": {"id": "Lanjut", "en": "Next"},
    "wizard.btn_finish": {"id": "Selesai", "en": "Finish"},
    "wizard.btn_close": {"id": "Tutup", "en": "Close"},
    "main.err_no_profile": {"id": "Tidak ada profil yang terbuka.", "en": "No profile is open."},
    "main.new_profile_title": {"id": "Profil baru", "en": "New profile"},
    "main.new_profile_prompt": {"id": "Nama profil:", "en": "Profile name:"},
    "main.dup_title": {"id": "Salin profil", "en": "Copy profile"},
    "main.dup_prompt": {"id": "Nama profil baru:", "en": "New profile name:"},
    "main.dup_default": {"id": "{name} (salinan)", "en": "{name} (copy)"},
    "main.rename_title": {"id": "Ubah nama profil", "en": "Rename profile"},
    "main.rename_prompt": {"id": "Nama baru:", "en": "New name:"},
    "main.delete_title": {"id": "Hapus profil", "en": "Delete profile"},
    "main.delete_question": {"id": "Hapus profil '{name}'?", "en": "Delete profile '{name}'?"},
    "main.import_title": {"id": "Impor profil", "en": "Import profile"},
    "main.export_title": {"id": "Ekspor profil", "en": "Export profile"},
    "main.file_filter_json": {"id": "File profil (*.json)", "en": "Profile file (*.json)"},
    "main.export_done": {"id": "Profil diekspor ke {path}", "en": "Profile exported to {path}"},
    "main.err_create": {"id": "Tidak bisa membuat profil", "en": "Could not create profile"},
    "main.err_create_new": {
        "id": "Tidak bisa membuat profil baru",
        "en": "Could not create the new profile",
    },
    "main.err_copy": {"id": "Tidak bisa menyalin profil", "en": "Could not copy profile"},
    "main.err_rename": {"id": "Tidak bisa mengubah nama profil", "en": "Could not rename profile"},
    "main.err_delete": {"id": "Tidak bisa menghapus profil", "en": "Could not delete profile"},
    "main.err_import": {"id": "Tidak bisa mengimpor profil", "en": "Could not import profile"},
    "main.err_export": {"id": "Tidak bisa mengekspor profil", "en": "Could not export profile"},
    "main.err_open": {"id": "Profil tidak bisa dibuka", "en": "The profile could not be opened"},
    "status.auto_saved": {
        "id": "Perubahan tersimpan otomatis.",
        "en": "Changes saved automatically.",
    },
    "status.auto_save_failed": {
        "id": "Perubahan belum tersimpan: {error}",
        "en": "Changes not saved: {error}",
    },
    "status.language_applied": {
        "id": "Bahasa diganti ke {name}.",
        "en": "Language switched to {name}.",
    },
    # ---- step 1: sources ----
    "s1.title": {"id": "Langkah 1 - Sumber data", "en": "Step 1 - Data sources"},
    "s1.subtitle": {
        "id": "Pilih folder induk lalu centang sub-folder yang berisi laporan.",
        "en": "Pick the parent folder, then check the sub-folders that hold reports.",
    },
    "s1.label_parent": {"id": "Folder induk:", "en": "Parent folder:"},
    "s1.btn_pick": {"id": "Pilih Folder...", "en": "Choose Folder..."},
    "s1.label_subfolders": {
        "id": "Sub-folder yang ditemukan (centang yang dipakai):",
        "en": "Sub-folders found (check the ones to use):",
    },
    "s1.not_selected": {"id": "(belum dipilih)", "en": "(not chosen yet)"},
    "s1.hint_start": {"id": "Tekan 'Pilih Folder...' untuk mulai.", "en": "Press 'Choose Folder...' to start."},
    "s1.hint_missing": {
        "id": "Folder induk tidak ditemukan. Pilih folder yang lain.",
        "en": "Parent folder not found. Choose a different folder.",
    },
    "s1.hint_info": {
        "id": (
            "Tiap sub-folder dianggap berisi satu file Excel. "
            "Kalau ada lebih dari satu, file yang paling baru dipakai."
        ),
        "en": (
            "Each sub-folder is assumed to hold one Excel file. "
            "If there is more than one, the newest file is used."
        ),
    },
    "s1.dialog_title": {"id": "Pilih folder induk laporan", "en": "Choose the report parent folder"},
    # ---- step 2: sheets and fields ----
    "s2.title": {"id": "Langkah 2 - Data yang diambil", "en": "Step 2 - Data to extract"},
    "s2.subtitle": {
        "id": (
            "Susun data per folder: sheet lalu data yang mau diambil. "
            "Geser barisnya untuk mengubah urutan."
        ),
        "en": (
            "Arrange the data per folder: sheet, then the data to extract. "
            "Drag a row to change the order."
        ),
    },
    "s2.tree_header": {"id": "Struktur data", "en": "Data structure"},
    "s2.btn_add_sheet": {"id": "+ Tambah Sheet", "en": "+ Add Sheet"},
    "s2.btn_add_field": {"id": "+ Tambah Data", "en": "+ Add Data"},
    "s2.btn_edit": {"id": "Ubah", "en": "Edit"},
    "s2.btn_duplicate": {"id": "Duplikat", "en": "Duplicate"},
    "s2.btn_delete": {"id": "Hapus", "en": "Delete"},
    "s2.sheet_prefix": {"id": "Sheet: {name}", "en": "Sheet: {name}"},
    "s2.field_row": {"id": "{name}  -  cari baris: '{text}'", "en": "{name}  -  find row: '{text}'"},
    "sd.title": {"id": "Tambah sheet", "en": "Add sheet"},
    "sd.label_name": {"id": "Nama sheet:", "en": "Sheet name:"},
    "sd.hint": {
        "id": (
            "Pilih dari daftar atau ketik nama. Kalau nama sheet sering berubah "
            "(mis. 'Produksi 01-10'), pilih 'Mengandung'."
        ),
        "en": (
            "Pick from the list or type a name. If the sheet name changes often "
            "(e.g. 'Produksi 01-10'), choose 'Contains'."
        ),
    },
    "sd.label_match": {"id": "Cara mencocokkan nama:", "en": "How to match the name:"},
    "sd.btn_add": {"id": "Tambah", "en": "Add"},
    "sd.btn_cancel": {"id": "Batal", "en": "Cancel"},
    "s2.info_add_sheet_title": {"id": "Tambah sheet", "en": "Add sheet"},
    "s2.info_pick_folder": {"id": "Pilih dulu satu folder di daftar atas.", "en": "First pick one folder in the list above."},
    "s2.delete_sheet_title": {"id": "Hapus sheet", "en": "Delete sheet"},
    "s2.delete_sheet_question": {
        "id": "Hapus sheet '{name}' beserta {count} data di dalamnya?",
        "en": "Delete sheet '{name}' and the {count} data inside it?",
    },
    "s2.delete_field_title": {"id": "Hapus data", "en": "Delete data"},
    "s2.delete_field_question": {"id": "Hapus data '{name}'?", "en": "Delete data '{name}'?"},
    "s2.dup_title": {"id": "Duplikat data", "en": "Duplicate data"},
    "s2.dup_prompt": {"id": "Nama untuk hasil baru:", "en": "Name for the new result:"},
    "s2.dup_default": {"id": "{name}_salinan", "en": "{name}_copy"},
    "s2.err_save": {"id": "Belum bisa disimpan", "en": "Cannot save yet"},
    # ---- step 3: run and review ----
    "s3.title": {"id": "Langkah 3 - Jalankan dan periksa", "en": "Step 3 - Run and review"},
    "s3.subtitle": {
        "id": "Tekan 'Jalankan Ekstraksi', lalu periksa hasil tiap data.",
        "en": "Press 'Run Extraction', then review each result.",
    },
    "s3.btn_run": {"id": "Jalankan Ekstraksi", "en": "Run Extraction"},
    "s3.btn_save": {"id": "Simpan Salinan JSON...", "en": "Save JSON Copy..."},
    "s3.summary_empty": {
        "id": "Belum ada hasil. Tekan 'Jalankan Ekstraksi' untuk mulai.",
        "en": "No results yet. Press 'Run Extraction' to start.",
    },
    "s3.label_issues": {"id": "Catatan pemeriksaan:", "en": "Review notes:"},
    "s3.col_name": {"id": "Nama data", "en": "Data name"},
    "s3.col_value": {"id": "Nilai", "en": "Value"},
    "s3.col_status": {"id": "Status", "en": "Status"},
    "s3.col_file": {"id": "File", "en": "File"},
    "s3.col_sheet": {"id": "Sheet", "en": "Sheet"},
    "s3.col_address": {"id": "Alamat nilai", "en": "Value address"},
    "s3.status_ok": {"id": "Berhasil", "en": "OK"},
    "s3.status_warning": {"id": "Perlu dicek", "en": "Needs review"},
    "s3.status_error": {"id": "Gagal", "en": "Failed"},
    "s3.status_unknown": {"id": "Tidak diketahui", "en": "Unknown"},
    "s3.err_no_root_title": {"id": "Belum bisa dijalankan", "en": "Cannot run yet"},
    "s3.err_no_root": {"id": "Folder induk belum diatur (Langkah 1).", "en": "The parent folder is not set (Step 1)."},
    "s3.err_no_sources": {"id": "Belum ada sub-folder yang dicentang (Langkah 1).", "en": "No sub-folder is checked (Step 1)."},
    "s3.err_no_fields": {"id": "Belum ada data yang diatur (Langkah 2).", "en": "No data is configured (Step 2)."},
    "s3.reading": {
        "id": "Sedang membaca {fields} data dari {folders} folder...",
        "en": "Reading {fields} data from {folders} folder(s)...",
    },
    "s3.saved_path": {"id": "Hasil tersimpan: {path}", "en": "Result saved: {path}"},
    "s3.failed_summary": {
        "id": "Ekstraksi gagal. Coba jalankan lagi, atau lihat file log.",
        "en": "Extraction failed. Try again, or check the log file.",
    },
    "s3.failed_title": {"id": "Ekstraksi gagal", "en": "Extraction failed"},
    "s3.summary_result": {
        "id": "{total} data: {ok} berhasil, {warning} perlu dicek, {error} gagal.",
        "en": "{total} data: {ok} OK, {warning} need review, {error} failed.",
    },
    "s3.value_empty": {"id": "(kosong)", "en": "(empty)"},
    "s3.source_none": {"id": "(tidak ada)", "en": "(none)"},
    "s3.level_error": {"id": "GAGAL", "en": "ERROR"},
    "s3.level_warning": {"id": "PERINGATAN", "en": "WARNING"},
    "s3.issue_general": {"id": "(umum)", "en": "(general)"},
    "s3.no_issues": {"id": "Tidak ada catatan. Semua data terbaca.", "en": "No notes. All data was read."},
    "s3.save_title": {"id": "Simpan salinan hasil", "en": "Save result copy"},
    "s3.json_filter": {"id": "File JSON (*.json)", "en": "JSON file (*.json)"},
    "s3.save_failed_title": {"id": "Gagal menyimpan", "en": "Could not save"},
    "s3.save_failed": {"id": "Salinan tidak bisa disimpan: {error}", "en": "The copy could not be saved: {error}"},
    "s3.copy_saved": {"id": "Salinan disimpan: {path}", "en": "Copy saved: {path}"},
    # ---- field form: labels, buttons ----
    "ff.title_new": {"id": "Data baru", "en": "New data"},
    "ff.title_edit": {"id": "Ubah data '{name}'", "en": "Edit data '{name}'"},
    "ff.label_name": {"id": "<b>Nama untuk hasil ini</b>", "en": "<b>Name for this result</b>"},
    "ff.name_placeholder": {"id": "Contoh: prod_hi", "en": "Example: prod_hi"},
    "ff.prompt_row": {"id": "Cari baris yang bertuliskan...", "en": "Find the row that says..."},
    "ff.prompt_col": {
        "id": "Cari kolom yang bertuliskan (boleh dikosongkan)...",
        "en": "Find the column that says (can be left empty)...",
    },
    "ff.offset_group": {"id": "Kalau kolom kosong, ambil nilai yang...", "en": "If the column is empty, take the value that..."},
    "ff.offset_from": {"id": "dari tulisan baris, geser", "en": "from the row text, shift"},
    "ff.offset_cells": {"id": "sel", "en": "cell(s)"},
    "ff.label_type": {"id": "<b>Tipe data yang diharapkan</b>", "en": "<b>Expected data type</b>"},
    "ff.type_note": {
        "id": "Kalau nilainya tidak sesuai, muncul peringatan; nilai asli tetap disimpan.",
        "en": "If the value does not match, a warning appears; the original value is kept.",
    },
    "ff.allow_empty": {"id": "Nilai kosong tidak dianggap masalah", "en": "An empty value is not a problem"},
    "ff.allow_empty_note": {
        "id": "Kalau tidak dicentang, nilai kosong ditandai 'perlu dicek'.",
        "en": "If unchecked, an empty value is marked 'needs review'.",
    },
    "ff.btn_save": {"id": "Simpan", "en": "Save"},
    "ff.btn_cancel": {"id": "Batal", "en": "Cancel"},
    "ff.err_save": {"id": "Data belum bisa disimpan", "en": "The data cannot be saved yet"},
    "ke.placeholder": {"id": "Tulis kata kunci...", "en": "Type a keyword..."},
    "ke.label_match": {"id": "Cara mencocokkan:", "en": "How to match:"},
    "ke.case": {"id": "Bedakan huruf besar/kecil", "en": "Match upper/lower case"},
    "ke.unique": {"id": "Tulisan ini hanya muncul satu kali di sheet", "en": "This text appears only once in the sheet"},
    "ke.extra_group": {"id": "Kalau muncul lebih dari sekali...", "en": "If it appears more than once..."},
    "ke.label_choose": {"id": "Cara memilih yang dipakai:", "en": "How to choose which one to use:"},
    "ke.address_label": {"id": "Alamat sel acuan (contoh: I45):", "en": "Reference cell address (example: I45):"},
    "ke.address_placeholder": {"id": "Contoh: I45", "en": "Example: I45"},
    "ke.ref_label": {
        "id": "Tulisan pembanding (contoh: SECTION PRODUKSI):",
        "en": "Comparison text (example: SECTION PRODUKSI):",
    },
    "ke.ref_match": {"id": "Cara mencocokkan pembanding:", "en": "How to match the comparison:"},
    "ke.ref_address": {
        "id": "...atau alamat sel (kosongkan bila memakai tulisan):",
        "en": "...or a cell address (leave empty if using text):",
    },
    "ke.radius_label": {"id": "Jarak 'dekat' (jumlah sel):", "en": "'Near' distance (number of cells):"},
    "ke.radius_note": {
        "id": "Kemunculan dalam jarak ini dianggap dekat dan dibuang.",
        "en": "Occurrences within this distance count as near and are discarded.",
    },
    # ---- combo box label lists (built per call so they follow the language) ----
    "mode.exact": {"id": "Sama persis", "en": "Exact"},
    "mode.contains": {"id": "Mengandung", "en": "Contains"},
    "mode.starts": {"id": "Diawali dengan", "en": "Starts with"},
    "mode.ends": {"id": "Diakhiri dengan", "en": "Ends with"},
    "mode.regex": {"id": "Lanjutan", "en": "Advanced"},
    "dis.by_address": {"id": "Paling dekat ke alamat sel yang saya tentukan", "en": "Closest to the cell address I set"},
    "dis.near": {"id": "Paling dekat ke tulisan pembanding", "en": "Closest to the comparison text"},
    "dis.not_near": {"id": "Tidak dekat dengan tulisan pembanding", "en": "Not near the comparison text"},
    "type.any": {"id": "Apa saja", "en": "Anything"},
    "type.number": {"id": "Angka", "en": "Number"},
    "type.text": {"id": "Teks", "en": "Text"},
    "type.date": {"id": "Tanggal", "en": "Date"},
    "dir.right": {"id": "di sebelah kanan", "en": "to the right"},
    "dir.left": {"id": "di sebelah kiri", "en": "to the left"},
    "dir.down": {"id": "di bawah", "en": "below"},
    "dir.up": {"id": "di atas", "en": "above"},
    # ---- field-form tips and live match help ----
    "tip.name": {
        "id": "Huruf, angka, dan garis bawah saja. Contoh: prod_hi. Nama harus berbeda dari data lain di profil ini.",
        "en": "Letters, numbers, and underscores only. Example: prod_hi. The name must differ from other data in this profile.",
    },
    "tip.row": {
        "id": "Tulis tulisan yang ada di baris, misalnya: Produksi Harian. Spasi berlebih dan huruf besar/kecil mengikuti pilihan di bawah.",
        "en": "Type the text found in the row, for example: Produksi Harian. Extra spaces and upper/lower case follow the choice below.",
    },
    "tip.col": {
        "id": "Tulis tulisan di kolom yang nilainya diambil, misalnya: Total. Kalau datanya berbentuk 'label: nilai', kosongkan saja isian ini.",
        "en": "Type the text in the column whose value is taken, for example: Total. If the data looks like 'label: value', just leave this empty.",
    },
    "help.exact": {
        "id": "Akan cocok dengan: {matches} - Tidak cocok dengan: '{sample} Total'",
        "en": "Will match: {matches} - Will not match: '{sample} Total'",
    },
    "help.contains": {
        "id": "Akan cocok dengan: 'Rekap {sample}' - Tidak cocok dengan: '{short}'",
        "en": "Will match: 'Rekap {sample}' - Will not match: '{short}'",
    },
    "help.starts": {
        "id": "Akan cocok dengan: '{sample} 01' - Tidak cocok dengan: 'Rekap {sample}'",
        "en": "Will match: '{sample} 01' - Will not match: 'Rekap {sample}'",
    },
    "help.ends": {
        "id": "Akan cocok dengan: 'Rekap {sample}' - Tidak cocok dengan: '{sample} 01'",
        "en": "Will match: 'Rekap {sample}' - Will not match: '{sample} 01'",
    },
    "help.regex": {
        "id": "Mode Lanjutan: pola tulisan khusus, untuk pengguna terlatih saja.",
        "en": "Advanced mode: a special text pattern, for trained users only.",
    },
    # ---- live preview pane ----
    "pv.title": {"id": "<b>Pratinjau hasil</b>", "en": "<b>Result preview</b>"},
    "pv.label_sample": {"id": "File sampel:", "en": "Sample file:"},
    "pv.label_notes": {"id": "Kemunculan dan catatan:", "en": "Occurrences and notes:"},
    "pv.label_grid": {"id": "Cuplikan sheet (sekitar 5 sel):", "en": "Sheet snippet (around 5 cells):"},
    "pv.legend_row": {"id": "tulisan baris", "en": "row text"},
    "pv.legend_col": {"id": "tulisan kolom", "en": "column text"},
    "pv.legend_value": {"id": "nilai", "en": "value"},
    "pv.placeholder_default": {"id": "Pratinjau akan tampil di sini.", "en": "The preview will appear here."},
    "pv.no_sample": {"id": "Belum ada file sampel. Lengkapi Langkah 1 dulu.", "en": "No sample file yet. Complete Step 1 first."},
    "pv.incomplete": {"id": "Lengkapi dulu bagian form yang masih kosong.", "en": "Fill in the parts of the form that are still empty first."},
    "pv.no_result": {"id": "Hasil pratinjau tidak tersedia.", "en": "The preview result is not available."},
    "pv.loading": {"id": "Membaca file sampel...", "en": "Reading the sample file..."},
    "pv.status_ok": {"id": "🟢 OK", "en": "🟢 OK"},
    "pv.status_warning": {"id": "🟡 Perlu dicek", "en": "🟡 Needs review"},
    "pv.status_error": {"id": "🔴 Gagal", "en": "🔴 Failed"},
    "pv.value_empty": {"id": "(kosong)", "en": "(empty)"},
    "pv.detail_value": {"id": "Nilai di sel {address}", "en": "Value in cell {address}"},
    "pv.detail_row": {"id": "tulisan baris di {address}", "en": "row text at {address}"},
    "pv.detail_col": {"id": "tulisan kolom di {address}", "en": "column text at {address}"},
    "pv.no_match": {"id": "Tidak ada titik temu.", "en": "No match point found."},
    "pv.occ_row": {"id": "baris", "en": "row"},
    "pv.occ_col": {"id": "kolom", "en": "column"},
    "pv.occ_count": {"id": "{count} kemunculan", "en": "{count} occurrence(s)"},
    "pv.occ_prefix": {"id": "Tulisan ", "en": "Text "},
    "pv.cand_row": {"id": "Tulisan baris", "en": "Row text"},
    "pv.cand_col": {"id": "Tulisan kolom", "en": "Column text"},
    "pv.cand_used": {"id": " (dipakai)", "en": " (used)"},
    "pv.cand_reason": {"id": "alasan: ", "en": "reason: "},
    "pv.dis_unique": {"id": "karena tulisan ini hanya muncul sekali", "en": "because this text appears only once"},
    "pv.dis_by_address": {"id": "karena paling dekat ke alamat acuan", "en": "because it is closest to the reference address"},
    "pv.dis_near": {"id": "karena paling dekat ke tulisan pembanding", "en": "because it is closest to the comparison text"},
    "pv.dis_not_near": {"id": "karena tidak dekat dengan tulisan pembanding", "en": "because it is not near the comparison text"},
    # ---- background worker failure messages (shown in a dialog) ----
    "wk.run_failed": {"id": "Ekstraksi gagal total. Detail lengkap ada di file log.", "en": "The extraction failed completely. Full details are in the log file."},
    "wk.preview_failed": {"id": "Pratinjau gagal dijalankan. Detail lengkap ada di file log.", "en": "The preview could not run. Full details are in the log file."},
}
