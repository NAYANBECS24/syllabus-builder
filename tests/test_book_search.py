"""Regression tests for evidence-weighted Book Explorer search."""

import unittest

import sylex_server


class BookSearchTests(unittest.TestCase):
    def setUp(self):
        self.handler = object.__new__(sylex_server.Handler)
        self.pages = [
            {
                "page": 1,
                "text": "A binary search tree stores ordered keys. This chapter introduces the binary search tree.",
            },
            {
                "page": 2,
                "text": "Tree traversal visits nodes using preorder, inorder, or postorder algorithms.",
            },
            {
                "page": 3,
                "text": "Search methods are useful for information retrieval and indexing.",
            },
            {"page": 4, "text": "Education policy and curriculum design."},
        ]
        self.outline = [
            {"page": 1, "kind": "Chapter", "label": "Chapter 7", "title": "Binary Search Trees"},
            {"page": 2, "kind": "Section", "label": "Section 7.2", "title": "Tree Traversal"},
        ]

    def test_query_terms_remove_common_words(self):
        self.assertEqual(
            self.handler._book_query_terms("The Introduction to Binary Trees"),
            ["introduction", "binary", "trees"],
        )

    def test_balanced_mode_ranks_exact_phrase_first(self):
        results, total = self.handler._search_book_pages(
            self.pages, "binary search tree", self.outline, "balanced"
        )

        self.assertEqual(total, 1)
        self.assertEqual(results[0]["page"], 1)
        self.assertTrue(results[0]["exact_match"])
        self.assertEqual(results[0]["match_type"], "Exact phrase")
        self.assertEqual(results[0]["term_coverage"], 100)
        self.assertGreaterEqual(results[0]["relevance"], 90)

    def test_exact_mode_excludes_pages_with_separated_terms(self):
        results, total = self.handler._search_book_pages(
            self.pages, "tree algorithms", self.outline, "exact"
        )

        self.assertEqual(total, 0)
        self.assertEqual(results, [])

    def test_broad_mode_finds_partial_concept_matches(self):
        results, total = self.handler._search_book_pages(
            self.pages, "retrieval algorithm", self.outline, "broad"
        )

        self.assertGreaterEqual(total, 2)
        self.assertTrue(any(result["term_coverage"] == 50 for result in results))
        self.assertTrue(all(result["match_type"] == "Related concept" for result in results))

    def test_term_matching_respects_word_boundaries(self):
        results, total = self.handler._search_book_pages(
            self.pages, "cat", self.outline, "broad"
        )

        self.assertEqual(total, 0)
        self.assertEqual(results, [])

    def test_section_context_is_attached_to_results(self):
        results, _ = self.handler._search_book_pages(
            self.pages, "tree traversal", self.outline, "balanced"
        )

        self.assertEqual(results[0]["page"], 2)
        self.assertEqual(results[0]["section"], "Chapter 7 · Binary Search Trees")

    def test_multipart_parser_accepts_research_mode(self):
        boundary = "sylex-test-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="query"\r\n\r\n'
            "binary search tree\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="mode"\r\n\r\n'
            "broad\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="book"; filename="algorithms.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode() + b"%PDF-test\r\n" + f"--{boundary}--\r\n".encode()

        pdf, filename, query, mode = self.handler._parse_book_search_multipart(
            f"multipart/form-data; boundary={boundary}", body
        )

        self.assertEqual(pdf, b"%PDF-test")
        self.assertEqual(filename, "algorithms.pdf")
        self.assertEqual(query, "binary search tree")
        self.assertEqual(mode, "broad")


if __name__ == "__main__":
    unittest.main()
