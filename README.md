# SmartExcelExtractor

SmartExcelExtractor is an automation tool that extracts data from Excel files. It locates each
value by the text that labels its row and column instead of a fixed cell address, and it records
where every value came from.

## Purpose

SmartExcelExtractor automates a repetitive task: retrieving values from Excel files. Its main goal
is to reduce human error in that task.

### Background

Operational data changes often. Excel is widely used for it because it is flexible, so reports are
structured in many different ways. Their layouts are not always tabular, positions shift when rows
or columns are added, file names change every day, and files from different sources rarely share
the same format.

This flexibility makes it difficult to retrieve the data reliably. Copying values by hand is slow
and prone to mistakes. Referring to fixed cell addresses (for example `I45`) is faster, but it
fails without warning: when the layout shifts, the address points to a different cell, and the
wrong value may be used without anyone noticing. The more files there are, and the more their
layouts differ, the harder it becomes to verify that every value is correct.

### Goals

- **Automate repetitive work.** Extract the same values from many files in one run, including on a
  schedule.
- **Reduce human error.** Remove manual copying and the dependence on fixed cell addresses.
- **Handle changing layouts.** Locate data by the text that labels it, so a rule keeps working
  when the layout shifts.
- **Make problems visible.** Record the source and cell address of every value, report ambiguity
  and deviations instead of guessing, and keep a full audit trail.
- **Provide consistent output.** Write all results to structured JSON that other reports and
  systems can use directly.
- **Be usable by non-technical staff.** Rules are written in plain words, checked with a live
  preview, and require no code.

### Comparison with fixed cell addresses

| Situation | Fixed cell address | Label-based extraction (this application) |
| --- | --- | --- |
| Rows or columns are added or removed | The address points to the wrong cell, often without any warning. | The data is still found by its label. |
| Layouts differ between files | A separate address list must be maintained and verified for each layout. | The same rule can be reused and adjusted per profile. |
| A value turns out to be wrong | Hard to detect, because nothing records where the value came from. | The source and cell address are recorded, and shifts or ambiguity are flagged in the audit notes. |

## Ways to use it

The application can be used in two modes, both running on the same extraction engine:

- **Application window**: for configuring settings and reviewing results.
- **Headless mode (CLI)**: for automatic execution through the Windows task scheduler.

## Table of contents

