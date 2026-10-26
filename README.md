# IWA Learn Pipeline

This repo processes IWA Learn abstract files into cleaned PDFs, extracted
metadata, and anonymised text exports.

This assumes that you already have git to clone the repo, and python installed to run the program.

## Requirements

- Python 3.10 or later
- LibreOffice, for converting `.doc` and `.docx` files to PDF

On Unix like OS, install LibreOffice with:

```bash
sudo apt install libreoffice
```

## Setup

Activate your Python environment before running the pipeline commands.

Linux or macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Windows Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

The commands below assume your environment is active.

## Usage

### Desktop app (Abstracts and Webinar reports)

Open **Start IWA Learn.bat** on Windows or **Start IWA Learn.command** on
macOS. On Linux, run the `.command` launcher or configure your file manager to
run executable scripts. The launcher finds the project folder automatically.
Python 3.10+ with Tkinter must already be installed. On Ubuntu/Debian, Tkinter
is provided by `sudo apt install python3-tk`.

The first launch creates `.venv` if needed and installs missing Python
dependencies, which requires internet access. Subsequent launches work offline
once dependencies are installed. Word inputs also require LibreOffice's
`soffice` or `libreoffice` command on your PATH; PDF and webinar processing do
not. This is a source-based launcher, not a packaged standalone executable.

1. Choose **Abstracts** or **Webinar reports**.
2. Drop files or a folder into the box, click the box to add files, or use
   **Choose folder** to import supported files including subfolders. The input
   list shows the current batch. Files are copied
   into `input/` or `webinar/input/`. Existing inputs remain in the batch;
   duplicate names receive a numbered suffix rather than being overwritten.
3. Click **Run**. The loading bar and status show processing progress.
4. Outputs appear in the list: raw PDFs and abstract metadata CSV for abstracts,
   or all Excel workbooks for webinars. **Open output folder** opens the workflow's
   output directory in Windows File Explorer on Windows, Finder on
   macOS, or the default Linux file manager.

The GUI uses the same fixed output folders and replacement behaviour as the
terminal commands. Each run replaces generated outputs from the previous run.
Manage the input folder in your file manager when starting a different batch.
Drag-and-drop support uses `tkinterdnd2`, installed by the launcher. File and
folder selection use Tkinter's native system dialogs; on Windows these are
Windows dialogs. No PowerShell or C# helper is required. Run the app with Windows
Python for the Windows desktop experience. Running it inside WSL uses Linux
dialogs and the Linux file manager; Explorer-to-WSL drag-and-drop is not supported.

If your environment is already set up, start with `python gui.py`.

### Full Pipeline: `main.py`

Runs conversion, combined-PDF splitting, metadata extraction, and anonymisation.

```bash
python main.py
```

`main.py` clears generated output folders before each run so the new outputs
can be inspected without leftovers from the previous run.

Use optional defaults when the conference name and place are known for a batch.
These values are only used when an individual PDF does not contain conference
metadata itself.

```bash
python main.py \
  --conference-name "IWA Example Conference" \
  --conference-place "Example City, Example Country"
```

Default inputs:

- `input/` for source files to aggregate and convert
- `output/abstracts_raw/` for PDFs produced by conversion and checked for
  splitting

Main outputs:

- `output/abstracts_raw/`
- `output/abstract_csv/abstract_metadata.csv`
- `output/abstract_json/abstract_metadata.json`
- `output/abstracts_clean/`
- `output/abstract_csv/anonymised_abstracts.csv`
- `output/abstract_json/anonymised_abstracts.json`

### Convert Files to PDF: `convert_to_pdf.py`

Aggregates supported files from an input folder and converts or copies them into
`output/abstracts_raw/`.

```bash
python convert_to_pdf.py input
```

Supported input types:

- `.pdf`
- `.doc`
- `.docx`

Presentations are not part of the automated abstract pipeline. `.ppt` and
`.pptx` files are ignored, and PDFs with path or filename text such as `ppt`,
`pptx`, or `presentation` are skipped before they reach
`output/abstracts_raw/`.
Password-protected PDFs are also skipped.

Outputs:

- `output/abstracts_aggregated/` as a staging folder
- `output/abstracts_raw/` for generated or copied PDFs

### Split Combined PDFs: `split_pdf.py`

Checks PDFs in `output/abstracts_raw/` and splits only the ones that match the
expected combined abstract e-book format.

Supported structures include the original `CONTENT` / `T1_O1` TOC, the
`Presentation 01` TOC, and session-organised printed contents such as
`HIC2026_Abstracts.pdf`. The new matcher runs only when the existing matchers
do not recognise the document. It reads titles and printed page numbers from
the contents pages, distinguishes italic author lines from titles, and validates
the printed-to-PDF page offset against body titles. Each abstract ends before
the next listed abstract or session; the last ends at the final numbered page.
PDF bookmarks are not used. These outputs use IDs such as `S1_A001`.

PDF loading also handles empty embedded ICC colour profiles by using the
matching device colour space in memory. This avoids the
`cmsOpenProfileFromMem failed` error caused by the empty RGB profile in the
HIC book. Source files remain unchanged; split PDFs inherit the fallback.
Nonempty profiles and unrelated MuPDF diagnostics are left unchanged.

```bash
python split_pdf.py
```

To check a custom PDF folder:

