# Pipeline repo for IWA Learn

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
