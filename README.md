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
 - Any workbooks or amalgamation of pdfs is handled separately via `split_pdf.py`
 - Since all files are pdf now, proceed to anonymise with `anonymise_abstracts.py`
 Anonymise assumes all files are pdfs and are located in `abstracts_raw/`.

 ## Repo structure
 ### The inputs are as follows:
 - `input` : the input folder that the conversion script runs on. This is the true raw input. The files are supposed to be in pdf format, so this is purely for files given prior to the standard being enforced.
 - `combined_input`: the input folder for combined pdfs. Assumes the structure contains a table of contents (which has title, page and ID) and is followed by the lengthy combination of abstracts.
 - `abstract_raw` is the folder which assumes everything is an atomic pdf. This is the input folder for anonymise.

 ### The outputs are as follows:
 - `abstract_csv`, `abstract_json`, `abstract_clean` are the outputs of the anonymise script. 
 - `abstracts_aggregated` is the intermediary output of the conversion script. This pulls together all the files to be converted under one directory. Acts as a staging folder -> `abstract_raw`.
- `abstracts_split` is the intermediary output for the split pdf script. This also contains `split_abstracts.csv` and `split_abstracts.json` for some metadata about the split.