1. [How it works](#1-how-it-works)
2. [Requirements and installation](#2-requirements-and-installation)
3. [Try it with sample data](#3-try-it-with-sample-data)
4. [Using the application window](#4-using-the-application-window)
5. [Running without the window (for scheduling)](#5-running-without-the-window-for-scheduling)
6. [Where files are stored](#6-where-files-are-stored)
7. [Reading the JSON result](#7-reading-the-json-result)
8. [Troubleshooting](#8-troubleshooting)
9. [For developers](#9-for-developers)
10. [Planned features](#10-planned-features)

---

## 1. How it works

Suppose a sheet named "Production" contains the following table:

```
                       Total     Average
Daily Production       1523.5      63.5
Night Production        980.0      40.8
```

Define a rule: the **row** is labeled `Daily Production` and the **column** is labeled `Total`.
The application finds both labels, reads the value at their intersection (1523.5), and records
the cell address. If the table shifts by a few rows next month, the same rule still works.

### Terms used

| Term | Meaning |
| --- | --- |
| **Profile** | A set of settings for one group of reports, for example "Report A". |
| **Source** | One sub-folder containing report files, for example `daily_production`. |
| **Sheet** | The worksheet inside an Excel file to be read. |
| **Data item** | One number or text value to extract, with a result name chosen by the user (for example `daily_prod`). |

### Matching options

Each text (for rows, columns, and sheet names) has a matching option. Examples for the text
`Daily Production`:

| Option | Meaning | Matches | Does not match |
| --- | --- | --- | --- |
| **Exact match** (default) | The cell content must be identical. Letter case and extra spaces are ignored. | `Daily Production`, `daily  production` | `Daily Production Total` |
| **Contains** | The cell contains the text anywhere. | `Daily Production Total` | `Daily` |
| **Starts with** | The cell begins with the text. | `Daily Production Total` | `Total Daily Production` |
| **Ends with** | The cell ends with the text. | `Total Daily Production` | `Daily Production Total` |

### Text that appears more than once

If the text appears only once in the sheet, tick the checkbox *"This text appears only once in the
sheet"*. If it turns out to appear more than once, the application does **not guess**: the data
item is marked **Failed** and all candidates are recorded.

If the text legitimately appears several times (for example "Daily Production" appears in both a
production section and a summary section), leave the checkbox unticked and choose how to select
the correct occurrence (see Step 2 in section 4).

### Status meanings

| Status | Meaning |
| --- | --- |
| 🟢 **OK** | The data was found and nothing unusual was detected. |
| 🟡 **Needs review** | The data was extracted, but something should be checked (for example the data has shifted, the cell is merged, or the value is not a number). |
| 🔴 **Failed** | The data could not be extracted. The audit notes give the reason. |

A single failed data item does not stop the others.

---

## 2. Requirements and installation

### Requirements

- Python 3.11 or later ([python.org](https://www.python.org/downloads/)). On Windows, tick
  **"Add python.exe to PATH"** during installation.
- A folder of reports containing one sub-folder per source (for example `input\daily_report`,
  `input\daily_production`).
- Microsoft Excel is **not** required.

### Installation (one time)

Command Prompt is recommended (instead of PowerShell). Go to the application folder, then run:

```
cd "C:\Documents\Work\SmartExcelExtractor"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On macOS / Linux:

```
cd "/path/to/SmartExcelExtractor"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

After activation succeeds, `(.venv)` appears at the start of the prompt. All commands below are
run in a window where the environment is active. If the window is closed, activate it again with
the activation command above (reinstallation is not needed).

> To skip activation, call Python directly, for example `.venv\Scripts\python.exe main.py`
> (Windows) or `./.venv/bin/python main.py` (macOS / Linux).

---

## 3. Try it with sample data

Before using real data, generate sample Excel files that are intentionally messy (text that
appears twice, merged cells, formulas not yet calculated by Excel, hidden rows, shifted data, and
temporary `~$` files). This does not touch any real data.

```
python tools/generate_samples.py --out samples
```

The output is `samples\input_a`, `samples\input_b`, and `samples\input_c`, each containing
`daily_report`, `daily_production`, and `daily_sales` (with sheets such as `Production` and
`Report 01-10`).

Then run `python main.py` and follow the steps in section 4, using the `samples\input_a` folder.

---

## 4. Using the application window

```
python main.py
```

A **profile** is stored as a file in the `profiles\` folder. Buttons at the top:
**New**, **Copy**, **Rename**, **Delete**, **Import**, and **Export**. The Copy button is useful
because report groups are often similar but not identical. Every change is saved immediately
(there is no Save button).

### Step 1 - Data source

1. Click **"Select Folder..."** and choose the **parent folder** (the folder that contains the
   source sub-folders). The last folder is remembered for next time.
2. The application lists the sub-folders it finds. **Tick** the ones to extract data from.

Folder rules:

- Each sub-folder is expected to contain one Excel file (`.xlsx` or `.xlsm`). The file name may
  change every day.
- If there is more than one file, the application uses the **most recently modified** one and adds
  a "Needs review" note.
- Temporary Excel files (`~$...`) are ignored.
- If a folder is empty or a file cannot be opened, that source is recorded as failed and the other
  sources are still processed.

### Step 2 - Data to extract

1. Click **"+ Add Sheet"**, choose a sheet name from the sample file found by the application (or
   type one), then choose how the sheet name is matched (see the table in section 1). Sheet names
   sometimes change, for example "Production 01-10", so *Contains* or *Starts with* is often
   useful.
2. Select the sheet, then click **"+ Add Data"** to create one data item. Fill in the form:
   - *"Name for this result"*: a name of your choice (letters, digits, and underscores, for
     example `daily_prod`). It must be unique within the profile.
   - *"Find the row labeled..."* and *"Find the column labeled..."*, each with a matching option.
   - Tick *"This text appears only once in the sheet"* if that is the case.
3. If the text appears more than once, choose how to select the correct occurrence: **the closest
   one** to another text, **by reference cell address** that you provide, or **choose manually**
   from the list of candidates. If the data has shifted from the reference address, it is still
   extracted but marked "Needs review", so that you know the report format has changed.
4. The **Preview** at the bottom of the form immediately shows the value found, its cell address,
   the number of times the text occurs, and a small excerpt of the sheet around the result (the
   row, column, and value are highlighted in color). This allows checking against Excel without
   opening Excel.
5. Other buttons in the data tree: **Edit**, **Duplicate**, and **Delete**. Delete always asks for
   confirmation.

### Step 3 - Run and review

1. Click **"Run Extraction"**. The application stays responsive (processing runs in the
   background).
2. Review the summary: the number of data items, how many are **OK**, how many **need review**, and
   how many **failed**. The result table shows the value, color-coded status, file, sheet, and
   cell address. The **"Audit Notes"** list explains each issue in plain sentences, ordered from
   most to least important.
3. The JSON file is saved automatically to the `output\` folder. The **"Save JSON Copy..."** button
   copies the result to a location of your choice (for example to send to a colleague).

Wizard buttons: **Back**, **Next**, **Finish**, and **Close** to exit.

---

## 5. Running without the window (for scheduling)

This mode uses profiles already created in the application window. Make sure the virtual
environment is active (section 2).

```
python cli.py list-profiles                     # list available profiles
python cli.py validate --profile "Report A"     # check the profile, without extracting data
python cli.py run --profile "Report A"          # extract data, write JSON to output\
```

Useful options:

- `--input "D:\Reports\input"` overrides the parent folder (if the report folder has moved or been
  renamed).
- `--output "D:\Results"` saves the JSON to a different folder.
- `--profile` accepts a **profile name** (for example `"Report A"`) or the **full path of a profile
  file** (for example `"D:\Settings\Report A.json"`).

Example output (run against the sample data from section 3):

```
Profile : Sample Report A
Time    : 2026-10-14T13:11:45+08:00
Result  : 15 items - 9 OK, 5 need review, 1 failed
  [REVIEW] prod_formula: The formula in J45 has not been calculated by Excel; the value is empty.
  [REVIEW] prod_util: The value in L57 comes from merged cells K57:L57.
  ... (more notes follow, ordered from most to least important)
  [FAILED] prod_unique: The text 'Daily Production' is set to appear only once, but was found 2 times: I45, I94.
File    : D:\...\output\Sample Report A_20261014_131145.json
```

### Exit codes

Used by the scheduler to determine the outcome.

| Code | Meaning |
| --- | --- |
| `0` | Success. Data that only "needs review" is still considered successful. |
| `1` | One or more data items failed to extract, or processing stopped because of a major problem. |
| `2` | The profile or its settings are not valid (profile not found, parent folder empty, or no sub-folder ticked). |

### Scheduling with Task Scheduler (Windows)

1. Create Task → Triggers → New (for example daily at 07:00).
2. Actions → New:
   - Program/script: `C:\Documents\Work\SmartExcelExtractor\.venv\Scripts\python.exe`
   - Add arguments: `cli.py run --profile "Report A"`
   - Start in: `C:\Documents\Work\SmartExcelExtractor`
3. Each run produces a new file in the `output\` folder. Older files are never overwritten; file
   names include the date and time.

Tips to prevent scheduled runs from failing unnoticed:

- The **Last Run Result** column in Task Scheduler shows the exit code (`0x0` = success, `0x1` = at
  least one failure, `0x2` = invalid settings).
- If the reports are on a network drive, use the full network path (`\\server\reports\input`)
  instead of a drive letter such as `Z:\`. Background tasks often have no access to mapped drive
  letters.
- The Windows account that runs the task must have access to the report folder and to the
  `output\` folder.
- Schedule the task for a time when the report files are complete and not open by anyone.

---

## 6. Where files are stored

| Content | Location |
| --- | --- |
| Profiles (settings) | `profiles\` next to the application, one `.json` file per profile |
| Extraction results | `output\`, named `Profile Name_DATE_TIME.json` |
| Technical notes and error messages | `logs\app.log` (trimmed automatically when it grows large) |
| Application memory (last profile and folder) | `settings.json` next to the application |

For backup, copy the `profiles\` folder (or use the **Export** button in the application window).
The `output\` folder keeps growing because old files are never deleted; clean it up periodically.

---

## 7. Reading the JSON result

Each run produces one JSON file with three sections:

- `meta`: the profile, the run time, and a summary of OK / needs review / failed counts.
- `data`: every extracted data item, with its value, status, and origin.
- `audit`: a list of all audit notes, including the candidates that were found.

Abbreviated example:

```json
{
  "meta": {
    "profile": "Report A",
    "run_at": "2026-10-14T08:30:00+07:00",
    "summary": { "total_fields": 24, "ok": 21, "warning": 2, "error": 1 }
  },
  "data": {
    "daily_prod": {
      "value": 1523.5,
      "status": "ok",
      "source": { "folder": "daily_production", "file": "Prod_14Oct2026.xlsx", "sheet": "Production" },
      "location": { "value_address": "L45", "row_keyword_address": "I45", "col_keyword_address": "L12" }
    }
  },
  "audit": {
    "issues": [
      { "field": "prod_util", "level": "warning", "code": "ADDRESS_DRIFT", "message": "..." }
    ]
  }
}
```

For a quick check, look at `meta.summary` first. If anything is not OK, look in `audit.issues`.
Compare `value_address` with the address you expect; a sudden change in address is an early sign
that the report format has changed.

---

## 8. Troubleshooting

All problems are written in the **"Audit Notes"** list (Step 3) in plain sentences, and in full
detail in `logs\app.log`.

### Installation problems

| What you see | Action |
| --- | --- |
| `'python' is not recognized` | Python is not installed or not in PATH. Reinstall and tick **"Add python.exe to PATH"**, or try `py` instead of `python`. |
| `running scripts is disabled on this system` (PowerShell) | Use **Command Prompt** for the activation command, or call Python directly: `.venv\Scripts\python.exe main.py`. |

### Extraction problems

| What you see | Meaning and action |
| --- | --- |
| Status **Failed**: "The text '...' appears more than once" | The text is set to appear only once, but several occurrences exist. Open the data item (**Edit**), then choose how to select: closest / reference cell address / choose manually. The candidates are shown in the preview. |
| Status **Failed**: "The text '...' was not found" | The text in the profile is not in that file (possibly different letter case, spacing, or a different month). Correct the text or change the matching option. |
| Status **Failed**: "The sheet '...' does not exist in the file" | The sheet name changed or differs between files. Adjust the sheet matching option in Step 2. |
| Needs review: data shifted from the reference address | The text was found, but not at the reference address (for example reference I45, found at I48). The value is still extracted. Check whether the report format has actually changed. |
| Needs review: more than one file in the sub-folder | The application uses the most recently modified file. Make sure it is the correct file, and remove old files from the sub-folder. |
| Needs review: "The formula in ... has not been calculated by Excel" | The file was saved by another program, so formula results were not stored. Open the file in Excel, save it once, then run again. |
| Needs review: "The cell ... contains the Excel error #REF!" | The formula in the Excel file is broken. Fix it in the original file. |
| Needs review: "The value in ... comes from merged cells" | Warning only; the value is still extracted. |
| Needs review: "The value in ... is not a number" | The content is text, not a number (for example "not available"). The original value is still stored. |
| Needs review: "There is no value in ..." | The intersection is correct, but the cell is empty. |
| "The file cannot be read" / a file is skipped | The file is open in Excel by someone else, or it is corrupted. Close the file in Excel and run again. |
| "Profile '...' was not found" (exit code 2) | The profile name is wrong, or the profile has never been created in the application window. Check with `python cli.py list-profiles`. |
| "No source (folder) has been ticked" (exit code 2) | Open Step 1 and tick the sub-folders to use. |

Note: folder and file names may contain spaces, but in Command Prompt always use quotation
marks, for example `--input "D:\Daily Reports\input"`.

---

## 9. For developers

Folder layout:

| Folder / file | Purpose |
| --- | --- |
| `core/` | Extraction engine (no UI, can run headless) |
| `ui/` | PySide6 application window |
| `cli.py` | Headless mode |
| `main.py` | Entry point for the application window |
| `tests/` | pytest tests |
| `tools/generate_samples.py` | Sample Excel file generator |
| `docs/SPEC.md` | Source of truth for the specification |
| `docs/PROGRESS.md` | Progress notes per phase |

Development commands:

```
pip install -r requirements-dev.txt
pytest -q
ruff check .
mypy core
python tools/generate_samples.py --out samples
```

Rules followed by the engine:

- The result must be identical for identical input (deterministic).
- A failing data item, sheet, or file must not stop the others.
- When there are several candidates, the engine does not guess; all of them are recorded in the
  audit.
- Every value stores its cell address and origin (file, sheet).
- A new issue code must be added to `docs/SPEC.md` first.

---

## 10. Planned features

- [ ] **"Save Audit Report"** button (CSV/HTML containing all notes, ordered from most to least
  severe). For now, use **"Save JSON Copy..."**.
- [ ] **Comparison between runs**: automatic warning when a value changes beyond a set threshold.
- [ ] **`.exe` package** with PyInstaller, so the application can run without installing Python.
- [ ] **Legacy `.xls` files** (Excel 97-2003). Currently only `.xlsx` and `.xlsm` are supported.