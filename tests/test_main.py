from pathlib import Path

import main as pipeline


def test_run_pipeline_calls_each_module_api_in_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Check that the top-level pipeline delegates to module APIs in order."""
    calls: list[str] = []
    input_folder = tmp_path / "input"
    output_root = tmp_path / "output"
    aggregate_folder = output_root / "abstracts_aggregated"
    raw_folder = output_root / "abstracts_raw"
    split_folder = output_root / "abstracts_split"
    clean_folder = output_root / "abstracts_clean"
    extract_csv_path = output_root / "abstract_csv" / "abstract_metadata.csv"
    extract_json_path = output_root / "abstract_json" / "abstract_metadata.json"
    anonymise_csv_path = output_root / "abstract_csv" / "anonymised_abstracts.csv"
    anonymise_json_path = output_root / "abstract_json" / "anonymised_abstracts.json"

    def fake_clear_folders(folders: list[Path]) -> dict[str, int]:
        calls.append("clear")
        assert folders == [
            aggregate_folder,
            raw_folder,
            split_folder,
            clean_folder,
            extract_csv_path.parent,
            extract_json_path.parent,
            anonymise_csv_path.parent,
            anonymise_json_path.parent,
        ]
        return {str(folder): 0 for folder in folders}

    def fake_convert_inputs_to_pdfs(
        input_folder: Path,
        aggregate_dir: Path,
        output_dir: Path,
    ) -> tuple[list[Path], list[Path]]:
        calls.append("convert")
        assert input_folder == tmp_path / "input"
        assert aggregate_dir == aggregate_folder
        assert output_dir == raw_folder
        return [aggregate_folder / "paper.docx"], [raw_folder / "paper.pdf"]

    def fake_split_combined_pdfs(
        input_folder: Path,
        output_folder: Path,
        staging_folder: Path,
    ) -> list[dict[str, object]]:
        calls.append("split")
        assert input_folder == raw_folder
        assert output_folder == raw_folder
        assert staging_folder == split_folder
        return [{"output_file": "split.pdf"}]

    def fake_extract_abstract_data(
        input_folder: Path,
        csv_path: Path,
        json_path: Path,
        default_additional_info: dict[str, str] | None = None,
    ) -> list[dict[str, str]]:
        calls.append("extract")
        assert input_folder == raw_folder
        assert csv_path == extract_csv_path
        assert json_path == extract_json_path
        assert default_additional_info == {
            "name": "Default conference",
            "place": "Default place",
        }
        return [{"filename": "paper.pdf"}]

    def fake_anonymise_pdf_abstracts(
        input_dir: Path,
        output_dir: Path,
        csv_path: Path,
        json_path: Path,
    ) -> list[dict[str, str]]:
        calls.append("anonymise")
        assert input_dir == raw_folder
        assert output_dir == clean_folder
        assert csv_path == anonymise_csv_path
        assert json_path == anonymise_json_path
        return [{"file_name": "paper.pdf"}]

    monkeypatch.setattr(
        pipeline.convert_to_pdf,
        "convert_inputs_to_pdfs",
        fake_convert_inputs_to_pdfs,
    )
    monkeypatch.setattr(
        pipeline.split_pdf,
        "split_combined_pdfs",
        fake_split_combined_pdfs,
    )
    monkeypatch.setattr(
        pipeline.extract_abstract_data,
        "extract_abstract_data",
        fake_extract_abstract_data,
    )
    monkeypatch.setattr(
        pipeline.anonymise_abstracts,
        "anonymise_pdf_abstracts",
        fake_anonymise_pdf_abstracts,
    )
    monkeypatch.setattr(
        pipeline.clear_outputs,
        "clear_folders",
        fake_clear_folders,
    )

    counts = pipeline.run_pipeline(
        input_folder=input_folder,
        aggregate_folder=aggregate_folder,
        raw_folder=raw_folder,
        split_folder=split_folder,
        clean_output_folder=clean_folder,
        extract_csv_path=extract_csv_path,
        extract_json_path=extract_json_path,
        anonymise_csv_path=anonymise_csv_path,
        anonymise_json_path=anonymise_json_path,
        default_additional_info={
            "name": "Default conference",
            "place": "Default place",
        },
    )

    assert calls == ["clear", "convert", "split", "extract", "anonymise"]
    assert counts == {
        "converted_pdfs": 1,
        "split_abstracts": 1,
        "metadata_rows": 1,
        "anonymised_pdfs": 1,
    }
