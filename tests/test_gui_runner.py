import pandas as pd
import pytest
from gui import runner


def test_drop_preserves_sources_and_handles_duplicate_names(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path / "app")
    source = tmp_path / "report.csv"
    source.write_text("original")
    runner.store_inputs("webinar", [source])
    runner.store_inputs("webinar", [source])
    folder = runner.input_folder("webinar")
    assert (folder / "report.csv").read_text() == "original"
    assert (folder / "report (2).csv").exists()
    runner.store_inputs("webinar", [folder / "report.csv"])
    assert len(list(folder.iterdir())) == 2
    assert source.read_text() == "original"


def test_invalid_drop_is_rejected_before_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path / "app")
    good = tmp_path / "good.csv"
    bad = tmp_path / "bad.txt"
    good.touch()
    bad.touch()
    with pytest.raises(ValueError):
        runner.store_inputs("webinar", [good, bad])
    assert not list(runner.input_folder("webinar").iterdir())


def test_abstract_fixed_outputs(tmp_path, monkeypatch, sample_pdf_path):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    runner.store_inputs("abstracts", [sample_pdf_path])
    runner.run_job("abstracts")
    outputs = runner.useful_outputs("abstracts")
    assert tmp_path / "output/handoff_bundle/abstract_metadata.csv" in outputs
    assert tmp_path / "output/handoff_bundle/pdfs/abstract_001.pdf" in outputs
    assert all("intermediate_outputs" not in str(p) for p in outputs)


def test_webinar_fixed_outputs(tmp_path, monkeypatch):
    regions = runner.ROOT / "webinar/Regions.csv"
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    folder = runner.input_folder("webinar")
    folder.mkdir(parents=True)
    (tmp_path / "webinar/Regions.csv").write_bytes(regions.read_bytes())
    (folder / "Workshop.csv").write_text(
        "Topic,Webinar ID\nWorkshop,12345\n"
        "Email,Join Time,Leave Time,Time in Session (minutes)\n"
        "one@example.com,2026-10-01 10:00,2026-10-01 11:00,60\n")
    output = tmp_path / "webinar/output"
    output.mkdir()
    (output / "old.xlsx").touch()
    runner.run_job("webinar")
    assert not (output / "old.xlsx").exists()
    assert len(runner.useful_outputs("webinar")) == 2
    assert len(pd.read_excel(output / "master_webinar_summary.xlsx")) == 1


def test_folder_import_filters_recurses_and_handles_name_collisions(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path / "app")
    source = tmp_path / "batch"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (source / "report.csv").write_text("first")
    (nested / "report.csv").write_text("second")
    (source / "notes.txt").write_text("ignored")
    runner.store_inputs("webinar", [source])
    files = runner.current_inputs("webinar")
    assert len(files) == 2
    assert {p.read_text() for p in files} == {"first", "second"}
    assert all(p.parent == runner.input_folder("webinar") for p in files)


def test_empty_folder_import_reports_no_supported_files(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path / "app")
    source = tmp_path / "empty"
    source.mkdir()
    with pytest.raises(ValueError, match="No supported"):
        runner.store_inputs("abstracts", [source])
