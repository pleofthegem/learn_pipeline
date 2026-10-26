"""Shared PDF loading with a narrow fallback for empty ICC profiles.
Addresses the MuPDF error: format error: cmsOpenProfileFromMem failed error."""
import re
from pathlib import Path

import fitz

ICC_COLORSPACE_RE = re.compile(r"^\[\s*/ICCBased\s+(\d+)\s+\d+\s+R\s*\]$")
DEVICE_COLORSPACES = {"1": "/DeviceGray",
                      "3": "/DeviceRGB", "4": "/DeviceCMYK"}


def open_pdf(path: Path) -> fitz.Document:
    """Open a PDF and replace empty indirect ICC colour spaces in memory.

    A zero-byte profile cannot describe colours. Use its declared device
    alternate, or the device colour space matching its component count. Leave
    valid/nonempty profiles and unknown colour spaces alone. The source is
    never saved; split outputs inherit the repaired colour-space reference.
    """
    pdf = fitz.open(path)
    try:
        repaired = 0
        for xref in range(1, pdf.xref_length()):
            match = ICC_COLORSPACE_RE.fullmatch(pdf.xref_object(xref).strip())
            if not match:
                continue
            profile = int(match.group(1))
            if not pdf.xref_is_stream(profile) or pdf.xref_stream(profile) != b"":
                continue
            _, components = pdf.xref_get_key(profile, "N")
            device = DEVICE_COLORSPACES.get(components)
            alternate_type, alternate = pdf.xref_get_key(profile, "Alternate")
            if alternate_type != "null" and alternate != device:
                continue
            if device is None:
                continue
            pdf.update_object(xref, device)
            repaired += 1
        if repaired:
            print(
                f"{Path(path).name}: used device colours for {repaired} empty ICC profile(s). Source file unchanged.")
        return pdf
    except Exception:
        pdf.close()
        raise
