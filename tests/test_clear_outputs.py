from pathlib import Path

from clear_outputs import OUTPUT_FOLDERS, clear_outputs


def test_clear_outputs_removes_only_generated_output_contents(
    tmp_path: Path,
) -> None:
    """Check that generated output folders are emptied but kept."""
    for folder in OUTPUT_FOLDERS:
        target = tmp_path / folder
        nested = target / "nested"
        nested.mkdir(parents=True)
        (target / "output.txt").write_text("old output", encoding="utf-8")
        (nested / "nested.txt").write_text("old nested output", encoding="utf-8")

    input_folder = tmp_path / "input"
    input_folder.mkdir()
    (input_folder / "source.pdf").write_text("keep me", encoding="utf-8")

    removed_counts = clear_outputs(tmp_path)

    assert removed_counts == {str(folder): 2 for folder in OUTPUT_FOLDERS}
    for folder in OUTPUT_FOLDERS:
        target = tmp_path / folder
        assert target.exists()
        assert list(target.iterdir()) == []
    assert (input_folder / "source.pdf").exists()


def test_clear_outputs_creates_missing_output_folders(tmp_path: Path) -> None:
    """Check that clearing an empty workspace creates the output folders."""
    removed_counts = clear_outputs(tmp_path)

    assert removed_counts == {str(folder): 0 for folder in OUTPUT_FOLDERS}
    for folder in OUTPUT_FOLDERS:
        assert (tmp_path / folder).is_dir()
