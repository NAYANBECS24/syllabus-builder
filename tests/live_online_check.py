"""Opt-in live test using generated material only: python tests/live_online_check.py [--vision]."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf as fitz
import sylex_server as server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vision', action='store_true')
    args = parser.parse_args()
    handler = object.__new__(server.Handler)
    with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SYLEX_CACHE_DIR': 'off'}):
        path = str(Path(folder) / 'synthetic-syllabus.pdf')
        text = '\n'.join(['CS50 INTRODUCTION TO ECOLOGY', 'COURSE OBJECTIVES:', 'Understand ecosystems.',
            'UNIT I FOREST HABITATS 4 hours', 'Forest habitats support biodiversity.', 'UNIT II POPULATIONS 3 hours',
            'Population dynamics and migration.', 'COURSE OUTCOMES:', 'CO1 Explain forest biodiversity. K2', 'Credits: 2.5'])
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((45, 50), text, fontsize=13)
            if args.vision:
                png = page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes('png')
            else:
                doc.save(path)
        if args.vision:
            with fitz.open() as doc:
                page = doc.new_page()
                page.insert_image(page.rect, stream=png)
                doc.save(path)
            with patch('document_ingest.LocalOCR.read', return_value=(None, 'OCR unavailable for this cloud regression')):
                result = handler._run_online(path, 'CS50', model='nvidia/nemotron-3.5-bolt-e4b')
        else:
            result = handler._run_online(path, 'CS50', model='nvidia/nemotron-3.5-bolt-e4b')
        print(json.dumps({'vision_test': args.vision, 'processing': result.get('_processing'), 'review': result.get('_online'),
            'course': result.get('course'), 'unit_count': len(result.get('units', [])), 'vision_pages': result.get('_source', {}).get('vision_pages')}, indent=2))
        assert result['_processing']['used_mode'] == 'online', 'Live cloud review did not complete'
        assert result.get('course', {}).get('code') == 'CS50', 'Source-backed course recovery failed'
        assert len(result['units']) == 2, 'Unit extraction did not match the generated source'
        if args.vision:
            assert result['_source']['vision_pages'] == [1], 'Live vision transcription did not complete'


if __name__ == '__main__': main()