```bash
python split_pdf.py custom_pdf_folder
```

Outputs:

- `output/abstracts_split/` as a staging folder
- `output/abstracts_split/split_abstracts.csv`
- `output/abstracts_split/split_abstracts.json`
- `output/abstracts_raw/` for the final split PDFs

### Extract Abstract Metadata: `extract_abstract_data.py`

Reads PDFs from `output/abstracts_raw/` and extracts title, authors, abstract
text, keywords, and optional conference metadata.

```bash
python extract_abstract_data.py
```

To read from a custom folder:

```bash
python extract_abstract_data.py output/abstracts_raw
```

Use optional defaults when conference metadata is known in advance:

```bash
python extract_abstract_data.py output/abstracts_raw \
  --conference-name "IWA Example Conference" \
  --conference-place "Example City, Example Country"
```

Outputs:

- `output/abstract_csv/abstract_metadata.csv`
- `output/abstract_json/abstract_metadata.json`

Each row includes `additional_info` with this shape:

```json
{"name": "", "place": ""}
```

The extractor tries to read the conference name and place from each PDF's own
header. If no conference metadata can be found and no defaults are supplied,
`additional_info` is written with empty strings for `name` and `place`.

### Anonymise Abstracts: `anonymise_abstracts.py`

Extracts text from PDFs and removes supported personal/contact identifiers.

Process every PDF in `output/abstracts_raw/`:

```bash
python anonymise_abstracts.py
```

Process a single file:

```bash
python anonymise_abstracts.py abstract_001.pdf
```

Outputs:

- `output/abstracts_clean/` for cleaned text files
- `output/abstract_csv/anonymised_abstracts.csv`
- `output/abstract_json/anonymised_abstracts.json`

## Pipeline Logic

The full pipeline:

1. Aggregates supported source files from `input/`.
2. Converts Office files to PDF and copies existing PDFs into
   `output/abstracts_raw/`.
3. Checks `output/abstracts_raw/` for combined abstract e-books and splits
   matches.
4. Extracts title, authors, description, keywords, and conference metadata.
5. Anonymises PDF text from `output/abstracts_raw/`.

## Repo Structure

Input folders:

- `input/`: raw source files for conversion. This is mainly for files supplied
  before PDF-only input is enforced.

Output folders:

- `output/`: master folder for generated pipeline outputs.
- `output/abstracts_raw/`: PDFs produced by conversion and split PDFs used by
  later stages. This can contain normal PDFs and combined e-book PDFs; the
  splitter ignores PDFs that do not match the expected combined format.
- `output/abstracts_aggregated/`: staging folder used by `convert_to_pdf.py`.
- `output/abstracts_split/`: staging folder and metadata output used by
  `split_pdf.py`.
- `output/abstract_csv/`: CSV exports from metadata extraction and
  anonymisation.
- `output/abstract_json/`: JSON exports from metadata extraction and
  anonymisation.
- `output/abstracts_clean/`: cleaned text files from anonymisation.

## Clear Generated Outputs

To start a fresh run with the same input files, clear generated outputs:

```bash
python clear_outputs.py
```

This empties `output/abstract_csv/`, `output/abstract_json/`,
`output/abstracts_aggregated/`, `output/abstracts_clean/`,
`output/abstracts_raw/`, and `output/abstracts_split/`. It leaves `input/`
untouched.

## Webinar Report Pipeline

`webinar/process_webinar_report.py` finds either the `Attendee Details` section
or a compact Zoom attendee header, removes the report preamble, fills
registration data across repeat connections, removes AI notetakers, and creates
cleaned and summary dataframes.

The attendee header row is read directly from each report, so its columns may
be reordered and custom registration question headings may vary. The cleaned
sheet preserves those source headings and their order. There is no fixed list
of required source columns: available fields are transformed, while unavailable
summary fields are left blank. Email can also be identified from its values
when its heading is unfamiliar.

If an `Other Attended` footer is present, that marker and every row beneath it
are excluded from processing.

Place raw Zoom attendee CSV files in `webinar/input/`, then run:

```bash
python webinar/process_webinar_report.py
```

Every CSV directly inside `webinar/input/` is processed. To process a specific
file or a different folder, provide its path:

```bash
python webinar/process_webinar_report.py "path/to/attendee report.csv"
```

The script uses `webinar/Regions.csv` and writes one Excel workbook per input to
`webinar/output/`. Each workbook contains:

- `Cleaned data`: the attendee dataframe after removing the Zoom report
  preamble, filling repeat-connection fields, removing AI notetakers, and
  reducing join and leave dates to times.
- `Summary`: one row per email address, with connection count, total session
  time, last leave time, attendance details, demographics, and region.

At the start of each run, the pipeline removes existing `.xlsx` files from
`webinar/output/`. After the fresh individual workbooks are written, it rebuilds
`webinar/output/master_webinar_summary.xlsx` from their `Summary` sheets. The
master workbook contains one row per attendee per webinar and otherwise matches
the normal `Summary` shape, with one additional `Webinar` column. This name
comes from the workbook filename after removing the `Attendee report` marker
and everything after it, including suffixes such as `(clean)`. Leading dates
and the rest of the filename are preserved.

Use `--regions path/to/Regions.csv` or `--output-folder path/to/output` to
override either default.

## Tests

```bash
pytest
```
