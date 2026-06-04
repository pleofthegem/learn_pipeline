"""Aggregate source files and convert supported inputs to PDF."""

import argparse
import shutil
import subprocess
from pathlib import Path

AGGREGATED_FOLDER: str = "abstracts_aggregated"
PDF_OUTPUT_FOLDER: str = "abstracts_raw"
PDF_SUFFIX: str = ".pdf"
OFFICE_SUFFIXES: set[str] = {".doc", ".docx", ".ppt", ".pptx"}


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the conversion script.

    Returns:
        argparse.Namespace: Parsed CLI arguments containing `input_folder`, the
            source directory to scan for files.
    """
    parser = argparse.ArgumentParser(
        description="Aggregate files and convert supported inputs to PDF."
    )
    parser.add_argument(
        "input_folder",
        help="Folder to scan for source files.",
        type=str,
    )
    return parser.parse_args()


def aggregate_files(
    input_folder: Path,
    aggregate_dir: Path = Path(AGGREGATED_FOLDER),
) -> list[Path]:
    """Copy every file under an input folder into one aggregate folder.

    Args:
        input_folder: Root folder to scan for files, including nested files.
        aggregate_dir: Destination folder that receives copied files.

    Returns:
        list[Path]: Paths to copied files in the aggregate folder.
    """
    input_folder = Path(input_folder)
    aggregate_dir = Path(aggregate_dir)
    aggregate_dir.mkdir(parents=True, exist_ok=True)
    aggregate_dir_resolved = aggregate_dir.resolve()

    copied: list[Path] = []
    for path in sorted(input_folder.rglob("*")):
        if not path.is_file():
            continue
        if path.resolve().is_relative_to(aggregate_dir_resolved):
            continue

        relative_path = path.relative_to(input_folder)
        destination = aggregate_destination(aggregate_dir, relative_path)
        shutil.copy2(path, destination)
        copied.append(destination)

    return copied


def aggregate_destination(aggregate_dir: Path, relative_path: Path) -> Path:
    """Build a flattened aggregate destination path.

    Args:
        aggregate_dir: Folder that receives aggregated files.
        relative_path: Source path relative to the original input root.

    Returns:
        Path: Destination path using `__` to preserve parent-folder context in a
            flat aggregate directory.
    """
    return aggregate_dir / "__".join(relative_path.parts)


def convert_file_to_pdf(path: Path, output_dir: Path) -> Path:
    """Convert one supported file to PDF.

    Args:
        path: Source file to convert.
        output_dir: Folder where the resulting PDF is written.

    Returns:
        Path: Path to the generated or copied PDF.

    Raises:
        ValueError: If the file suffix has no conversion behaviour.
    """
    match path.suffix.lower():
        case ".pdf":
            return copy_pdf(path, output_dir)
        case suffix if suffix in OFFICE_SUFFIXES:
            return convert_office_to_pdf(path, output_dir)
        case _:
            raise ValueError(f"Unsupported file type: {path.suffix}")


def copy_pdf(path: Path, output_dir: Path) -> Path:
    """Copy an existing PDF into the PDF output folder.

    Args:
        path: Source PDF file.
        output_dir: Folder where the PDF copy is written.

    Returns:
        Path: Destination PDF path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / path.name
    shutil.copy2(path, destination)
    return destination


def convert_office_to_pdf(path: Path, output_dir: Path) -> Path:
    """Convert an Office document or presentation to PDF with LibreOffice.

    Args:
        path: Source `.doc`, `.docx`, `.ppt`, or `.pptx` file.
        output_dir: Folder where the generated PDF is written.

    Returns:
        Path: Destination PDF path.

    Raises:
        RuntimeError: If no LibreOffice command is available.
        FileNotFoundError: If the converter finishes without producing the
            expected PDF.
        subprocess.CalledProcessError: If LibreOffice exits with an error.
    """
    command = office_converter_command()
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            command,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    pdf_path = output_dir / f"{path.stem}.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    return pdf_path


def office_converter_command() -> str:
    """Find a local LibreOffice conversion command.

    Returns:
        str: Executable name or path for `soffice` or `libreoffice`.

    Raises:
        RuntimeError: If neither command is available on `PATH`.
    """
    for command in ("soffice", "libreoffice"):
        resolved = shutil.which(command)
        if resolved:
            return resolved
    raise RuntimeError("Office conversion requires soffice or libreoffice.")


def convert_all_to_pdf(files: list[Path], output_dir: Path) -> list[Path]:
    """Convert a list of files to PDF.

    Args:
        files: Source files to convert. Each file is handled independently,
            which makes this function straightforward to parallelise later.
        output_dir: Folder where PDFs are written.

    Returns:
        list[Path]: Paths to generated or copied PDFs.
    """
    return [convert_file_to_pdf(path, output_dir) for path in files]


def main() -> None:
    """Run aggregation followed by PDF conversion from the CLI.

    Returns:
        None.
    """
    args = parse_args()
    aggregated_files = aggregate_files(Path(args.input_folder))
    pdf_files = convert_all_to_pdf(
        files=aggregated_files,
        output_dir=Path(PDF_OUTPUT_FOLDER),
    )

    print(f"Aggregated {len(aggregated_files)} files.")
    print(f"Converted {len(pdf_files)} PDFs.")
    print(f"PDF files saved in: {PDF_OUTPUT_FOLDER}")


if __name__ == "__main__":
    main()
