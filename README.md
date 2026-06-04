# Pipeline repo for IWA Learn
## Extra requirements
 - libreoffice
On Unix-like system, intall via sudo apt install libreoffice
## Usage

Process every PDF file in `abstracts_raw`:

```bash
./.venv/bin/python anonymise_abstracts.py
```

Process a single file:

```bash
./.venv/bin/python anonymise_abstracts.py abstract_001.pdf
```

Outputs are written to:

- `abstracts_clean/` for cleaned text files
- `abstract_csv/anonymised_abstracts.csv` for CSV metadata and text
- `abstract_json/anonymised_abstracts.json` for JSON metadata and text

## Logic
Firstly aggregates all files in the given folder.
Secondly checks if there are any non pdf files. 
 - If so, converts them to pdf via `convert_to_pdf.py`
 - Since all files are pdf now, proceed to anonymise with `anonymise_abstracts.py`
 Anonymise assumes all files are pdfs and are located in `abstracts_raw/`.