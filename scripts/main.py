"""Build a handoff bundle of individual PDFs and their abstract metadata."""
import argparse
from pathlib import Path

from . import anonymise_abstracts, clear_outputs, convert_to_pdf, extract_abstract_data, split_pdf
from .config import INPUT_FOLDER, OUTPUT_ROOT


def run_pipeline(
    input_folder: Path = INPUT_FOLDER,
    output_folder: Path = OUTPUT_ROOT,
    *,
    full: bool = False,
    default_additional_info: extract_abstract_data.AdditionalInfo | None = None,
) -> dict[str, int]:
    """Replace generated outputs, leaving source files untouched.

    By default only PDFs are collected, split and described. Full mode also
    accepts Word documents and exports anonymised text. Input and output trees
    must be separate so clearing outputs cannot remove or re-import sources.
    """
    source, output = Path(input_folder).resolve(), Path(output_folder).resolve()
    if source.is_relative_to(output) or output.is_relative_to(source):
        raise ValueError("Input and output folders must be separate, with neither inside the other.")
    if not source.is_dir():
        raise ValueError(f"Input folder does not exist: {source}")
    suffixes = convert_to_pdf.SUPPORTED_SUFFIXES if full else {".pdf"}
    files = [p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in suffixes]
    if not files:
        raise ValueError("No supported input files found. Use PDF files, or --full for Word documents.")
    if full and any(p.suffix.lower() in convert_to_pdf.OFFICE_SUFFIXES for p in files):
        convert_to_pdf.office_converter_command()

    bundle = output / "handoff_bundle"
    intermediate = output / "intermediate_outputs"
    pdfs = bundle / "pdfs"
    print("Clearing generated outputs...")
    clear_outputs.clear_folders([bundle, intermediate])
    print("Collecting input files...")
    if full:
        _, copied = convert_to_pdf.convert_inputs_to_pdfs(
            source, intermediate / "abstracts_aggregated", pdfs,
        )
    else:
        copied = convert_to_pdf.aggregate_files(source, pdfs, suffixes={".pdf"})
    print("Splitting combined PDFs...")
    splits = split_pdf.prepare_individual_pdfs(pdfs, pdfs, intermediate / "abstracts_split")
    print("Extracting data from abstracts...")
    metadata = extract_abstract_data.extract_abstract_data(
        pdfs, bundle / "abstract_metadata.csv",
        intermediate / "json/abstract_metadata.json", default_additional_info,
    )
    anonymised = []
    if full:
        print("Anonymising PDFs...")
        anonymised = anonymise_abstracts.anonymise_pdf_abstracts(
            input_dir=pdfs, output_dir=intermediate / "abstracts_clean",
            csv_path=intermediate / "csv/anonymised_abstracts.csv",
            json_path=intermediate / "json/anonymised_abstracts.json",
        )
    return {
        "converted_pdfs": len(copied),
        "split_abstracts": len(splits),
        "metadata_rows": len(metadata),
        "anonymised_pdfs": len(anonymised),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_folder", nargs="?", type=Path, default=INPUT_FOLDER)
    parser.add_argument("--output-folder", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--full", action="store_true", help="Also convert Word inputs and export anonymised text.")
    parser.add_argument("--conference-name")
    parser.add_argument("--conference-place")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    counts = run_pipeline(
        args.input_folder, args.output_folder, full=args.full,
        default_additional_info=extract_abstract_data.default_additional_info_from_values(
            args.conference_name, args.conference_place,
        ),
    )
    print(f"Done: {counts['metadata_rows']} abstracts in {args.output_folder / 'handoff_bundle'}")


if __name__ == "__main__":
    main()
