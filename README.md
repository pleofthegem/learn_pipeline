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

## Tests

```bash
pytest
```
