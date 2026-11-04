"""Synthetic documents exercise real local parsing, OCR, boundaries and cache recovery."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from xml.sax.saxutils import escape

import pymupdf as fitz
import document_ingest
import offline_cache
import sylex


def course(code='CS101', title='DATA STRUCTURES', topic='Binary trees and graph traversal.'):
    return '\n'.join([f'{code} {title}', 'COURSE OBJECTIVES:', 'Understand the printed course topics.',
                      'UNIT I FUNDAMENTALS 9', topic, 'COURSE OUTCOMES:', 'CO1 Explain the concepts. K2'])


class OfflineExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'SYLEX_CACHE_DIR': str(self.root / 'cache')})
        self.env.start()
        sylex._GLOBAL_COURSE_DETECTOR_CACHE.clear()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def pdf(self, texts, filename='source.pdf'):
        path = self.root / filename
        with fitz.open() as doc:
            for text in texts:
                doc.new_page().insert_text((40, 45), text, fontsize=11)
            doc.save(path)
        return str(path)

    def test_continuation_pages_survive_catalog_hints(self):
        path = self.pdf([course(), 'UNIT II SORTING 6\nMerge sort and quick sort.', course('CS102', 'DATABASE SYSTEMS', 'Relational algebra.')])
        catalog = sylex.run_task1(path)
        result = sylex.run_task2(path, 'CS101', {'courses': catalog['courses']})
        self.assertEqual(result['course']['pages'], [1, 2])
        self.assertEqual([u['number'] for u in result['units']], [1, 2])
        self.assertIn('Merge sort', result['units'][1]['text'])
        self.assertNotIn('Relational algebra', json.dumps(result['units']))

    def test_two_courses_on_one_page_do_not_leak(self):
        path = self.pdf([course() + '\n\n' + course('CS102', 'DATABASE SYSTEMS', 'Relational algebra.')])
        catalog = sylex.run_task1(path)
        self.assertEqual({c['code'] for c in catalog['courses']}, {'CS101', 'CS102'})
        first = sylex.run_task2(path, 'CS101', {'courses': catalog['courses']})
        second = sylex.run_task2(path, 'CS102', {'courses': catalog['courses']})
        self.assertNotIn('Relational algebra', json.dumps(first['units']))
        self.assertNotIn('Binary trees', json.dumps(second['units']))
        self.assertIn('Relational algebra', json.dumps(second['units']))

    def test_long_course_is_not_truncated_after_four_pages(self):
        path = self.pdf([course()] + [f'UNIT {i} ADVANCED TOPICS\nContinuation content number {i}.' for i in range(2, 9)])
        result = sylex.run_task2(path, 'CS101')
        self.assertEqual(len(result['units']), 8)
        self.assertEqual(result['course']['pages'], list(range(1, 9)))

    def test_dotted_numeric_and_spaced_course_codes(self):
        for code in ['6.0001', '34421002', 'CS 101']:
            with self.subTest(code=code):
                path = self.pdf([course(code)], code.replace(' ', '_') + '.pdf')
                catalog = sylex.run_task1(path)
                self.assertTrue(any(sylex.codes_match(c['code'], code) for c in catalog['courses']), catalog)
                self.assertTrue(sylex.run_task2(path, code)['course'])

    def test_short_codes_bracketed_codes_and_labelled_identity_are_extracted(self):
        cases = [
            ('CS50 INTRODUCTION TO COMPUTING', 'CS50', 'INTRODUCTION TO COMPUTING'),
            ('INTRODUCTION TO COMPUTING (CS50)', 'CS50', 'INTRODUCTION TO COMPUTING'),
            ('Subject Code: CS50\nSubject Name: INTRODUCTION TO COMPUTING\nL T P C\n3 0 0 3', 'CS50', 'INTRODUCTION TO COMPUTING'),
        ]
        for index, (identity, code, title) in enumerate(cases):
            with self.subTest(identity=identity):
                path = self.pdf([identity + '\nUNIT 1 FOUNDATIONS\nComputational thinking and algorithms.'], f'identity-{index}.pdf')
                catalog = sylex.run_task1(path)
                self.assertTrue(any(sylex.codes_match(c['code'], code) and c['title'] == title for c in catalog['courses']), catalog)
                result = sylex.run_task2(path, code)
                self.assertEqual(result['course']['code'], code)
                self.assertEqual(result['course']['title'], title)

    def test_hours_before_unit_title_are_not_mislabelled(self):
        path = self.pdf(['CS50 COMPUTING\nMODULE 1\n(6 hours): FOUNDATIONS\nComputational thinking and algorithms.\nMODULE 2\n(4 hours): DATA\nData representation and storage.'])
        result = sylex.run_task2(path, 'CS50')
        self.assertEqual([(unit['title'], unit['hours']) for unit in result['units']], [('FOUNDATIONS', 6), ('DATA', 4)])

    def test_source_audit_marks_tampered_values_for_review(self):
        path = self.pdf([course()])
        result = sylex.run_task2(path, 'CS101')
        self.assertEqual(result['_audit']['status'], 'verified', result['_audit'])
        changed = json.loads(json.dumps(result))
        changed['units'][0]['text'] = 'Invented material that is not present in the document.'
        audit = sylex.audit_extraction_output(changed, 'CS101 DATA STRUCTURES\nUNIT I FUNDAMENTALS\nBinary trees and graph traversal.')
        self.assertEqual(audit['status'], 'review_required')
        self.assertTrue(any(issue['field'] == 'units[1].text' for issue in audit['issues']))

    def test_docx_tables_and_unicode_text_are_local(self):
        path = self.root / 'source.docx'
        paragraphs = course().splitlines()
        xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        xml += ''.join('<w:p><w:r><w:t>' + escape(line) + '</w:t></w:r></w:p>' for line in paragraphs)
        xml += '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>தமிழ் — résumé</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('word/document.xml', xml)
        with patch('urllib.request.urlopen', side_effect=AssertionError('Offline path attempted a network call')):
            reader = sylex.PDFReader(str(path))
            result = sylex.run_task2(str(path), 'CS101')
        self.assertIn('தமிழ்', reader.full_text())
        self.assertEqual(reader.pages[0].tables[0][0][0], 'தமிழ் — résumé')
        self.assertEqual(result['_source']['format'], 'docx')
        self.assertTrue(result['units'])

    def test_title_only_markdown_retains_uncoded_identity(self):
        path = self.root / 'source.md'
        path.write_text('# Course Title: Introduction to Ecology\nCourse Objectives:\nUnderstand ecology.\n## WEEK 1 ECOSYSTEMS\nHabitats and biodiversity.\n## WEEK 2 POPULATIONS\nPopulation dynamics.', encoding='utf-8')
        catalog = sylex.run_task1(str(path))
        self.assertEqual(catalog['courses'][0]['code'], '')
        result = sylex.run_task2(str(path), 'Introduction to Ecology')
        self.assertEqual(result['course']['code'], '')
        self.assertEqual(len(result['units']), 2)

    def test_references_to_units_in_body_do_not_create_headings(self):
        path = self.pdf([course(topic='Apply concepts from unit 3 when analysing trees.')])
        self.assertEqual(len(sylex.run_task2(path, 'CS101')['units']), 1)

    def test_two_column_pdf_keeps_independent_units_in_reading_order(self):
        path = self.root / 'columns.pdf'
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((40, 40), 'CS101 ECOLOGY\nCOURSE OBJECTIVES: Study ecosystems.', fontsize=10)
            page.insert_text((40, 100), 'UNIT I FORESTS 4 hours\nForest habitats.\nNative trees.\nForest biodiversity.', fontsize=11)
            page.insert_text((330, 100), 'UNIT II POPULATIONS 3 hours\nPopulation dynamics.\nMigration and growth.\nPopulation statistics.', fontsize=11)
            doc.save(path)
        result = sylex.run_task2(str(path), 'CS101')
        self.assertEqual(result['_source']['pages'][0]['layout'], 'two_columns')
        self.assertEqual([u['number'] for u in result['units']], [1, 2])
        self.assertIn('Forest biodiversity', result['units'][0]['text'])
        self.assertNotIn('Population dynamics', result['units'][0]['text'])
        self.assertIn('Population statistics', result['units'][1]['text'])

    def test_unstructured_content_is_flagged_for_review(self):
        path = self.pdf(['Course Code: CS101\nCourse Title: DATA STRUCTURES\nCOURSE OBJECTIVES:\nStudy binary trees and traversal algorithms with graph techniques.'])
        result = sylex.run_task2(path, 'CS101')
        self.assertTrue(any('unstructured' in warning for warning in result['not_extracted']))
        self.assertEqual(result['_quality']['status'], 'review_required')

    def test_cache_survives_a_new_reader_and_can_be_cleared(self):
        path = self.pdf([course()])
        first = sylex.PDFReader(path)
        with patch.object(sylex.PDFReader, '_load_fitz', side_effect=AssertionError('Cache missed')):
            second = sylex.PDFReader(path)
        self.assertEqual(first.full_text(), second.full_text())
        offline_cache.clear()
        self.assertIsNone(offline_cache.get(offline_cache.cache_key(first._sha)))

    def test_blank_and_password_protected_documents_are_honest(self):
        blank = self.pdf([''])
        result = sylex.run_task1(blank)
        self.assertEqual(result['course_count'], 0)
        self.assertEqual(result['_source']['review_pages'], [1])
        path = self.root / 'locked.pdf'
        with fitz.open() as doc:
            doc.new_page()
            doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='user')
        with self.assertRaises(sylex.PDFReadError):
            sylex.run_task1(str(path))

    @unittest.skipUnless(document_ingest.ocr_capabilities()['available'], 'Local Tesseract unavailable')
    def test_real_scanned_pdf_and_image_use_local_ocr(self):
        text_pdf = self.pdf([course()])
        image_path = self.root / 'source.png'
        with fitz.open(text_pdf) as doc:
            doc[0].get_pixmap(matrix=fitz.Matrix(2, 2)).save(image_path)
        scan_path = self.root / 'scanned.pdf'
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_image(page.rect, filename=str(image_path))
            doc.save(scan_path)
        with patch('urllib.request.urlopen', side_effect=AssertionError('OCR must stay offline')):
            for path in [scan_path, image_path]:
                with self.subTest(path=path.suffix):
                    result = sylex.run_task2(str(path), 'CS101')
                    self.assertIsNotNone(result['course'], result)
                    self.assertIn('Binary trees', json.dumps(result['units']))
                    self.assertEqual(result['_source']['ocr_pages'], [1])

    def test_missing_ocr_reports_gap_instead_of_success(self):
        image_path = self.root / 'scan.pdf'
        with fitz.open() as doc:
            page = doc.new_page()
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100))
            pix.clear_with(255)
            page.insert_image(page.rect, pixmap=pix)
            doc.save(image_path)
        with patch.object(document_ingest, 'ocr_capabilities', return_value={'available': False}):
            result = sylex.run_task1(str(image_path))
        self.assertEqual(result['course_count'], 0)
        self.assertTrue(any('OCR unavailable' in warning for warning in result['_source']['warnings']))


if __name__ == '__main__':
    unittest.main()
