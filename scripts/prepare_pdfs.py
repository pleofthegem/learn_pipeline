"""Select isolation for shared-page proposals, retaining page splitting by default."""
from pathlib import Path

import fitz

from . import isolate_pdf, split_pdf


def needs_isolation(pdf: fitz.Document, contents: split_pdf.CombinedPdfContents) -> bool:
    """Require a delimiter separating body text and a listed title on one page."""
    titles_by_page = {}
    for entry in contents.entries:
        page = entry.printed_start_page + contents.page_offset
        titles_by_page.setdefault(page, []).append(entry.title)
    for number, titles in titles_by_page.items():
        page = pdf[number - 1]
        lines = isolate_pdf.read_lines(page)
        for separator in isolate_pdf.detect_delimiters(lines):
            # Edge text alone (e.g. a running header) is not another proposal.
            before = [line for line in lines if line.rect.y1 <= separator.y0
                      and not isolate_pdf.at_edge(line.rect, page.rect)]
            after = ' '.join(line.text for line in lines if line.rect.y0 >= separator.y1)
            if before and any(split_pdf.normalise_title_for_matching(title)
                              in split_pdf.normalise_title_for_matching(after) for title in titles):
                return True
    return False


def prepare_individual_pdfs(pdf_folder: Path, intermediate_folder: Path) -> tuple[list[dict], list[dict]]:
    """Write isolated PDFs beside split PDFs; retain originals in the input tree.

    Snapshot the collected inputs so newly isolated files are not isolated again.
    Remove each collected combined copy only after its PDFs and manifests succeed.
    The split batch then handles all remaining inputs using its existing rules.
    """
    isolated = []
    for source in sorted(path for path in Path(pdf_folder).iterdir()
                         if path.is_file() and path.suffix.lower() == '.pdf'):
        with fitz.open(source) as pdf:
            contents = split_pdf.read_combined_pdf_contents(pdf)
            isolate = contents is not None and needs_isolation(pdf, contents)
            end = (contents.content_end_page or len(pdf)) if contents else None
        if not isolate:
            continue
        entries = [{'title': entry.title, 'printed_start_page': entry.printed_start_page,
                    'pdf_start_page': entry.printed_start_page + contents.page_offset}
                   for entry in contents.entries]
        print(f'Isolating shared-page proposals: {source.name}', flush=True)
        summary = isolate_pdf.isolate_pdf(
            source, pdf_folder, start_page=entries[0]['pdf_start_page'], end_page=end,
            expected_count=len(entries), contents_entries=entries,
            metadata_folder=intermediate_folder / 'abstracts_isolated' / isolate_pdf.filename_component(source.stem))
        isolated.extend(summary['abstracts'])
        source.unlink()
    split = split_pdf.prepare_individual_pdfs(pdf_folder, pdf_folder, intermediate_folder / 'abstracts_split')
    return split, isolated
