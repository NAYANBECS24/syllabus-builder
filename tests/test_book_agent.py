"""Book research agent tests: local grounding, syllabus alignment and privacy."""
import unittest

from book_agent import build_report
import sylex_server


class BookAgentTests(unittest.TestCase):
    def setUp(self):
        self.handler = object.__new__(sylex_server.Handler)
        self.pages = [
            {"page": 1, "text": "Binary trees store ordered keys. Tree traversal uses inorder and preorder."},
            {"page": 2, "text": "Graph traversal uses breadth first search and depth first search."},
            {"page": 3, "text": "Sorting algorithms include merge sort and quick sort."},
        ]
        self.outline = [
            {"page": 1, "kind": "Chapter", "label": "Chapter 1", "title": "Trees"},
            {"page": 2, "kind": "Chapter", "label": "Chapter 2", "title": "Graphs"},
        ]

    def report(self, query, context=None):
        primary, _ = self.handler._search_book_pages(self.pages, query, self.outline, "balanced")
        return build_report(
            self.pages, self.outline, query, "balanced", primary,
            self.handler._search_book_pages, context,
        )

    def test_reading_path_is_backed_by_page_excerpts(self):
        report = self.report("binary trees")
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["reading_path"][0]["page"], 1)
        self.assertIn("Binary trees", report["reading_path"][0]["evidence"])
        self.assertEqual(report["engine"], "local-evidence-agent")

    def test_syllabus_alignment_reports_covered_topics_and_gaps(self):
        context = {"task2": {
            "course": {"code": "CS101", "title": "DATA STRUCTURES"},
            "units": [{"number": 1, "title": "Structures", "topics": [
                {"text": "binary trees"}, {"text": "graph traversal"},
                {"text": "dynamic programming"},
            ]}],
        }}
        report = self.report("tree traversal", context)
        alignment = report["syllabus_alignment"]
        self.assertEqual(alignment["topics_checked"], 3)
        self.assertEqual(alignment["topics_covered"], 2)
        self.assertEqual(alignment["coverage_percent"], 67)
        self.assertEqual(alignment["gaps"][0]["text"], "dynamic programming")
        self.assertEqual(report["course"]["code"], "CS101")

    def test_no_context_stays_useful_and_does_not_claim_coverage(self):
        report = self.report("sorting algorithms")
        self.assertFalse(report["syllabus_alignment"]["available"])
        self.assertIsNone(report["syllabus_alignment"]["coverage_percent"])
        self.assertFalse(report["online"]["requested"])
        self.assertTrue(report["reading_path"])

    def test_catalog_identity_uses_metadata_without_page_text(self):
        identity = self.handler._book_agent_identity({"metadata": {
            "title": "Introduction to Algorithms",
            "author": "Thomas H. Cormen",
            "isbn_candidates": ["978-0-262-04630-5"],
        }}, "ignored.pdf")
        self.assertEqual(identity, {
            "title": "Introduction to Algorithms",
            "author": "Thomas H. Cormen",
            "isbn": "9780262046305",
        })


if __name__ == "__main__":
    unittest.main()
