# Errors

Command failures and integration errors.

---

## 2026-04-15 - PowerShell here-string BOM affected inline Python

- Context: While validating `docs/ConflictNTL_event_collection_2026-02-27_2026-04-14.md`, an inline Python script piped from a PowerShell here-string failed before reading the target file.
- Symptom: Python reported `SyntaxError: invalid non-printable character U+FEFF` at line 1.
- Cause: The command input stream included a BOM; this was a command-construction issue, not evidence of markdown file corruption.
- Safer pattern: Use `python -c "..."` for small UTF-8 validation snippets on Windows PowerShell.

## 2026-04-15T19:39:01 - Excel rulebook write locked

- Command: conda run -n NTL-GPT-Stable python scripts/export_screening_rulebook.py
- Error: PermissionError writing docs/screening_rulebook/ConflictNTL_two_round_screening_rulebook.xlsx, likely because workbook was open in Excel.
- Resolution: write a versioned/fallback XLSX path instead of overwriting locked workbook.

## 2026-04-15T20:10:00 - Base Python missing openpyxl for rulebook export

- Command: python scripts/export_screening_rulebook.py
- Error: ModuleNotFoundError: No module named 'openpyxl'
- Context: Base Python had pandas but not openpyxl, so CSV writing succeeded and XLSX export failed.
- Resolution: run spreadsheet exports in the project conda environment, e.g. `conda run -n NTL-GPT-Stable python scripts/export_screening_rulebook.py`.

## 2026-04-15T20:35:00 - NTL-GPT-Stable missing pycountry

- Command: conda run -n NTL-GPT-Stable python -c "import geopandas, shapely, pycountry"
- Error: ModuleNotFoundError: No module named 'pycountry'
- Context: geoBoundaries helper can resolve country names through pycountry, but the conda environment does not include it.
- Resolution: for ConflictNTL batch admin AOI generation, pass explicit ISO3 codes from a small Middle East country map instead of relying on pycountry.

## 2026-04-15T20:42:00 - scripts entrypoint could not import tools package

- Command: conda run -n NTL-GPT-Stable python scripts/generate_isw_admin_area_aois.py
- Error: ModuleNotFoundError: No module named 'tools'
- Context: When Python executes a file under `scripts/`, `sys.path[0]` is the scripts directory, not necessarily the repository root.
- Resolution: add the repository root to `sys.path` before importing local packages.

## 2026-04-16T00:00:00 - PowerShell here-string added BOM to stdin Python

- Command: `@' ... '@ | python -`
- Error: `SyntaxError: invalid non-printable character U+FEFF`
- Context: The here-string passed to Python stdin included a leading BOM, so the validation script failed before checking the target files.
- Resolution: use `python -c "..."` for small UTF-8 validation snippets in PowerShell.

## 2026-04-16T00:00:00 - Candidate CSV has no candidate_id column

- Command: pandas preview of `docs/ISW_screened_events_2026-02-27_2026-04-07_top_candidates.csv`
- Error: `KeyError: "['candidate_id'] not in index"`
- Context: The top-candidates CSV stores `objectid`, `event_id`, and date fields but not a materialized `candidate_id`.
- Resolution: construct candidate IDs with `ISW_{YYYYMMDD}_{objectid}_{event_id}` when exporting candidate point GeoJSON.

## 2026-04-16T00:00:00 - PowerShell python -c newline escape parsed literally

- Command: `python -c "...;\nfor ..."`
- Error: `SyntaxError: unexpected character after line continuation character`
- Context: In PowerShell command strings, `\n` is not converted into a Python newline. Python receives a literal backslash followed by `n`.
- Resolution: use semicolon-only one-liners, list comprehensions, or a temporary script file for multi-line Python validation.

## 2026-04-16T00:00:00 - conda run can crash when relaying Chinese stdout under GBK console

- Command: `conda run -n NTL-GPT-Stable python -c "... print(docx paragraph text)"`
- Error: `UnicodeEncodeError: 'gbk' codec can't encode character ...` inside conda's stdout relay.
- Context: The child Python process completed enough to print DOCX content, but conda's wrapper failed while writing Unicode text to the PowerShell console.
- Resolution: avoid printing Chinese through `conda run`; use the environment Python executable directly or set UTF-8 output encoding.

## 2026-04-16T00:00:00 - DOCX overwrite failed when target is open

- Command: `python scripts/convert_markdown_to_docx.py ... ConflictNTL_Letter_Manuscript_Draft_CN.docx`
- Error: `PermissionError: [Errno 13] Permission denied`
- Context: The target DOCX was likely open in Word/WPS or otherwise locked by another process.
- Resolution: save to a new filename or ask the user to close the document before overwriting.

## 2026-04-16T00:00:00 - Local package import failed when running a script from scripts/

- Command: `python scripts/count_vnp46a1_country_granules.py`
- Error: `ModuleNotFoundError: No module named 'experiments'`
- Context: When executing a file under `scripts/`, Python sets `sys.path[0]` to the scripts directory, not the repository root.
- Resolution: insert the repository root into `sys.path` before importing local packages.

