# IWA Learn Pipeline

The default abstract workflow accepts PDF and Word files, converts Word files to
PDF when present, splits recognised combined PDFs, and extracts metadata.
Its handoff bundle contains the individual source
PDFs and their metadata CSV. Webinar processing produces Excel reports.

## Desktop app

Install Python 3.10+ with Tkinter, then double-click **Start IWA Learn.bat** on
Windows or **Start IWA Learn.command** on macOS. On Linux, run the `.command`
launcher. Launchers locate the project automatically, so shortcuts can start
from another directory.

The first launch creates `.venv` and installs missing dependencies from
`requirements.txt`, requiring internet access. Later launches work offline.
On Ubuntu/Debian, Tkinter is supplied by `python3-tk`; on Windows use Python with
Tcl/Tk support installed. This launcher requires Python; it is not a standalone
executable.

1. Choose **Abstracts** or **Webinar reports**.
2. Drop PDF or Word files (abstracts), CSV files (webinars), or a folder into the box.
   Clicking the box selects files; **Choose folder** includes supported files
   in subfolders. Imports copy files into `input/` or `webinar/input/` and leave
   originals untouched. Duplicate names receive a numbered suffix.
3. Check the input list and click **Run**. Existing inputs remain in the batch;
   remove unwanted inputs using your file manager before starting another batch.
4. The output list shows the abstract bundle's PDFs and CSV, or all webinar
   Excel workbooks. **Open output folder** opens the bundle or webinar output
   folder in your system file manager.

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
keywords, and conference information when available.

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
