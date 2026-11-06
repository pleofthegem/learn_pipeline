"""Shared author-block reading for PDF filenames and extracted metadata."""
import re
import unicodedata

from . import extraction_rules as rules
from .pdf_text import join_pdf_lines

NAME_PARTICLES = {'de', 'da', 'dos', 'das', 'van', 'von', 'der', 'den', 'del', 'la', 'le', 'du', 'di', 'd', 'l', 'al', 'el'}
NAME_PUNCTUATION = " .-'’–"


def strip_title_quotes(title: str) -> str:
    """Remove paired enclosing quotation marks, preserving quotes within a title."""
    pairs = {'"': '"', "'": "'", '“': '”', '‘': '’', '«': '»'}
    title = title.strip()
    while len(title) >= 2 and pairs.get(title[0]) == title[-1]:
        title = title[1:-1].strip()
    return title


def strip_author_markers(text: str) -> str:
    """Remove numeric/letter marker groups together, including comma-separated ones."""
    return rules.AUTHOR_AFFILIATION_SUFFIX_RE.sub('', unicodedata.normalize('NFC', text))


def clean_author_name(name: str) -> str:
    """Remove trailing affiliation markers; reject residual alphanumeric names."""
    name = strip_author_markers(name)
    name = rules.AUTHOR_MARKER_SUFFIX_RE.sub('', name)
    name = rules.AUTHOR_MARKER_SYMBOL_RE.sub('', name)
    name = re.sub(r'[0-9¹²³⁴⁵⁶⁷⁸⁹⁰]+(?=\s|[,\.]|$)', '', name)
    name = unicodedata.normalize('NFC', re.sub(r'\s+', ' ', name)).strip(' .,;')
    if not name or not any(c.isalpha() for c in name):
        return ''
    if any(not (c.isalpha() or unicodedata.category(c).startswith('M') or c in NAME_PUNCTUATION)
           for c in name):
        return ''
    return name


def normalise_author_separators(text: str) -> str:
    return re.sub(r'\s+\band\s+(?=[A-Z])|\s*&\s*(?=[A-Z])', ', ', text)


def is_initials_only(text: str) -> bool:
    text = clean_author_name(text).replace(' ', '')
    return bool(rules.AUTHOR_INITIALS_ONLY_RE.fullmatch(text))


def parse_author_names(text: str) -> list[str]:
    """Parse one author block, joining initials wrapped at comma boundaries."""
    names = []
    pending = ''
    for part in normalise_author_separators(strip_author_markers(text)).split(','):
        if re.fullmatch(r'\s*[a-z]\s*', part):
            continue  # A standalone lowercase affiliation marker is not a name.
        name = clean_author_name(part)
        if not name:
            continue
        if is_initials_only(name):
            pending = f'{pending} {name}'.strip()
            continue
        if pending:
            name, pending = f'{pending} {name}', ''
        names.append(name)
    return names


def _visible_text(line: dict) -> str:
    if line.get('spans'):
        return ''.join(span['text'] for span in line['spans'] if not span['flags'] & 1).strip()
    return line.get('text', '').strip()


def _raw_text(line: dict) -> str:
    return ''.join(s['text'] for s in line['spans']).strip() if line.get('spans') else line.get('text', '').strip()


def _boundary(line: dict) -> bool:
    text = _raw_text(line)
    if not text:
        return False
    # A leading marker identifies the associated affiliation, as distinct from
    # the trailing markers on names. Do not discard it and turn it into a name.
    if text[0].isdigit() or text.startswith(('*', '#', '†', '‡', '§')):
        return True
    heading = text.split(':', 1)[0].strip().lower()
    return bool(':' in text or '@' in text or 'http' in text.lower()
                or heading in rules.SECTION_HEADINGS or rules.KEYWORDS_RE.match(text))


def _name_shaped(text: str) -> bool:
    """Require name-shaped words, rather than any sentence containing a capital."""
    text = strip_author_markers(re.sub(r'^and\s+|\s+and\s*$', '', text))
    parts = normalise_author_separators(text).split(',')
    found = False
    for part in parts:
        name = clean_author_name(part)
        if not name:
            # Marker-only comma fragments are allowed, other invalid text is not.
            if any(c.isalpha() for c in part):
                return False
            continue
        words = re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)*", name, re.UNICODE)
        if len(words) > 8:
            return False
        if any(not (not word[0].islower() or word.lower() in NAME_PARTICLES
                    or ('’' in word and word.split('’', 1)[0].lower() in NAME_PARTICLES))
               for word in words):
            return False
        found = True
    return found


def _continues(previous: str, line: dict) -> bool:
    text = _raw_text(line)
    last = previous.rsplit(',', 1)[-1].strip()
    return bool((re.search(r'[^\W\d_][-‐‑]$', previous) and re.match(r'[^\W\d_]', _visible_text(line)))
                or previous.rstrip().endswith(',') or re.search(r'\band\s*$', previous)
                or is_initials_only(last)
                or rules.AUTHOR_MARKER_SUFFIX_RE.search(text)
                or rules.AUTHOR_AFFILIATION_SUFFIX_RE.search(text)
                or rules.NUMERIC_AUTHOR_MARKER_RE.search(text))


def formatted_author_block(lines: list[dict], title_end_index: int) -> str | None:
    """Read only the adjacent bold, upright author block; never scan body prose."""
    names = []
    style = None
    for line in lines[title_end_index + 1:]:
        if not _raw_text(line):
            continue
        if _boundary(line):
            break
        spans = [s for s in line.get('spans', []) if s['text'].strip()]
        letters = [s for s in spans if not s['flags'] & 1 and any(c.isalpha() for c in s['text'])]
        if not letters or not all(s['flags'] & 16 and not s['flags'] & 2 for s in letters):
            break
        current_style = (letters[0]['font'], round(letters[0]['size'], 1))
        if style is not None and (current_style != style or not _continues(names[-1], line)):
            break
        text = _visible_text(line)
        if not _name_shaped(text):
            break
        style = current_style
        names.append(text)
    return join_pdf_lines(names) if names else None


def author_names_from_lines(lines: list[dict], title_end_index: int) -> list[str]:
    """Use the same bounded author reader for filenames and metadata.

    When bold formatting is absent, inspect only the immediately adjacent name
    lines. Stop at the first non-name, leading affiliation marker, or style change.
    A failed header read returns no authors; it never searches later body text.
    """
    if not 0 <= title_end_index < len(lines):
        return []
    formatted = formatted_author_block(lines, title_end_index)
    if formatted:
        return parse_author_names(formatted)
    names = []
    style = None
    for line in lines[title_end_index + 1:]:
        if not _raw_text(line):
            continue
        if _boundary(line):
            break
        text = _visible_text(line)
        spans = [s for s in line.get('spans', []) if s['text'].strip()
                 and not s['flags'] & 1 and any(c.isalpha() for c in s['text'])]
        current_style = ((spans[0]['font'], round(spans[0]['size'], 1)) if spans
                         else ('', round(line.get('size', 0), 1)))
        if style is not None and (current_style != style or not _continues(names[-1], line)):
            break
        if not _name_shaped(text):
            break
        names.append(text)
        style = current_style
    return parse_author_names(join_pdf_lines(names))
