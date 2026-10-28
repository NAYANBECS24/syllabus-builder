"""Focused, offline regression tests for the Book Finder catalog pipeline."""

import unittest
from unittest.mock import patch

import sylex_server


class BookDiscoveryTests(unittest.TestCase):
    def setUp(self):
        # Catalog helpers do not need a live HTTP request object.
        self.handler = object.__new__(sylex_server.Handler)

    @staticmethod
    def record(**overrides):
        base = {
            "id": "provider:1",
            "title": "Introduction to Algorithms",
            "authors": ["Thomas H. Cormen", "Charles E. Leiserson"],
            "year": "2009",
            "publisher": "MIT Press",
            "availability": "Catalog record",
            "view_url": "https://example.test/view",
            "detail_url": "https://example.test/detail",
            "download_url": "",
            "archive_identifier": "",
            "identifiers": ["9780262033848"],
            "edition_count": 1,
            "sources": [{"name": "Example", "url": "https://example.test/detail"}],
        }
        base.update(overrides)
        return base

    def test_multi_author_query_gets_exact_match(self):
        record = self.record()
        score, label, metrics = self.handler._catalog_match_score(
            record,
            "Introduction to Algorithms",
            "Thomas H. Cormen, Charles E. Leiserson",
        )

        self.assertGreater(score, 900)
        self.assertEqual(label, "Exact match")
        self.assertEqual(metrics["author"], 100)

    def test_distinct_editions_are_not_collapsed(self):
        earlier = self.record(year="2009", identifiers=["9780262033848"])
        later = self.record(
            id="provider:2",
            year="2022",
            identifiers=["9780262046305"],
            sources=[{"name": "Another catalog", "url": "https://example.test/another"}],
        )

        merged = self.handler._merge_catalog_records(
            [earlier, later], "Introduction to Algorithms", "Thomas H. Cormen"
        )

        self.assertEqual(len(merged), 2)

    def test_same_edition_merges_catalog_provenance(self):
        first = self.record()
        second = self.record(
            id="provider:2",
            sources=[{"name": "Second catalog", "url": "https://example.test/second"}],
            availability="Preview available",
        )

        merged = self.handler._merge_catalog_records(
            [first, second], "Introduction to Algorithms", "Thomas H. Cormen"
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]["sources"]), 2)

    def test_restricted_archive_items_never_offer_a_pdf(self):
        metadata = {
            "metadata": {"access-restricted": "true"},
            "files": [{"name": "book.pdf", "format": "Text PDF"}],
        }
        with patch.object(self.handler, "_catalog_json_request", return_value=metadata):
            download_url = self.handler._archive_pdf_download_url("restricted-book")

        self.assertEqual(download_url, "")

    def test_public_archive_pdf_url_escapes_the_filename(self):
        metadata = {
            "metadata": {"access-restricted": "false"},
            "files": [{"name": "nested/book_text.pdf", "format": "Text PDF"}],
        }
        with patch.object(self.handler, "_catalog_json_request", return_value=metadata):
            download_url = self.handler._archive_pdf_download_url("public-book")

        self.assertEqual(
            download_url,
            "https://archive.org/download/public-book/nested%2Fbook_text.pdf",
        )


if __name__ == "__main__":
    unittest.main()
