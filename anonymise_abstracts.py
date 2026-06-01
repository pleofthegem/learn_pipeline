import os

import re

import csv

from pathlib import Path


import fitz  # PyMuPDF

from docx import Document


INPUT_FOLDER = "abstracts_raw"

OUTPUT_FOLDER = "abstracts_clean"

OUTPUT_CSV = "anonymised_abstracts.csv"

# EMAIL_RE = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b' # Original
EMAIL_RE = r'(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.+-])'

ORCID_RE = r'\b(?:https?://orcid\.org/)?\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b'

PHONE_RE = r'(\+?\d[\d\s().-]{7,}\d)'


def extract_text_from_docx(path):
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def extract_text_from_pdf(path):
    text = []
    with fitz.open(path) as pdf:
        for page in pdf:
            text.append(page.get_text())
    return "\n".join(text)


def anonymise_text(text):

    text = re.sub(EMAIL_RE, "[EMAIL_REMOVED]", text)
    text = re.sub(ORCID_RE, "[ORCID_REMOVED]", text)
    text = re.sub(PHONE_RE, "[PHONE_REMOVED]", text)
    return text


def process_file(path):
    suffix = path.suffix.lower()
    if suffix == ".docx":
        raw_text = extract_text_from_docx(path)
    elif suffix == ".pdf":
        raw_text = extract_text_from_pdf(path)
    else:
        return None
    clean_text = anonymise_text(raw_text)
    return {
        "file_name": path.name,
        "file_type": suffix,
        "clean_text": clean_text
    }


def main():
    input_dir = Path(INPUT_FOLDER)
    output_dir = Path(OUTPUT_FOLDER)
    output_dir.mkdir(exist_ok=True)
    rows = []
    for path in input_dir.iterdir():
        if path.suffix.lower() not in [".pdf", ".docx"]:
            continue
        result = process_file(path)
        if result:
            clean_file = output_dir / f"{path.stem}_clean.txt"
            clean_file.write_text(result["clean_text"], encoding="utf-8")
            rows.append({
                "file_name": result["file_name"],
                "file_type": result["file_type"],
                "clean_text_file": str(clean_file),
                "clean_text": result["clean_text"]
            })
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["file_name", "file_type",
                        "clean_text_file", "clean_text"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Processed {len(rows)} files.")
    print(f"CSV created: {OUTPUT_CSV}")
    print(f"Clean text files saved in: {OUTPUT_FOLDER}")


if __name__ == "__main__":

    main()
