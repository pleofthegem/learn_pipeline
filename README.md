# IWA Learn Pipeline

This repo processes IWA Learn abstract files into cleaned PDFs, extracted
metadata, and anonymised text exports.

## Requirements

- Python 3.10 or later
- LibreOffice, for converting `.doc`, `.docx`, `.ppt`, and `.pptx` files to PDF

On Debian or Ubuntu, install LibreOffice with:

```bash
sudo apt install libreoffice
```

## Setup

Activate your Python environment before running the pipeline commands.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The commands below assume your environment is active.

## Usage

### Full Pipeline: `main.py`

Runs conversion, combined-PDF splitting, metadata extraction, and anonymisation.

```bash
python main.py
```

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
- `combined_input/` for combined abstract e-books to split
- `abstracts_raw/` for atomic PDF abstracts

Main outputs:

- `abstracts_raw/`
- `abstract_csv/abstract_metadata.csv`
- `abstract_json/abstract_metadata.json`
- `abstracts_clean/`
- `abstract_csv/anonymised_abstracts.csv`
- `abstract_json/anonymised_abstracts.json`

### Convert Files to PDF: `convert_to_pdf.py`

Aggregates supported files from an input folder and converts or copies them into
`abstracts_raw/`.

```bash
python convert_to_pdf.py input
```

Supported input types:

- `.pdf`
- `.doc`
- `.docx`
- `.ppt`
- `.pptx`

Outputs:

- `abstracts_aggregated/` as a staging folder
- `abstracts_raw/` for generated or copied PDFs

### Split Combined PDFs: `split_pdf.py`

Splits combined abstract e-book PDFs into individual PDFs.

```bash
python split_pdf.py
```

To use a custom combined-PDF input folder:

```bash
python split_pdf.py custom_combined_input
```

Outputs:

- `abstracts_split/` as a staging folder
- `abstracts_split/split_abstracts.csv`
- `abstracts_split/split_abstracts.json`
- `abstracts_raw/` for the final split PDFs

### Extract Abstract Metadata: `extract_abstract_data.py`

Reads PDFs from `abstracts_raw/` and extracts title, authors, abstract text,
keywords, and optional conference metadata.

```bash
python extract_abstract_data.py
```

To read from a custom folder:

```bash
python extract_abstract_data.py abstracts_raw
```

Use optional defaults when conference metadata is known in advance:

```bash
python extract_abstract_data.py abstracts_raw \
  --conference-name "IWA Example Conference" \
  --conference-place "Example City, Example Country"
```

Outputs:

- `abstract_csv/abstract_metadata.csv`
- `abstract_json/abstract_metadata.json`

Each row includes `additional_info` with this shape:

```json
{"name": "", "place": ""}
```

The extractor tries to read the conference name and place from each PDF's own
header. If no conference metadata can be found and no defaults are supplied,
`additional_info` is written with empty strings for `name` and `place`.

### Anonymise Abstracts: `anonymise_abstracts.py`

Extracts text from PDFs and removes supported personal/contact identifiers.

Process every PDF in `abstracts_raw/`:

```bash
python anonymise_abstracts.py
```

Process a single file:

```bash
python anonymise_abstracts.py abstract_001.pdf
```

Outputs:

- `abstracts_clean/` for cleaned text files
- `abstract_csv/anonymised_abstracts.csv`
- `abstract_json/anonymised_abstracts.json`

## Pipeline Logic

The full pipeline:

1. Aggregates supported source files from `input/`.
2. Converts Office files to PDF and copies existing PDFs into `abstracts_raw/`.
3. Splits combined abstract e-books from `combined_input/`.
4. Extracts title, authors, description, keywords, and conference metadata.
5. Anonymises PDF text from `abstracts_raw/`.

## Repo Structure

Input folders:

- `input/`: raw source files for conversion. This is mainly for files supplied
  before PDF-only input is enforced.
- `combined_input/`: combined PDF e-books with a table of contents followed by
  multiple abstracts.
- `abstracts_raw/`: atomic PDF abstracts used by metadata extraction and
  anonymisation.

Output folders:

- `abstracts_aggregated/`: staging folder used by `convert_to_pdf.py`.
- `abstracts_split/`: staging folder and metadata output used by `split_pdf.py`.
- `abstract_csv/`: CSV exports from metadata extraction and anonymisation.
- `abstract_json/`: JSON exports from metadata extraction and anonymisation.
- `abstracts_clean/`: cleaned text files from anonymisation.

## Tests

```bash
pytest
```
