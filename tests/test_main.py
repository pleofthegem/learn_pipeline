import csv
import json
from pathlib import Path
import shutil

import pytest

from scripts import main as pipeline
from scripts.config import INPUT_FOLDER, OUTPUT_ROOT
from test_split_pdf import write_combined_pdf


def test_minimal_bundle_contains_pdfs_and_matching_metadata(sample_input_dir, tmp_path, monkeypatch):
    output = tmp_path / "output"
    (sample_input_dir / "abstract_003.docx").unlink()
    # Conversion and anonymisation must not run for a default PDF batch.
    def unexpected(*args, **kwargs):
        pytest.fail("Optional processing ran in minimal mode")
    monkeypatch.setattr(pipeline.convert_to_pdf, "convert_inputs_to_pdfs", unexpected)
    monkeypatch.setattr(pipeline.convert_to_pdf, "office_converter_command", unexpected)
    monkeypatch.setattr(pipeline.anonymise_abstracts, "anonymise_pdf_abstracts", unexpected)
    before = {p.name: p.read_bytes() for p in sample_input_dir.iterdir()}
    counts = pipeline.run_pipeline(sample_input_dir, output, default_additional_info={"name": "Conference", "place": "London"})
    bundle = output / "handoff_bundle"
    with (bundle / "abstract_metadata.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert {row['filename'] for row in rows} == {p.name for p in (bundle / "pdfs").iterdir()}
    assert len(rows) == counts['metadata_rows'] == 2
    assert counts['anonymised_pdfs'] == 0
    assert json.loads(rows[0]['additional_info']) == {"name": "Conference", "place": "London"}
    assert not (output / "intermediate_outputs/abstracts_clean").exists()
    assert {p.name: p.read_bytes() for p in sample_input_dir.iterdir()} == before
    assert {p.name for p in output.iterdir()} == {"handoff_bundle", "intermediate_outputs"}


def test_combined_source_is_split_in_bundle_and_original_is_preserved(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    book = source / "book.pdf"
    write_combined_pdf(book)
    original = book.read_bytes()
    output = tmp_path / "output"
    counts = pipeline.run_pipeline(source, output)
    pdfs = output / "handoff_bundle/pdfs"
    assert counts['split_abstracts'] == counts['metadata_rows'] == 2
    assert len(list(pdfs.glob('*.pdf'))) == 2
    assert len(list(output.rglob('*.pdf'))) == 2
    assert not (pdfs / 'book.pdf').exists()
    assert book.read_bytes() == original
    assert (output / 'intermediate_outputs/abstracts_split/split_abstracts.csv').exists()


@pytest.mark.parametrize('full', [False, True])
def test_word_conversion_is_automatic_and_anonymisation_is_optional(sample_input_dir, tmp_path, monkeypatch, full):
    output = tmp_path / 'output'
    monkeypatch.setattr(pipeline.convert_to_pdf, 'office_converter_command', lambda: 'soffice')
    def convert_words(paths, output_dir):
        targets = []
        for path in paths:
            assert path.suffix == '.docx'
            target = output_dir / f'{path.stem}.pdf'
            shutil.copy2(sample_input_dir / 'abstract_001.pdf', target)
            targets.append(target)
        return targets
    monkeypatch.setattr(pipeline.convert_to_pdf, 'convert_office_files_to_pdf', convert_words)
    original = {p.name: p.read_bytes() for p in sample_input_dir.iterdir()}
    counts = pipeline.run_pipeline(sample_input_dir, output, full=full)
    assert counts['converted_pdfs'] == counts['metadata_rows'] == 3
    assert counts['anonymised_pdfs'] == (3 if full else 0)
    intermediate = output / 'intermediate_outputs'
    if full:
        assert len(list((intermediate / 'abstracts_clean').glob('*.txt'))) == 3
        assert '[EMAIL_REMOVED]' in next((intermediate / 'abstracts_clean').glob('*.txt')).read_text()
        assert (intermediate / 'csv/anonymised_abstracts.csv').exists()
        assert (intermediate / 'json/anonymised_abstracts.json').exists()
        # Switching to the default run still converts Word and removes optional outputs.
        counts = pipeline.run_pipeline(sample_input_dir, output)
        assert counts['metadata_rows'] == 3
        assert counts['anonymised_pdfs'] == 0
    assert not (intermediate / 'abstracts_clean').exists()
    assert not (intermediate / 'csv/anonymised_abstracts.csv').exists()
    assert not (intermediate / 'json/anonymised_abstracts.json').exists()
    assert {p.name: p.read_bytes() for p in sample_input_dir.iterdir()} == original


@pytest.mark.parametrize('relation', ['same', 'output_inside_input', 'input_inside_output'])
def test_overlapping_folders_are_rejected_before_deletion(tmp_path, relation):
    source = tmp_path / 'input'
    output = {'same': source, 'output_inside_input': source / 'output', 'input_inside_output': tmp_path}[relation]
    source.mkdir()
    sentinel = source / 'keep.pdf'
    sentinel.write_bytes(b'preserve')
    with pytest.raises(ValueError, match='separate'):
        pipeline.run_pipeline(source, output)
    assert sentinel.read_bytes() == b'preserve'


def test_invalid_input_does_not_clear_previous_bundle(tmp_path):
    output = tmp_path / 'output'
    bundle = output / 'handoff_bundle'
    bundle.mkdir(parents=True)
    previous = bundle / 'abstract_metadata.csv'
    previous.write_text('previous results')
    missing = tmp_path / 'missing'
    with pytest.raises(ValueError, match='does not exist'):
        pipeline.run_pipeline(missing, output)
    missing.mkdir()
    with pytest.raises(ValueError, match='No supported'):
        pipeline.run_pipeline(missing, output)
    assert previous.read_text() == 'previous results'


def test_cli_defaults_are_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('sys.argv', ['pipeline'])
    args = pipeline.parse_args()
    assert args.input_folder == INPUT_FOLDER
    assert args.output_folder == OUTPUT_ROOT
    assert args.full is False
    monkeypatch.setattr('sys.argv', ['pipeline', '--full'])
    assert pipeline.parse_args().full is True


def test_default_word_only_batch_uses_one_office_process_before_metadata(tmp_path, sample_pdf_path, monkeypatch):
    import subprocess
    source = tmp_path / 'inputs'
    source.mkdir()
    names = ['first.doc', 'second.docx', 'third.DOCX']
    for name in names:
        (source / name).write_text(name)
    calls = []
    monkeypatch.setattr(pipeline.convert_to_pdf, 'office_converter_command', lambda: 'soffice')
    def run(args, **kwargs):
        calls.append(args)
        destination = Path(args[args.index('--outdir') + 1])
        documents = args[args.index('--outdir') + 2:]
        assert len(documents) == 3
        for document in map(Path, documents):
            shutil.copy2(sample_pdf_path, destination / f'{document.stem}.pdf')
        return subprocess.CompletedProcess(args, 0, stdout='', stderr='')
    monkeypatch.setattr(pipeline.convert_to_pdf.subprocess, 'run', run)
    output = tmp_path / 'output'
    counts = pipeline.run_pipeline(source, output)
    assert len(calls) == 1
    assert counts['converted_pdfs'] == counts['metadata_rows'] == 3
    assert counts['anonymised_pdfs'] == 0
    assert {p.name for p in (output / 'handoff_bundle/pdfs').glob('*.pdf')} == {
        'first.pdf', 'second.pdf', 'third.pdf',
    }
    assert not (output / 'intermediate_outputs/abstracts_clean').exists()
    assert {p.name: p.read_text() for p in source.iterdir()} == {name: name for name in names}


def test_missing_office_does_not_clear_previous_bundle_for_default_word_run(tmp_path, monkeypatch):
    source = tmp_path / 'inputs'
    source.mkdir()
    word = source / 'paper.docx'
    word.write_bytes(b'original Word document')
    output = tmp_path / 'output'
    previous = output / 'handoff_bundle/abstract_metadata.csv'
    previous.parent.mkdir(parents=True)
    previous.write_text('previous metadata')
    def missing_office():
        raise RuntimeError('Office conversion requires soffice or libreoffice.')
    monkeypatch.setattr(pipeline.convert_to_pdf, 'office_converter_command', missing_office)
    with pytest.raises(RuntimeError, match='Office conversion requires'):
        pipeline.run_pipeline(source, output)
    assert previous.read_text() == 'previous metadata'
    assert word.read_bytes() == b'original Word document'
