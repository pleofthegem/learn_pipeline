"""Normalise text when joining lines extracted from PDFs."""
import re
from collections.abc import Iterable


def join_pdf_lines(lines: Iterable[str]) -> str:
    """Join wrapped hyphenated words without adding a space after the hyphen.

    Preserve the hyphen and ordinary spaced dashes. Only remove the artificial
    line boundary when a letter-hyphen ending is followed by another letter.
    """
    text = '\n'.join(line.strip() for line in lines if line.strip())
    text = re.sub(r'(?<=[^\W\d_])([-‐‑])\n(?=[^\W\d_])', r'\1', text)
    return re.sub(r'\s+', ' ', text).strip()
