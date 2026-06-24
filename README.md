# Pipeline repo for IWA Learn
## Extra requirements
 - libreoffice
On Unix-like system, intall via sudo apt install libreoffice
## Usage

### Run the full pipeline:

```bash
./.venv/bin/python main.py
```

If the conference name and place are known for a batch, pass them as optional
defaults. These values are only used when an individual PDF does not contain
conference metadata itself:

```bash
./.venv/bin/python main.py \
  --conference-name "IWA Example Conference" \
  --conference-place "Example City, Example Country"
```

### Extract abstract metadata:

```bash
./.venv/bin/python extract_abstract_data.py
```

This reads PDFs from `abstracts_raw` and writes:

- `abstract_csv/abstract_metadata.csv`
- `abstract_json/abstract_metadata.json`

Each row includes `additional_info` with this shape:

```json
{"name": "", "place": ""}
```

The extractor tries to read the conference name and place from each PDF's own
header. If the PDF does not contain conference metadata, `additional_info`
stays blank unless explicit defaults are supplied.

If the conference metadata is known in advance, optional defaults can fill
missing values:

```bash
./.venv/bin/python extract_abstract_data.py abstracts_raw \
  --conference-name "IWA Example Conference" \
  --conference-place "Example City, Example Country"
```

When no conference metadata can be found and no defaults are supplied,
`additional_info` is still written with empty strings for `name` and `place`.

Process every PDF file in `abstracts_raw`:

```bash
./.venv/bin/python anonymise_abstracts.py
```

### Anonymise a single file:

```bash
./.venv/bin/python anonymise_abstracts.py abstract_001.pdf
```

Outputs are written to:

- `abstracts_clean/` for cleaned text files
- `abstract_csv/anonymised_abstracts.csv` for CSV metadata and text
- `abstract_json/anonymised_abstracts.json` for JSON metadata and text

### Split pdfs:
```bash
./venv/bin/python split_pdf.py
```
Outputs are written to:

- `abstracts_split` as an intermediary output
- `abstracts_raw` as the final output

## Convert file types to PDF

To convert the assortment of files to pdf, run
```bash
./venv/bin/python convert_to_pdf.py
```
Currently, this converts files of type 
- doc
- docx
- pptx

Output is sent to `abstracts_raw`

## Logic
Firstly aggregates all files in the given folder.
Secondly checks if there are any non pdf files. 
 - If so, converts them to pdf via `convert_to_pdf.py`
 - Any workbooks or amalgamation of pdfs is handled separately via `split_pdf.py`
 - Extracts title, authors, description, keywords, and optional conference metadata via `extract_abstract_data.py`
 - Since all files are pdf now, proceed to anonymise with `anonymise_abstracts.py`
 Anonymise assumes all files are pdfs and are located in `abstracts_raw/`.

 ## Repo structure
 ### The inputs are as follows:
 - `input` : the input folder that the conversion script runs on. This is the true raw input. The files are supposed to be in pdf format, so this is purely for files given prior to the standard being enforced.
 - `combined_input`: the input folder for combined pdfs. Assumes the structure contains a table of contents (which has title, page and ID) and is followed by the lengthy combination of abstracts.
 - `abstract_raw` is the folder which assumes everything is an atomic pdf. This is the input folder for anonymise.

 ### The outputs are as follows:
 - `abstract_csv`, `abstract_json`, `abstracts_clean` are the outputs of the anonymise and metadata extraction scripts. 
 - `abstracts_aggregated` is the intermediary output of the conversion script. This pulls together all the files to be converted under one directory. Acts as a staging folder -> `abstract_raw`.
- `abstracts_split` is the intermediary output for the split pdf script. This also contains `split_abstracts.csv` and `split_abstracts.json` for some metadata about the split.
