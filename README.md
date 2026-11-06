# IWA Learn Pipeline

The default abstract workflow accepts PDF and Word files, converts Word files to
PDF when present, splits recognised combined PDFs (or isolates proposals sharing a page), and extracts metadata.
Its handoff bundle contains the individual source
PDFs and their metadata CSV. Webinar processing produces Excel reports.

## Desktop app

Install Python 3.10+ with Tkinter, then double-click **Start IWA Learn.bat** on
Windows or **Start IWA Learn.command** on macOS. On Linux, run the `.command`
launcher. Launchers locate the project automatically, so shortcuts can start
from another directory.

Both launchers run `git pull --ff-only` before starting the app.
Updating requires Git on PATH and a Git checkout with a configured
upstream branch. If Git is missing or updating fails, it displays a warning and
starts the installed version. Existing
checkouts need one manual `git pull` to receive this launcher change; subsequent
launches attempt to update automatically on Windows, macOS, and Linux.

The first launch creates `.venv` and installs missing dependencies from
`requirements.txt`, requiring internet access. Later launches reuse the environment;
both launchers attempt an online update but can start offline.
On Ubuntu/Debian, Tkinter is supplied by `python3-tk`; on Windows use Python with
Tcl/Tk support installed. This launcher requires Python; it is not a standalone
executable.

1. Choose **Abstracts** or **Webinar reports**.
2. Drop PDF or Word files (abstracts), CSV files (webinars), or a folder into the box.
   Clicking the box selects files; **Choose folder** includes supported files
   in subfolders. Imports copy files into `input/` or `webinar/input/` and leave
   originals untouched. Duplicate names receive a numbered suffix.
3. Check the input list and click **Run**. Existing inputs remain in the batch;
   use **Clear input** to empty the selected workflow's input folder before
   starting another batch. Original files outside that folder are preserved.
4. The output list shows the abstract bundle's PDFs and CSV, or all webinar
   Excel workbooks. **Open output folder** opens the bundle or webinar output
   folder in your system file manager.
5. **Clear output** empties the selected workflow's output folder. For abstracts,
   this includes the handoff bundle and intermediate outputs. Clearing input and
   output are separate actions; both buttons are disabled during processing.

The GUI automatically converts Word inputs before splitting and extraction.
Anonymised text exports are available through the optional full command below.
Each successful new run
replaces the previous generated outputs; keep any bundles you want to retain
outside the output folder. A failure during processing can leave partial results.

On Windows, selection dialogs and folder opening use the Windows desktop.
Running inside WSL uses Linux dialogs and its file manager; dragging files from
Windows Explorer into the WSL app is not supported. For Windows use, run the
`.bat` launcher with Windows Python.

## Finding your results

Click **Open output folder** after processing. For abstracts, share the whole
`output/handoff_bundle/` folder: it contains `abstract_metadata.csv` and the
corresponding PDFs in `pdfs/`. The CSV includes titles, authors, abstract text,
keywords, and conference information when available. Abstract descriptions are
extracted only from explicitly labelled abstract sections; unlabelled body text,
introductions and summaries leave that field blank. Recognised leading submission
IDs are removed from titles using `TITLE_ID_PREFIX_PATTERNS` in
`scripts/extraction_rules.py`; add a pattern there for a new ID format.

Webinar Excel reports are saved in `webinar/output/`.

## Command-line use

From the project folder, create and activate an environment and install dependencies:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# Windows Command Prompt: .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

Start the already configured GUI with `python -m gui`, or run the PDF pipeline:

```bash
python -m scripts.main
python -m scripts.main path/to/input --output-folder path/to/output
python -m scripts.main --conference-name "IWA Example Conference" --conference-place "London, UK"
```

Conference defaults only fill fields missing from a PDF. Default data locations
are anchored to the project folder. Custom input and output folders must be
separate, with neither containing the other.

Automatic conference metadata uses only text before the entire paper title.
Names require an explicit conference/event label or a recognisable event heading
with edition/year evidence. Places require an explicit `Venue:`, `Location:`,
`Place:`, or `Host city:` label; dates, capitalisation, city-like text and author
affiliations are insufficient. Conflicting labels leave the field blank unless
an explicit batch default was provided.

Word conversion is automatic; no extra flag is needed for `.doc` or `.docx` inputs.
If Word files are present, LibreOffice's `soffice` or `libreoffice` command must be
on PATH. PDF-only and webinar runs do not require LibreOffice.

To additionally produce anonymised text and its CSV/JSON reports, run:

```bash
python -m scripts.main --full
```

Presentation PDFs identified by `ppt`, `pptx`
or `presentation` in their paths and password-protected PDFs are skipped.

Individual steps are still available as modules:

```bash
python -m scripts.convert_to_pdf input
python -m scripts.split_pdf
python -m scripts.extract_abstract_data
python -m scripts.anonymise_abstracts
python -m scripts.anonymise_abstracts abstract_001.pdf
python -m scripts.clear_outputs
```

