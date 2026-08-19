"""Aggregate source files and convert supported inputs to PDF."""

import argparse
import re
import shutil
import subprocess
from pathlib import Path

import fitz

OUTPUT_ROOT: str = "output"
AGGREGATED_FOLDER: str = f"{OUTPUT_ROOT}/abstracts_aggregated"
PDF_OUTPUT_FOLDER: str = f"{OUTPUT_ROOT}/abstracts_raw"
OFFICE_SUFFIXES: set[str] = {".doc", ".docx"}
SUPPORTED_SUFFIXES: set[str] = {'.pdf', *OFFICE_SUFFIXES}
POWERPOINT_PDF_MARKERS: tuple[str, ...] = ("pptx", "ppt", "presentation")


def alter_file_name(file_name: str) -> str:
    """Add or increment a Windows-style duplicate suffix in a file name."""
    path = Path(file_name)
    # Has this file already been altered?
    match = re.match(r"^(?P<stem>.*)\((?P<count>\d+)\)$", path.stem)
    if match:
        stem = match.group("stem")
        count = int(match.group("count")) + 1
    else:
        stem = path.stem
        count = 1

    return f"{stem}({count}){path.suffix}"


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
    """Copy every supported file under an input folder into one aggregate folder.
Exclude unsupported files.
Fails if the output folder is the same as the input folder
    Args:
        input_folder: Root folder to scan for supported files, including nested
            files.
        aggregate_dir: Destination folder that receives copied files.

    Returns:
        list[Path]: Paths to copied supported files in the aggregate folder.
    """
    input_folder = Path(input_folder)
    aggregate_dir = Path(aggregate_dir)
    input_folder.mkdir(parents=True, exist_ok=True)
    aggregate_dir.mkdir(parents=True, exist_ok=True)
    aggregate_dir_resolved = aggregate_dir.resolve()

    copied: list[Path] = []
    destinations: dict[Path, Path] = {}
    for path in sorted(input_folder.rglob("*")):
        if not path.is_file():
            continue
        if path.resolve().is_relative_to(aggregate_dir_resolved):
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            # If unsupported then don't consider it.
            continue
        if is_powerpoint_pdf(path):
            continue
        if is_password_protected_pdf(path):
            continue

        relative_path = path.relative_to(input_folder)
        destination = aggregate_destination(aggregate_dir, relative_path)
        while destination in destinations or destination.exists():
            destination = destination.with_name(
                alter_file_name(destination.name))

        destinations[destination] = relative_path
        shutil.copy2(path, destination)
        copied.append(destination)

    return copied


def aggregate_destination(aggregate_dir: Path, relative_path: Path) -> Path:
    """Build an aggregate path from the top-level folder and file name.

    Args:
        aggregate_dir: Folder that receives aggregated files.
        relative_path: Source path relative to the original input root.

    Returns:
        Path: Destination path using the top-level source folder plus the file
            name for nested files. Files directly under the input root keep
            their original name.
    """
    if len(relative_path.parts) == 1:
        return aggregate_dir / relative_path.name
    return aggregate_dir / f"{relative_path.parts[0]}__{relative_path.name}"


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


def is_powerpoint_pdf(path: Path) -> bool:
    """Check whether a PDF path looks like it came from a presentation."""
    if path.suffix.lower() != ".pdf":
        return False

    searchable_path = " ".join(path.parts).casefold()
    return any(marker in searchable_path for marker in POWERPOINT_PDF_MARKERS)


def is_password_protected_pdf(path: Path) -> bool:
    """Check whether a PDF requires a password before text can be read."""
    if path.suffix.lower() != ".pdf":
        return False

    try:
        with fitz.open(path) as pdf:
            return bool(pdf.needs_pass)
    except (fitz.FileDataError, RuntimeError):
        return False


def copy_pdf(path: Path, output_dir: Path) -> Path:
    """Copy an existing PDF into the PDF output folder.

    Args:
        path: Source PDF file.
        output_dir: Folder where the PDF copy is written.

    Returns:
        Path: Destination PDF path.
    """
    # Catches any powerpoint or password protected pdfs, which allows us to remove them from input.
    if is_powerpoint_pdf(path):
        raise ValueError(f"Unsupported PowerPoint PDF: {path.name}")
    if is_password_protected_pdf(path):
        raise ValueError(f"Unsupported password-protected PDF: {path.name}")

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / path.name
    if path.resolve() == destination.resolve():
        return destination

    shutil.copy2(path, destination)
    return destination


def convert_office_to_pdf(path: Path, output_dir: Path) -> Path:
    """Convert an Office document to PDF with LibreOffice.

    Args:
        path: Source `.doc` or `.docx` file.
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
    output_dir.mkdir(parents=True, exist_ok=True)
    return [convert_file_to_pdf(path, output_dir) for path in files]


def convert_inputs_to_pdfs(
    input_folder: Path,
    aggregate_dir: Path = Path(AGGREGATED_FOLDER),
    output_dir: Path = Path(PDF_OUTPUT_FOLDER),
) -> tuple[list[Path], list[Path]]:
    """Aggregate supported source files and convert them to PDFs.

    Args:
        input_folder: Root folder to scan for supported source files.
        aggregate_dir: Intermediary folder that receives flattened source
            files before conversion.
        output_dir: Final folder that receives PDF files.

    Returns:
        tuple[list[Path], list[Path]]: A tuple containing the aggregated source
            file paths and the resulting PDF paths.
    """
    aggregated_files = aggregate_files(Path(input_folder), Path(aggregate_dir))
    pdf_files = convert_all_to_pdf(
        files=aggregated_files,
        output_dir=Path(output_dir),
    )
    return aggregated_files, pdf_files


def main() -> None:
    """Run aggregation followed by PDF conversion from the CLI.

    Returns:
        None.
    """
    args = parse_args()
    aggregated_files, pdf_files = convert_inputs_to_pdfs(
        input_folder=Path(args.input_folder),
    )

    print(f"Aggregated {len(aggregated_files)} files.")
    print(f"Converted {len(pdf_files)} PDFs.")
    print(f"PDF files saved in: {PDF_OUTPUT_FOLDER}")


if __name__ == "__main__":
    main()
