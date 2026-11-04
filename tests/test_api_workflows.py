"""HTTP-level checks using a generated, non-user PDF and the production handler."""
import io
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import pymupdf
import sylex_server as server


def multipart(fields, file_field=None, pdf=None):
    boundary = 'sylex-integration-boundary'
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    if file_field:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="test-syllabus.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode() + pdf + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


class APIWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.SylexHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.http.server_port}'
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((50, 50), '\n'.join([
            'TEST SYLLABUS - INTEGRATION FIXTURE',
            'CS23301 DATA STRUCTURES',
            'L T P C', '3 0 0 3',
            'OBJECTIVES:', 'To understand data structures and algorithms.',
            'UNIT I BINARY SEARCH TREES 9',
            'A binary search tree stores ordered keys. Tree traversal visits nodes.',
            'UNIT II SORTING 9', 'Sorting algorithms include merge sort and quick sort.',
            'TOTAL: 18 PERIODS', 'COURSE OUTCOMES:',
            'CO1 Explain binary search tree operations. K2',
            'CO2 Apply sorting algorithms to ordered data. K3',
            'TEXT BOOKS:', '1. Example Author, Data Structures, Test Publisher, 2024.',
        ]), fontsize=11)
        cls.pdf = document.tobytes()
        document.close()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=2)

    def request(self, path, payload=None, content_type='application/json'):
        body = json.dumps(payload).encode() if isinstance(payload, dict) else payload
        request = urllib.request.Request(self.base + path, data=body, headers={'Content-Type': content_type})
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            content = response.read()
            if 'application/json' in response.headers.get('Content-Type', ''):
                content = json.loads(content)
            return response.status, content

    def test_duplicate_listener_is_rejected(self):
        with self.assertRaises(OSError):
            server.SylexHTTPServer(self.http.server_address, server.Handler)

    def test_status_and_new_assets_are_available(self):
        status, data = self.request('/api/status')
        self.assertEqual(status, 200)
        self.assertTrue(data['capabilities']['pdf']['pymupdf'])
        for path in ['/workspace.css?v=1', '/workspace.js?v=1', '/cinematic.css?v=2']:
            self.assertEqual(self.request(path)[0], 200)
        self.assertEqual(self.request('/.env')[0], 404)

    def test_pdf_to_catalog_to_course_to_audit_and_dossier(self):
        payload, mime = multipart({'mode': 'offline'}, 'pdf', self.pdf)
        status, catalog = self.request('/api/extract', payload, mime)
        self.assertEqual(status, 200, catalog)
        self.assertTrue(any(course['code'] == 'CS23301' for course in catalog['courses']), catalog)
        payload, mime = multipart({'mode': 'offline', 'course': 'CS23301'}, 'pdf', self.pdf)
        status, course = self.request('/api/extract', payload, mime)
        self.assertEqual(status, 200, course)
        self.assertEqual(course['course']['code'], 'CS23301')
        self.assertTrue(course['units'])
        self.assertEqual(course['_processing']['used_mode'], 'offline')
        status, audit = self.request('/api/curriculum-audit', {'task2': course})
        self.assertEqual(status, 200, audit)
        self.assertEqual(audit['status'], 'ok')
        status, dossier = self.request('/api/export-dossier', {'task2': course})
        self.assertEqual(status, 200, dossier)
        self.assertIn('CS23301', dossier['html'])

    def test_book_search_and_page_preview(self):
        payload, mime = multipart({'query': 'binary search tree', 'mode': 'exact'}, 'book', self.pdf)
        status, data = self.request('/api/book-search', payload, mime)
        self.assertEqual(status, 200, data)
        self.assertGreater(data['total_matches'], 0)
        self.assertEqual(data['results'][0]['page'], 1)
        payload, mime = multipart({'page': '1'}, 'book', self.pdf)
        status, data = self.request('/api/book-page', payload, mime)
        self.assertEqual(status, 200)
        with pymupdf.open(stream=data, filetype='pdf') as document:
            self.assertEqual(len(document), 1)
            self.assertIn('binary search tree', document[0].get_text())

    def test_invalid_requests_do_not_generate_sample_results(self):
        for path in ['/api/curriculum-audit', '/api/export-dossier']:
            self.assertEqual(self.request(path, {})[0], 400)
        self.assertEqual(self.request('/api/curriculum-audit')[0], 405)
        self.assertEqual(self.request('/api/chat', {'message': 'hello', 'history': ['invalid']})[0], 400)
        self.assertEqual(self.request('/api/book-discovery', {'isbn': '9780262046306'})[0], 400)
        self.assertEqual(self.request('/api/extract', b'not a pdf', 'application/pdf')[0], 422)


class CloudReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.handler = object.__new__(server.Handler)

    def test_a_stalled_model_leaves_time_for_the_fallback(self):
        response = io.BytesIO(json.dumps({'choices': [{'message': {'content': 'connected'}}]}).encode())
        with patch.object(server.urllib.request, 'urlopen', side_effect=[TimeoutError('slow model'), response]) as call:
            content, _, model = self.handler._call_nvidia_nemotron('test', 'test', model='nvidia/nemotron-3.5-bolt-e4b', api_key='test-only', timeout=18)
        self.assertEqual(content, 'connected')
        self.assertNotEqual(model, 'nvidia/nemotron-3.5-bolt-e4b')
        self.assertLess(call.call_args_list[0].kwargs['timeout'], 13)

    def test_empty_context_is_not_replaced_with_sample_courses(self):
        with patch.object(self.handler, '_call_nvidia_nemotron', return_value=('General answer', '', 'test-model')) as call:
            self.handler._handle_chat_request('Help me plan a lesson', [], {})
        prompt = call.call_args.kwargs['system_prompt']
        self.assertIn('No syllabus is loaded', prompt)
        self.assertNotIn('Active Course: CS23301', prompt)