Conversion writes PDFs into the bundle and aggregated originals into intermediate
outputs. Splitting and extraction default to the bundle's `pdfs/` folder;
provide a positional folder to read a different source. Anonymisation writes
only intermediate outputs. `clear_outputs` empties the bundle and intermediate
outputs, leaving source inputs and webinar files untouched.

## Webinar reports

To process webinar reports from the command line:

```bash
python -m scripts.process_webinar_report
python -m scripts.process_webinar_report "path/to/attendee report.csv"
```

The default run processes every CSV directly inside `webinar/input/`, using
`webinar/Regions.csv`. Use `--regions` and `--output-folder` to override these
locations. Each run replaces existing `.xlsx` files in its output folder.

Each input produces a workbook with **Cleaned data** and **Summary** sheets.
The processor recognises the `Attendee Details` section or compact Zoom headers,
preserves source headings and order, fills registration data across repeat
connections, removes AI notetakers, and excludes `Other Attended` footer rows.
It accepts reordered/custom registration headings, identifies email from values
when needed, and leaves unavailable summary fields blank.

The master workbook, `master_webinar_summary.xlsx`, combines the per-report
summaries with one row per attendee per webinar. Its additional `Webinar` column
comes from the workbook filename before `Attendee report`, retaining leading
dates and removing trailing markers such as `(clean)`.

## Isolating proposals that share pages

The pipeline automatically isolates proposals when a standalone asterisk separator
has body content above it and a contents-listed title below it on the same page.
Other recognised combined books use ordinary page splitting. Both routes write
individual PDFs directly into `output/handoff_bundle/pdfs/`, then the existing
extractor creates `output/handoff_bundle/abstract_metadata.csv`. The GUI and
`python -m scripts.main` use this same workflow.

Isolation copies original PDF regions without rasterising or rebuilding text.
It validates the isolated count, titles, order, and starting pages against the
contents before writing PDFs. Isolation summaries and contents validation reports
are saved under `output/intermediate_outputs/abstracts_isolated/<book_name>/`.
Source inputs remain untouched; their collected combined copies are removed from
the handoff folder after individual PDFs and reports have been written.

To run isolation separately for the ICNSS book currently in `input/`:

```bash
python -m scripts.isolate_pdf "input/Abstract Book_Final ICNSS 2026.pdf" \
  --start-page 54 --end-page 337 --expected-count 156 \
  --output-folder output/handoff_bundle/pdfs \
  --metadata-folder output/intermediate_outputs/abstracts_isolated/ICNSS_manual
```

Page arguments are inclusive, 1-based PDF page numbers. Select the body range to
exclude front matter and back covers. `--expected-count` validates against the
expected count before writing files. Leading submission IDs are used for naming
only; boundaries still come from delimiters. Numeric IDs, IDs with a numeric
suffix, and `ICNSS#` IDs retain their printed values in metadata and filenames,
including the hashtag (for example, `ICNSS#02`). Other filename components replace
spaces and punctuation with underscores, preserving letters, numbers and hyphens.
The first listed author is read from the formatted heading, excluding affiliation
markers, and formatted as initials and surname (`Govind Agrawala` → `G.Agrawala`,
`K. S. Shameem` → `K.S.Shameem`). Full names remain in the summary. Author titles
are removed, surname particles are retained, and single names are preserved; missing authors use `Unknown_Author` and are reported as warnings. If an ID is absent,
`paper_NNN` is used as the ID and reported in the summary.
Duplicate IDs fail before any PDFs are written. Outputs are
`<combined_PDF_stem>_<submission_ID>_<first_author>.pdf` (for example,
`Abstract_Book_Final_ICNSS_2026_7147445_G.Agrawala.pdf`), plus `isolation_summary.json`
with counts, warnings, titles, first authors, original page ranges and clipping
coordinates. Existing filenames are never overwritten;
choose a fresh destination for another run. Source PDFs are preserved.

Repeated text near page edges is removed when identifiable; use `--keep-margins`
to retain it. Uppercase theme-only and oral/poster section divider pages, and blank pages,
are excluded. A caption-only fragment separated by an extra delimiter is attached
to its preceding proposal and reported in the summary.
A final proposal without a closing delimiter is retained with a warning. Count
mismatches and content crossing a clipping boundary raise errors. An extraction
failure is logged and can leave partial output. Missing delimiters cannot always
be detected without an expected count; inspect the summary and resulting PDFs.

The ICNSS book has 156 ID-bearing abstracts. Its contents includes a stray
numbered `75.` before an author line; the 157 delimiters also include an extra
separator before a dry-toilet figure. That figure is retained with abstract
`7149572`, rather than becoming a separate PDF.

After standalone isolation, run `python -m scripts.extract_abstract_data` to
regenerate metadata from the handoff PDFs. The normal pipeline runs extraction
automatically. Standalone isolation refuses existing filenames; the normal
pipeline clears previous generated outputs at the start of each run.
