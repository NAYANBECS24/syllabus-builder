"""Output expectations for materially different document layouts and audit failures."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf as fitz
import sylex
from online_pipeline import run as online_run
from tests.test_online_pipeline import FakeCloud


class LayoutVariationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'SYLEX_CACHE_DIR': 'off'})
        self.env.start()
        sylex._GLOBAL_COURSE_DETECTOR_CACHE.clear()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def source(self, text):
        path = self.root / 'syllabus.txt'
        path.write_text(text, encoding='utf-8')
        return str(path)

    def detail(self, body):
        return sylex.run_task2(self.source('CS101 DATA STRUCTURES\n' + body), 'CS101')

    def table_pdf(self, tables):
        path = self.root / 'tables.pdf'
        with fitz.open() as document:
            for header, rows in tables:
                page = document.new_page(width=720, height=720)
                page.insert_text((30, 35), header, fontsize=11)
                widths = [75] + [510 / (len(rows[0]) - 1)] * (len(rows[0]) - 1)
                x = [30]
                for width in widths:
                    x.append(x[-1] + width)
                y0, height = 85, 65
                for ri, row in enumerate(rows):
                    for ci, cell in enumerate(row):
                        rect = fitz.Rect(x[ci], y0 + ri * height, x[ci + 1], y0 + (ri + 1) * height)
                        page.draw_rect(rect)
                        fit = page.insert_textbox(rect + (4, 5, -4, -5), cell, fontsize=9)
                        self.assertGreaterEqual(fit, 0, cell)
            document.save(path)
        return str(path)

    def test_last_course_outcome_at_end_of_file_is_retained(self):
        result = self.detail('UNIT I TREES\nBinary trees.\nCourse Outcomes:\nCO1 Explain binary trees. K2\nCO2 Implement traversal. K3')
        self.assertEqual([x['id'] for x in result['course_outcomes']], ['CO1', 'CO2'])
        self.assertEqual(result['course_outcomes'][-1]['text'], 'Implement traversal')
        self.assertEqual(result['_audit']['status'], 'verified', result['_audit'])

    def test_objectives_are_not_relabelled_as_outcomes(self):
        result = self.detail('Course Objectives:\n1. Introduce basic data types.\n2. Introduce trees.\nUNIT I TREES\nBinary trees and traversal.')
        self.assertEqual(result['course_outcomes'], [])

    def test_outcomes_before_modules_do_not_absorb_the_syllabus(self):
        result = self.detail('Learning Outcomes:\n1. Explain binary trees.\n2. Implement traversal.\nMODULE 1 TREES\nBinary trees and traversal.')
        self.assertEqual(len(result['course_outcomes']), 2)
        self.assertNotIn('MODULE', result['course_outcomes'][-1]['text'])

    def test_narrative_unit_references_preserve_all_body_text(self):
        result = self.detail('UNIT I TREES\nReferences to unit 3 are useful when studying binary trees.\nPractice tree traversal.\nUNIT II GRAPHS\nGraph traversal.')
        self.assertIn('References to unit 3', result['units'][0]['text'])
        self.assertIn('Practice tree traversal', result['units'][0]['text'])

    def test_sentence_case_and_non_latin_unit_titles(self):
        for title in ['Introduction to trees', 'அடிப்படை மரங்கள்', '树和图']:
            with self.subTest(title=title):
                result = self.detail(f'UNIT 1 {title}\nBinary trees and traversal.')
                self.assertEqual(result['units'][0]['title'], title)
                self.assertEqual(result['units'][0]['text'], 'Binary trees and traversal.')

    def test_numbered_outline_under_content_heading(self):
        result = self.detail('Course Content:\n1. Introduction to trees\nBinary trees and traversal.\n2. Graph algorithms\nBreadth first search.\nReferences:\n1. Author, Graphs, Publisher, 2024.')
        self.assertEqual([u['number'] for u in result['units']], [1, 2])
        self.assertEqual([u['title'] for u in result['units']], ['Introduction to trees', 'Graph algorithms'])
        self.assertNotIn('Author', result['units'][-1]['text'])

    def test_table_units_stitch_pages_and_blank_continuation_rows(self):
        path = self.table_pdf([
            ('CS101 DATA STRUCTURES\nCOURSE CONTENT', [
                ['Module', 'Title', 'Topics', 'Hours'],
                ['I', 'Trees', 'Binary trees and traversal.', '2.5'],
                ['', '', 'Balanced trees and rotations.', ''],
            ]),
            ('COURSE CONTENT (continued)', [
                ['Module', 'Title', 'Topics', 'Hours'],
                ['II', 'Graphs', 'Graph search algorithms.', '4'],
                ['Total', '', '', '6.5'],
            ]),
        ])
        result = sylex.run_task2(path, 'CS101')
        self.assertEqual([u['number'] for u in result['units']], [1, 2], result['units'])
        self.assertEqual([u['hours'] for u in result['units']], [2.5, 4])
        self.assertIn('Balanced trees', result['units'][0]['text'])

    def test_ltpc_table_uses_labels_not_column_positions(self):
        path = self.table_pdf([('CS101 DATA STRUCTURES', [
            ['Credits', 'P', 'L', 'T'], ['2.5', '2', '1.5', '0'],
        ])])
        result = sylex.run_task2(path, 'CS101')
        self.assertEqual([result['course'][key] for key in ['lecture', 'tutorial', 'practical', 'credits']], [1.5, 0, 2, 2.5])

    def test_arbitrary_numbers_are_not_inferred_as_workload(self):
        result = self.detail('UNIT I TREES\nExplore 1 2 3 4 as keys in binary trees.')
        self.assertIsNone(result['course']['lecture'])
        self.assertIsNone(result['course']['credits'])

    def test_matrices_stitch_all_pages(self):
        path = self.table_pdf([
            ('CS101 DATA STRUCTURES\nCO-PO Mapping', [['CO', 'PO1', 'PO2'], ['CO1', '3', '2']]),
            ('CO-PO Mapping continued', [['CO', 'PO1', 'PO2'], ['CO2', '-', '1']]),
        ])
        result = sylex.run_task2(path, 'CS101')
        self.assertEqual(result['co_po_matrix'], {'CO1': {'PO1': '3', 'PO2': '2'}, 'CO2': {'PO2': '1'}})

    def test_parenthesized_course_headers_on_shared_page_are_isolated(self):
        path = self.source('DATA STRUCTURES (CS101)\nCourse Objectives:\nStudy structures.\nUNIT I TREES\nBinary trees.\nDATABASE SYSTEMS (CS102)\nCourse Objectives:\nStudy databases.\nUNIT I RELATIONS\nRelational algebra.')
        first = sylex.run_task2(path, 'CS101')
        second = sylex.run_task2(path, 'CS102')
        self.assertEqual(len(first['units']), 1)
        self.assertEqual(len(second['units']), 1)
        self.assertNotIn('Relational algebra', first['units'][0]['text'])
        self.assertNotIn('Binary trees', second['units'][0]['text'])

    def test_audit_understands_short_identifiers_unicode_and_word_boundaries(self):
        self.assertTrue(sylex._has_source_evidence('CO1', 'CO1 Explain trees'))
        self.assertFalse(sylex._has_source_evidence('CO1', 'CO10 Explain trees'))
        self.assertTrue(sylex._has_source_evidence('树和图', 'UNIT 1 树和图'))
        self.assertFalse(sylex._has_source_evidence('trees', 'streetrees'))

    def test_audit_flags_dropped_unit_and_topic_coverage(self):
        text = 'CS101 DATA STRUCTURES\nUNIT I TREES\nBinary trees; balancing rotations.\nUNIT II GRAPHS\nGraph traversal.'
        result = sylex.run_task2(self.source(text), 'CS101')
        result['units'] = result['units'][:1]
        result['units'][0]['topics'] = [{'text': 'Binary trees'}]
        audit = sylex.audit_extraction_output(result, text)
        reasons = {issue['reason'] for issue in audit['issues']}
        self.assertIn('source_unit_missing_from_output', reasons)
        self.assertIn('unit_body_not_covered_by_topics', reasons)

    def test_empty_catalog_is_not_verified(self):
        self.assertEqual(sylex.audit_catalog_output([], '')['status'], 'review_required')

    def test_online_audit_does_not_use_neighbor_course_as_evidence(self):
        path = self.source('CS101 DATA STRUCTURES\nUNIT I TREES\nBinary trees.\nCS102 DATABASES\nCourse Objectives:\nStudy data.\nUNIT I RELATIONS\nRelational algebra.')
        import online_pipeline
        original = online_pipeline.merge_detail
        def corrupt(*args):
            result = original(*args)
            result['units'][0]['text'] = 'Relational algebra.'
            result['units'][0]['topics'] = [{'text': 'Relational algebra.'}]
            return result
        with patch.object(online_pipeline, 'merge_detail', side_effect=corrupt):
            result = online_run(path, 'CS101', {}, FakeCloud())
        self.assertTrue(any(i['field'] == 'units[1].text' for i in result['_audit']['issues']), result['_audit'])


if __name__ == '__main__':
    unittest.main()
