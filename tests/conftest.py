from pathlib import Path

import fitz
import pytest
from docx import Document


@pytest.fixture
def sample_paragraphs() -> list[str]:
    return [
        "Title: Sample abstract",
        "Email: author@example.com",
        "ORCID: https://orcid.org/0000-0002-1825-0097",
        "Phone: +44 20 7946 0958",
    ]


@pytest.fixture
def sample_text(sample_paragraphs: list[str]) -> str:
    return "\n".join(sample_paragraphs)


def write_sample_docx(path: Path, paragraphs: list[str]) -> None:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)


def write_sample_pdf(path: Path, paragraphs: list[str]) -> None:
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "\n".join(paragraphs), fontsize=12)
    pdf.save(path)
    pdf.close()


@pytest.fixture
def sample_docx_path(tmp_path: Path, sample_paragraphs: list[str]) -> Path:
    path = tmp_path / "abstract_001.docx"
    write_sample_docx(path, sample_paragraphs)
    return path


@pytest.fixture
def sample_pdf_path(tmp_path: Path, sample_paragraphs: list[str]) -> Path:
    path = tmp_path / "abstract_001.pdf"
    write_sample_pdf(path, sample_paragraphs)
    return path


@pytest.fixture
def sample_input_dir(tmp_path: Path, sample_paragraphs: list[str]) -> Path:
    input_dir = tmp_path / "abstracts_raw"
    input_dir.mkdir()

    write_sample_docx(input_dir / "abstract_001.docx", sample_paragraphs)
    write_sample_pdf(input_dir / "abstract_001.pdf", sample_paragraphs)
    write_sample_docx(input_dir / "abstract_002.docx", sample_paragraphs)
    (input_dir / "notes.txt").write_text("Unsupported input", encoding="utf-8")

    return input_dir
