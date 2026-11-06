"""Local document adapters and bounded OCR. No network access in this module."""
import csv
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET

ENGINE_VERSION = 'hybrid-5.0'
FORMATS = {'.pdf', '.docx', '.txt', '.md', '.png', '.jpg', '.jpeg', '.tif', '.tiff'}
MAX_PAGES = 1500
MAX_TEXT_BYTES = 16 * 1024 * 1024


def native_page_text(page):
    """Read clear two-column syllabus layouts in column order, keeping page furniture.

    Require independent section headings in both columns to avoid turning ordinary
    two-column syllabus tables into two unrelated streams of text.
    """
    default = page.get_text('text', sort=True) or ''
    blocks = [b for b in page.get_text('blocks') if b[6] == 0 and b[4].strip()]
    middle = (page.rect.x0 + page.rect.x1) / 2
    left = [b for b in blocks if b[2] < middle - 6]
    right = [b for b in blocks if b[0] > middle + 6]
    heading = re.compile(r'(?im)^\s*(?:UNIT|MODULE|CHAPTER|WEEK|LESSON|TOPIC)\s+\w+')
    if not left or not right or not any(heading.search(b[4]) for b in left) or not any(heading.search(b[4]) for b in right):
        return default, 'single_or_table', []
    span = [b for b in blocks if b not in left and b not in right]
    top = min(b[1] for b in left + right)
    bottom = max(b[3] for b in left + right)
    if any(b[1] >= top and b[3] <= bottom for b in span):
        return default, 'complex_columns', ['Mixed-width columns could not be safely reordered; review this page against the original.']
    before = sorted([b for b in span if b[1] < top], key=lambda b: (b[1], b[0]))
    after = sorted([b for b in span if b[1] >= top], key=lambda b: (b[1], b[0]))
    ordered = before + sorted(left, key=lambda b: (b[1], b[0])) + sorted(right, key=lambda b: (b[1], b[0])) + after
    return '\n'.join(b[4].rstrip() for b in ordered), 'two_columns', ['Two-column reading order was reconstructed from page geometry; review column transitions.']


def ocr_capabilities():
    executable = os.environ.get('SYLEX_TESSERACT') or shutil.which('tesseract')
    if not executable:
        candidate = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tesseract-OCR/tesseract.exe'
        if candidate.is_file():
            executable = str(candidate)
    data = os.environ.get('TESSDATA_PREFIX')
    if not data and executable:
        for folder in [Path(executable).parent / 'tessdata', Path('/usr/share/tesseract-ocr/5/tessdata'), Path('/usr/share/tesseract-ocr/4.00/tessdata')]:
            if folder.is_dir():
                data = str(folder)
                break
    languages = sorted(p.stem for p in Path(data).glob('*.traineddata')) if data else []
    requested = os.environ.get('SYLEX_OCR_LANGUAGES', 'eng')
    return {'available': bool(executable and (not languages or all(x in languages for x in requested.split('+')))),
            'executable': executable, 'tessdata': data, 'languages': languages, 'requested': requested}


def validate_document(data, filename):
    extension = Path(filename or 'document.pdf').suffix.lower()
    if extension not in FORMATS:
        raise ValueError('Supported files: PDF, DOCX, UTF-8 TXT/MD, PNG, JPEG and TIFF. Convert legacy DOC files to DOCX or PDF.')
    if extension == '.pdf' and b'%PDF-' not in data[:1024]:
        raise ValueError('Uploaded file is not a valid PDF')
    if extension == '.docx':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo('word/document.xml')
            if info.file_size > MAX_TEXT_BYTES or info.flag_bits & 1:
                raise ValueError('DOCX content is encrypted or exceeds the 16 MB text limit')
    if extension in {'.txt', '.md'}:
        if len(data) > MAX_TEXT_BYTES:
            raise ValueError('Text document exceeds the 16 MB limit')
        data.decode('utf-8-sig')
        if b'\x00' in data:
            raise ValueError('Text documents must contain UTF-8 text, not binary data')
    return extension


