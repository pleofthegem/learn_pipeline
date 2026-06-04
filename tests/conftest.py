from pathlib import Path

import fitz
import pytest


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


@pytest.fixture
def email_before_adjacent_sentence_text() -> str:
    return "test@email.com.This was a test"


def write_sample_pdf(path: Path, paragraphs: list[str]) -> None:
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "\n".join(paragraphs), fontsize=12)
    pdf.save(path)
    pdf.close()


@pytest.fixture
def sample_pdf_path(tmp_path: Path, sample_paragraphs: list[str]) -> Path:
    path = tmp_path / "abstract_001.pdf"
    write_sample_pdf(path, sample_paragraphs)
    return path


@pytest.fixture
def sample_input_dir(tmp_path: Path, sample_paragraphs: list[str]) -> Path:
    input_dir = tmp_path / "abstracts_raw"
    input_dir.mkdir()

    write_sample_pdf(input_dir / "abstract_001.pdf", sample_paragraphs)
    write_sample_pdf(input_dir / "abstract_002.pdf", sample_paragraphs)
    (input_dir / "abstract_003.docx").write_text("Not a PDF", encoding="utf-8")
    (input_dir / "notes.csv").write_text("Unsupported input", encoding="utf-8")

    return input_dir
