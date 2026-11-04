"""No-network regressions for grounded cloud proposals, coverage and vision."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf as fitz
from cloud_models import CloudModels, CloudError, parse_object
import online_pipeline as pipeline
import sylex


class FakeCloud:
    available = True
    def __init__(self, response=None):
        self.response = response or (lambda *_: {'courses': []})
        self.calls = []
    def complete(self, system, prompt, timeout, image_bytes=None):
        self.calls.append({'prompt': prompt, 'timeout': timeout, 'image': image_bytes is not None})
        return self.response(prompt, image_bytes), 'fixture-model'


def fixture(code='CS101', body='UNIT I TREES 9 hours\nBinary trees and traversal.'):
    return f'{code} DATA STRUCTURES\nCOURSE OBJECTIVES:\nUnderstand the printed topics.\n{body}\nCOURSE OUTCOMES:\nCO1 Explain tree traversal. K2'


class OnlinePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'SYLEX_CACHE_DIR': 'off'})
        self.env.start()
        self.network = patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected network access'))
        self.network.start()
    def tearDown(self):
        self.network.stop()
        self.env.stop()
        self.temp.cleanup()
    def source(self, text, name='syllabus.txt'):
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        return str(path)
    def test_online_catalog_recovers_a_source_backed_short_course_code(self):
        text = fixture('CS50')
        path = self.source(text)
        cloud = FakeCloud(lambda *_: {'courses': [{'code': 'CS50', 'title': 'DATA STRUCTURES', 'page': 1, 'quote': 'CS50 DATA STRUCTURES'}]})
        result = pipeline.run(path, None, {}, cloud)
        self.assertIn('CS50', [c['code'] for c in result['courses']])
        self.assertEqual(result['_processing']['used_mode'], 'online')
        self.assertEqual(result['_online']['reviewed_pages'], [1])
    def test_detail_recovers_a_course_the_local_detector_missed(self):
        path = self.source(fixture('CS50'))
        cloud = FakeCloud(lambda *_: {'courses': [{'code': 'CS50', 'title': 'DATA STRUCTURES', 'page': 1, 'quote': 'CS50 DATA STRUCTURES'}]})
        result = pipeline.run(path, 'CS50', {}, cloud)
        self.assertEqual(result['course']['code'], 'CS50')
        self.assertTrue(result['units'])
    def test_empty_local_catalog_does_not_prevent_cloud_review(self):
        path = self.source('SYLLABUS\nCourse Q1 — Ecology\nHabitats and biodiversity.')
        cloud = FakeCloud(lambda *_: {'courses': [{'code': 'Q1', 'title': 'Ecology', 'page': 1, 'quote': 'Course Q1 — Ecology'}]})
        result = pipeline.run(path, None, {}, cloud)
        self.assertEqual(result['courses'][0]['code'], 'Q1')
    def test_fabricated_titles_credits_quotes_and_pages_are_rejected(self):
        path = self.source(fixture())
        cloud = FakeCloud(lambda *_: {
            'courses': [{'code': 'FAKE999', 'title': 'Invented Course', 'page': 1, 'quote': 'CS101 DATA STRUCTURES'}],
            'metadata': [{'field': 'credits', 'value': 99, 'page': 1, 'quote': 'UNIT I TREES 9 hours'}],
            'units': [{'number': 8, 'title': 'Imaginary', 'text': 'Fake content', 'page': 300, 'quote': 'Fake content'}],
            'course_outcomes': [{'id': 'CO9', 'text': 'Invent a topic', 'page': 1, 'quote': 'No such source quote'}]})
        result = pipeline.run(path, 'CS101', {}, cloud)
        self.assertGreaterEqual(result['_online']['rejected_proposals'], 4)
        self.assertNotEqual(result['course']['credits'], 99)
        self.assertNotIn('Imaginary', json.dumps(result['units']))
    def test_model_cannot_overwrite_known_metadata(self):
        baseline = {'course': {'code': 'CS101', 'credits': 3}, 'units': [], 'course_outcomes': [], 'programme_outcomes': [], 'books': []}
        audit = {'accepted': 0, 'rejected': 0, 'conflicts': 0, 'evidence': []}
        result = pipeline.merge_detail(baseline, {'metadata': [{'field': 'credits', 'value': 4, 'page': 1, 'quote': 'Credits: 4'}]}, {1: 'Credits: 4'}, audit)
        self.assertEqual(result['course']['credits'], 3)
        self.assertEqual(audit['conflicts'], 1)
    def test_unit_recovery_uses_verbatim_text_and_marks_bloom_as_inferred(self):
        baseline = {'course': {'code': 'CS101'}, 'units': [], 'course_outcomes': [], 'programme_outcomes': [], 'books': []}
        quote = 'TOPIC 7 BIODIVERSITY 3 hours\nExplain forest habitats.'
        item = {'number': 7, 'title': 'BIODIVERSITY', 'text': 'Explain forest habitats.', 'hours': 3, 'page': 2, 'quote': quote, 'bloom': 'create', 'bloom_source': 'printed'}
        audit = {'accepted': 0, 'rejected': 0, 'conflicts': 0, 'evidence': []}
        result = pipeline.merge_detail(baseline, {'units': [item]}, {2: quote}, audit)
        self.assertEqual(result['units'][0]['hours'], 3)
        self.assertEqual(result['units'][0]['topics'][0]['bloom_source'], 'inferred')
    def test_prose_does_not_support_invented_unit_number(self):
        baseline = {'course': {'code': 'CS101'}, 'units': [], 'course_outcomes': [], 'programme_outcomes': [], 'books': []}
        quote = 'Trees\nBinary trees and traversal.'
        audit = {'accepted': 0, 'rejected': 0, 'conflicts': 0, 'evidence': []}
        result = pipeline.merge_detail(baseline, {'units': [{'number': 7, 'title': 'Trees', 'text': 'Binary trees and traversal.', 'page': 1, 'quote': quote}]}, {1: quote}, audit)
        self.assertFalse(result['units'])
        self.assertEqual(audit['rejected'], 1)
    def test_cross_course_cloud_proposals_cannot_escape_header_scope(self):
        path = self.source(fixture() + '\nCS102 DATABASES\nCOURSE OBJECTIVES:\nStudy data.\nUNIT I RELATIONS\nRelational algebra.')
        cloud = FakeCloud(lambda *_: {'units': [{'number': 1, 'title': 'RELATIONS', 'text': 'Relational algebra.', 'page': 1, 'quote': 'UNIT I RELATIONS\nRelational algebra.'}]})
        result = pipeline.run(path, 'CS101', {}, cloud)
        self.assertNotIn('Relational algebra', json.dumps(result['units']))
        self.assertGreater(result['_online']['rejected_proposals'], 0)
    def test_all_cloud_failures_preserve_local_result(self):
        path = self.source(fixture())
        def fail(*_): raise CloudError('Provider unavailable')
        result = pipeline.run(path, 'CS101', {}, FakeCloud(fail))
        self.assertEqual(result['course']['code'], 'CS101')
        self.assertTrue(result['units'])
        self.assertTrue(result['_processing']['fallback'])
        self.assertEqual(result['_online']['unreviewed_pages'], [1])
    def test_bad_model_schema_is_not_claimed_as_success(self):
        path = self.source(fixture())
        result = pipeline.run(path, None, {}, FakeCloud(lambda *_: {'units': 'not an array'}))
        self.assertEqual(result['_online']['status'], 'fallback')
        self.assertTrue(result['courses'])
    def test_budget_limit_reports_unreviewed_tail_instead_of_silent_truncation(self):
        path = self.source('\f'.join(fixture(f'CS10{i}') + '\n' + ('Supplementary printed notes. ' * 450) for i in range(8)))
        result = pipeline.run(path, None, {}, FakeCloud())
        self.assertLessEqual(result['_online']['requests_attempted'], pipeline.MAX_CHUNKS)
        self.assertTrue(result['_online']['unreviewed_pages'])
        self.assertGreater(result['_online']['chunks_planned'], result['_online']['chunks_completed'])
    def test_no_credentials_and_zero_budget_make_no_cloud_calls(self):
        path = self.source(fixture())
        cloud = FakeCloud()
        result = pipeline.run(path, None, {}, cloud, budget=0)
        self.assertFalse(cloud.calls)
        self.assertTrue(result['_processing']['fallback'])
        cloud.available = False
        pipeline.run(path, None, {}, cloud)
        self.assertFalse(cloud.calls)

    def test_page_window_reviews_tail_and_preserves_catalog_from_previous_pass(self):
        path = self.source(fixture() + '\f' + 'Q1 ECOLOGY\nCOURSE OBJECTIVES:\nUnderstand ecosystems.\nUNIT I HABITATS\nForest habitats.')
        cloud = FakeCloud(lambda *_: {'courses': [{'code': 'Q1', 'title': 'ECOLOGY', 'page': 2, 'quote': 'Q1 ECOLOGY'}]})
        result = pipeline.run(path, None, {'online_review': {'start_page': 2, 'end_page': 2}, 'courses': [{'code': 'CS101', 'title': 'DATA STRUCTURES', 'page': 1}]}, cloud)
        self.assertEqual(result['_online']['reviewed_pages'], [2])
        self.assertEqual(result['_online']['outside_review_pages'], [1])
        self.assertEqual({c['code'] for c in result['courses']}, {'CS101', 'Q1'})
        self.assertEqual([p['page'] for p in json.loads(cloud.calls[0]['prompt'])['source_pages']], [2])

    def test_topic_proposals_cannot_drop_source_body_from_study_plans(self):
        baseline = {'course': {'code': 'CS101'}, 'units': [], 'course_outcomes': [], 'programme_outcomes': [], 'books': []}
        text = 'Trees; graphs; sorting.'
        quote = 'UNIT I ALGORITHMS\n' + text
        audit = {'accepted': 0, 'rejected': 0, 'conflicts': 0, 'evidence': []}
        result = pipeline.merge_detail(baseline, {'units': [{'number': 1, 'title': 'ALGORITHMS', 'text': text, 'topics': ['Trees'], 'page': 1, 'quote': quote}]}, {1: quote}, audit)
        self.assertEqual(result['units'][0]['topics'][0]['text'], text)
    def test_cloud_vision_recovers_scan_without_local_ocr_and_stays_labelled(self):
        path = self.root / 'scan.pdf'
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((40, 50), fixture(), fontsize=12)
            image = page.get_pixmap().tobytes('png')
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_image(page.rect, stream=image)
            doc.save(path)
        cloud = FakeCloud(lambda prompt, image: {'text': fixture()} if image else {'courses': []})
        with patch('document_ingest.LocalOCR.read', return_value=(None, 'OCR unavailable')):
            result = pipeline.run(str(path), 'CS101', {}, cloud)
        self.assertEqual(result['course']['code'], 'CS101')
        self.assertEqual(result['_source']['vision_pages'], [1])
        self.assertEqual(result['_source']['review_pages'], [1])
        self.assertTrue(any(call['image'] for call in cloud.calls))
    def test_chunker_preserves_tail_and_quote_validation_preserves_page_identity(self):
        text = 'a' * 15000 + '\nUNIQUE DOCUMENT TAIL'
        planned = list(pipeline.chunks({1: text, 2: 'other page'}))
        self.assertIn('UNIQUE DOCUMENT TAIL', ''.join(p['text'] for chunk in planned for p in chunk))
        self.assertIsNone(pipeline.quote_for({'page': 2, 'quote': 'UNIQUE DOCUMENT TAIL'}, {1: text, 2: 'other page'}))


class ProviderAdapterTests(unittest.TestCase):
    def test_json_and_finish_reason_guards(self):
        self.assertEqual(parse_object('```json\n{"courses": []}\n```'), {'courses': []})
        for bad in ['{"courses": [', '[]', 'null', 'some prose']:
            with self.assertRaises(CloudError): parse_object(bad)
        response = io.BytesIO(json.dumps({'choices': [{'finish_reason': 'length', 'message': {'content': '{"courses": []}'}}]}).encode())
        with patch('cloud_models.urllib.request.urlopen', return_value=response):
            with self.assertRaisesRegex(CloudError, 'truncated'):
                CloudModels(api_key='test').complete('system', 'prompt', 1)
    def test_vision_uses_multimodal_payload_without_external_image_url(self):
        response = io.BytesIO(json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': '{"text": "source text"}'}}]}).encode())
        with patch('cloud_models.urllib.request.urlopen', return_value=response) as call:
            CloudModels(api_key='test').complete('system', 'prompt', 1, image_bytes=b'PNG fixture')
        payload = json.loads(call.call_args.args[0].data)
        self.assertEqual(payload['model'], 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning')
        self.assertTrue(payload['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,'))
        self.assertEqual(call.call_args.kwargs['timeout'], 1)


if __name__ == '__main__': unittest.main()