def read_non_pdf(path):
    """Return logical pages; DOCX paragraphs and table rows retain document order."""
    extension = Path(path).suffix.lower()
    if extension in {'.txt', '.md'}:
        raw = Path(path).read_bytes()
        validate_document(raw, path)
        text = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
        if extension == '.md':
            text = re.sub(r'(?m)^#{1,6}\s+', '', text)
        return [{'text': chunk, 'tables': [], 'method': 'text', 'warnings': []}
                for chunk in text.split('\f')]
    if extension != '.docx':
        return None
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    tag = lambda name: '{' + ns['w'] + '}' + name
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo('word/document.xml')
        if info.file_size > MAX_TEXT_BYTES:
            raise ValueError('DOCX text exceeds the 16 MB limit')
        xml = archive.read(info)
    if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
        raise ValueError('DOCX contains unsupported XML declarations')
    root = ET.fromstring(xml)
    body = root.find('w:body', ns)
    if body is None:
        raise ValueError('DOCX has no document body')
    def paragraph(node):
        parts = []
        for element in node.iter():
            if element.tag == tag('t'):
                parts.append(element.text or '')
            elif element.tag == tag('tab'):
                parts.append('\t')
            elif element.tag == tag('br'):
                parts.append('\f' if element.get(tag('type')) == 'page' else '\n')
        return ''.join(parts)
    pages = [{'text': '', 'tables': [], 'method': 'docx', 'warnings': []}]
    for child in body:
        if child.tag == tag('tbl'):
            table = [[ '\n'.join(paragraph(p) for p in cell.findall('w:p', ns))
                      for cell in row.findall('w:tc', ns)] for row in child.findall('w:tr', ns)]
            pages[-1]['tables'].append(table)
            pages[-1]['text'] += '\n'.join('  '.join(row) for row in table) + '\n'
        elif child.tag == tag('p'):
            for index, chunk in enumerate(paragraph(child).split('\f')):
                if index:
                    pages.append({'text': '', 'tables': [], 'method': 'docx', 'warnings': []})
                pages[-1]['text'] += chunk + '\n'
    for page in pages:
        page['warnings'].append('DOCX page numbers are logical sections separated by explicit page breaks; layout pagination is not available.')
    return pages


class LocalOCR:
    """Tesseract subprocesses have a per-page timeout and a document time budget."""
    def __init__(self, budget_seconds=None):
        self.capabilities = ocr_capabilities()
        self.deadline = time.monotonic() + (80 if budget_seconds is None else budget_seconds)

    def read(self, page):
        info = self.capabilities
        if not info['available']:
            return None, 'OCR unavailable: install Tesseract and the requested language data before going offline.'
        remaining = self.deadline - time.monotonic()
        if remaining <= 1:
            return None, 'OCR document time budget reached; split this scan into smaller documents.'
        try:
            # Cap raster memory independently of the input PDF page size.
            import pymupdf as fitz
            scale = min(3.0, (10_000_000 / max(1, page.rect.width * page.rect.height)) ** 0.5)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False)
            with tempfile.TemporaryDirectory(prefix='sylex-ocr-') as folder:
                source = str(Path(folder) / 'page.png')
                pix.save(source)
                cmd = [info['executable'], source, 'stdout', '-l', info['requested'], '--psm', '3']
                if info['tessdata']:
                    cmd += ['--tessdata-dir', info['tessdata']]
                cmd += ['tsv']
                result = subprocess.run(cmd, capture_output=True, timeout=min(18, remaining),
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                return None, 'Local OCR could not read this page; check the installed language data.'
            lines, words, confidence = {}, [], []
            for row in csv.DictReader(io.StringIO(result.stdout.decode('utf-8', errors='replace')), delimiter='\t'):
                text = (row.get('text') or '').strip()
                if row.get('level') != '5' or not text:
                    continue
                key = (row['block_num'], row['par_num'], row['line_num'])
                lines.setdefault(key, []).append(text)
                x, y, w, h = (float(row[k]) / scale for k in ('left', 'top', 'width', 'height'))
                words.append({'text': text, 'x0': x, 'y0': y, 'x1': x+w, 'y1': y+h})
                confidence.append(float(row['conf']))
            text = '\n'.join(' '.join(line) for line in lines.values())
            return {'text': text, 'words': words, 'confidence': round(sum(confidence) / max(1, len(confidence)), 1)}, None
        except subprocess.TimeoutExpired:
            return None, 'OCR page timeout; use a clearer scan or a smaller document.'
        except Exception:
            return None, 'OCR failed on this page; its text needs manual review.'


def source_report(reader):
    pages = reader.page_diagnostics
    warnings = sorted(set(w for p in pages for w in p.get('warnings', [])))
    unreadable = [p['page'] for p in pages if p.get('needs_review')]
    return {'engine': ENGINE_VERSION, 'sha256': reader._sha, 'format': Path(reader.path).suffix.lower().lstrip('.'),
            'page_count': reader.page_count, 'pages': pages, 'review_pages': unreadable, 'warnings': warnings,
            'ocr_pages': [p['page'] for p in pages if p['method'] in {'ocr', 'cloud_vision'}],
            'vision_pages': [p['page'] for p in pages if p['method'] == 'cloud_vision']}
