"""Clear generated pipeline output folders for a fresh run."""

import shutil
from pathlib import Path

OUTPUT_FOLDERS = [
    Path("abstract_csv"),
    Path("abstract_json"),
    Path("abstracts_aggregated"),
    Path("abstracts_clean"),
    Path("abstracts_raw"),
    Path("abstracts_split"),
]


def clear_folder(folder: Path) -> int:
    """Remove every file and subfolder inside `folder`, keeping `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    removed_count = 0

    for path in folder.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed_count += 1

    return removed_count


def clear_outputs(base_dir: Path = Path(".")) -> dict[str, int]:
    """Clear generated output folders under `base_dir`."""
    return {
        str(folder): clear_folder(base_dir / folder)
        for folder in OUTPUT_FOLDERS
    }


def clear_folders(folders: list[Path]) -> dict[str, int]:
    """Clear the given folders, de-duplicating repeated paths."""
    removed_counts: dict[str, int] = {}

    for folder in folders:
        folder = Path(folder)
        if str(folder) in removed_counts:
            continue
        removed_counts[str(folder)] = clear_folder(folder)

    return removed_counts


def main() -> None:
    """Clear generated output folders and print a short summary."""
    removed_counts = clear_outputs()
    for folder, count in removed_counts.items():
        print(f"Cleared {folder}: {count} items removed")


if __name__ == "__main__":
    main()
