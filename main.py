"""Run the full abstract processing pipeline."""

import argparse
from pathlib import Path

import anonymise_abstracts
import convert_to_pdf
import extract_abstract_data
import split_pdf

INPUT_FOLDER = "input"
COMBINED_INPUT_FOLDER = "combined_input"


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the full pipeline.

    Returns:
        argparse.Namespace: Parsed CLI arguments containing `input_folder` and
            `combined_input_folder`.
    """
    parser = argparse.ArgumentParser(
        description="Run conversion, splitting, metadata extraction, and anonymisation."
    )
    parser.add_argument(
        "input_folder",
        nargs="?",
        default=INPUT_FOLDER,
        help="Folder containing raw source files to aggregate and convert.",
        type=str,
    )
    parser.add_argument(
        "--combined-input-folder",
        default=COMBINED_INPUT_FOLDER,
        help="Folder containing combined PDF e-books to split.",
        type=str,
    )
    return parser.parse_args()


def run_pipeline(
    input_folder: Path = Path(INPUT_FOLDER),
    combined_input_folder: Path = Path(COMBINED_INPUT_FOLDER),
    aggregate_folder: Path = Path(convert_to_pdf.AGGREGATED_FOLDER),
    raw_folder: Path = Path(convert_to_pdf.PDF_OUTPUT_FOLDER),
    split_folder: Path = Path(split_pdf.SPLIT_FOLDER),
    clean_output_folder: Path = Path(anonymise_abstracts.OUTPUT_FOLDER),
    extract_csv_path: Path = (
        Path(extract_abstract_data.CSV_OUTPUT_FOLDER)
        / extract_abstract_data.OUTPUT_CSV
    ),
    extract_json_path: Path = (
        Path(extract_abstract_data.JSON_OUTPUT_FOLDER)
        / extract_abstract_data.OUTPUT_JSON
    ),
    anonymise_csv_path: Path = (
        Path(anonymise_abstracts.CSV_OUTPUT_FOLDER)
        / anonymise_abstracts.OUTPUT_CSV
    ),
    anonymise_json_path: Path = (
        Path(anonymise_abstracts.JSON_OUTPUT_FOLDER)
        / anonymise_abstracts.OUTPUT_JSON
    ),
) -> dict[str, int]:
    """Run each pipeline stage in order.

    Args:
        input_folder: Folder containing raw files to aggregate and convert.
        combined_input_folder: Folder containing combined PDFs to split.
        aggregate_folder: Intermediary folder for converted source files.
        raw_folder: Shared folder containing atomic PDF abstracts.
        split_folder: Intermediary folder for split combined PDFs.
        clean_output_folder: Folder where anonymised text files are written.
        extract_csv_path: Destination CSV path for extracted metadata.
        extract_json_path: Destination JSON path for extracted metadata.
        anonymise_csv_path: Destination CSV path for anonymised text output.
        anonymise_json_path: Destination JSON path for anonymised text output.

    Returns:
        dict[str, int]: Counts from each pipeline stage.
    """
    print('Collecting files to convert...')
    _, converted_pdfs = convert_to_pdf.convert_inputs_to_pdfs(
        input_folder=Path(input_folder),
        aggregate_dir=Path(aggregate_folder),
        output_dir=Path(raw_folder),
    )
    print('Splitting combined pdfs...')
    split_metadata = split_pdf.split_combined_pdfs(
        input_folder=Path(combined_input_folder),
        output_folder=Path(raw_folder),
        staging_folder=Path(split_folder),
    )
    print('Extracting data from abstracts...')
    metadata_rows = extract_abstract_data.extract_abstract_data(
        input_folder=Path(raw_folder),
        csv_path=Path(extract_csv_path),
        json_path=Path(extract_json_path),
    )
    print('Anonymising pdfs...')
    anonymised_rows = anonymise_abstracts.anonymise_pdf_abstracts(
        input_dir=Path(raw_folder),
        output_dir=Path(clean_output_folder),
        csv_path=Path(anonymise_csv_path),
        json_path=Path(anonymise_json_path),
    )

    return {
        "converted_pdfs": len(converted_pdfs),
        "split_abstracts": len(split_metadata),
        "metadata_rows": len(metadata_rows),
        "anonymised_pdfs": len(anonymised_rows),
    }


def main() -> None:
    """Run the full pipeline from the command line.

    Returns:
        None.
    """
    args = parse_args()
    counts = run_pipeline(
        input_folder=Path(args.input_folder),
        combined_input_folder=Path(args.combined_input_folder),
    )

    print(f"Converted {counts['converted_pdfs']} PDFs.")
    print(f"Split {counts['split_abstracts']} combined abstracts.")
    print(f"Extracted metadata for {counts['metadata_rows']} PDFs.")
    print(f"Anonymised {counts['anonymised_pdfs']} PDFs.")


if __name__ == "__main__":
    main()
