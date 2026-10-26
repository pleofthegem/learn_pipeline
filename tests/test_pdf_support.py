from pathlib import Path

import fitz
import pytest

from pdf_support import open_pdf


def make_profile_pdf(path, profile_bytes=b'', components=3, alternate=''):
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), 'Abstract: Text must remain unchanged.')
        image = page.insert_image(fitz.Rect(72, 100, 100, 128),
                                  pixmap=fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1, 1), False))
        profile = pdf.get_new_xref()
        pdf.update_object(profile, f'<< /N {components} {alternate} >>')
        pdf.update_stream(profile, profile_bytes)
        space = pdf.get_new_xref()
        pdf.update_object(space, f'[/ICCBased {profile} 0 R]')
        pdf.xref_set_key(image, 'ColorSpace', f'{space} 0 R')
        pdf.save(path)
    return space


def test_empty_icc_fallback_preserves_text_and_source(tmp_path, capsys):
    source = tmp_path / 'empty-profile.pdf'
    space = make_profile_pdf(source)
    original = source.read_bytes()
    fitz.TOOLS.reset_mupdf_warnings()
    with open_pdf(source) as pdf:
        assert pdf.xref_object(space) == '/DeviceRGB'
        assert 'Text must remain unchanged.' in pdf[0].get_text()
        with fitz.open() as split:
            split.insert_pdf(pdf)
            split.save(tmp_path / 'split.pdf')
    with fitz.open(tmp_path / 'split.pdf') as split:
        assert 'Text must remain unchanged.' in split[0].get_text()
    assert 'cmsOpenProfileFromMem' not in fitz.TOOLS.mupdf_warnings()
    assert 'cmsOpenProfileFromMem' not in capsys.readouterr().out
    assert source.read_bytes() == original


@pytest.mark.parametrize('data,components,alternate', [
    (b'nonempty profile left alone', 3, ''),
    (b'', 2, ''),
    (b'', 3, '/Alternate /DeviceCMYK'),
])
def test_unrelated_profiles_are_not_modified(tmp_path, data, components, alternate):
    source = tmp_path / 'profile.pdf'
    space = make_profile_pdf(source, data, components, alternate)
    with fitz.open(source) as pdf:
        original = pdf.xref_object(space)
    with open_pdf(source) as pdf:
        assert pdf.xref_object(space) == original
