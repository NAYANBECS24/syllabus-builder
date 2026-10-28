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

    def test_isbn_match_overrides_ambiguous_title_metadata(self):
        record = self.record(title="Algorithms, Fourth Edition")
        score, label, metrics = self.handler._catalog_match_score(
            record,
            "Introduction to Algorithms",
            "",
            "9780262033848",
        )

        self.assertGreater(score, 1200)
        self.assertEqual(label, "Exact ISBN")
        self.assertEqual(metrics["isbn"], 100)

    def test_invalid_isbn_checksum_is_rejected(self):
        self.assertEqual(self.handler._normalize_isbn("978-0-262-04630-6"), "")
        self.assertEqual(
            self.handler._normalize_isbn("978-0-262-04630-5"),
            "9780262046305",
        )

    def test_open_library_isbn_uses_exact_edition_metadata(self):
        work_search = {
            "numFound": 1,
            "docs": [{
                "title": "Introduction to Algorithms",
                "author_name": ["Thomas H. Cormen"],
                "isbn": ["9780262046305", "9780262033848"],
            }],
        }
        exact_edition = {
            "key": "/books/OL34192801M",
            "title": "Introduction to Algorithms, Fourth Edition",
            "publish_date": "2022",
            "publishers": ["MIT Press"],
            "isbn_13": ["9780262046305"],
            "covers": [13768952],
        }
        with patch.object(
            self.handler,
            "_catalog_json_request",
            side_effect=[work_search, exact_edition],
        ):
            records, total = self.handler._search_open_library_catalog(
                "", "", "9780262046305"
            )

        self.assertEqual(total, 1)
        self.assertEqual(records[0]["title"], "Introduction to Algorithms, Fourth Edition")
        self.assertEqual(records[0]["year"], "2022")
        self.assertEqual(records[0]["identifiers"][0], "9780262046305")

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

    def test_low_confidence_candidate_is_removed(self):
        record = self.record(title="Completely Unrelated Biology Handbook")
        merged = self.handler._merge_catalog_records(
            [record], "Introduction to Algorithms", "Thomas H. Cormen"
        )

        self.assertFalse(
            self.handler._catalog_record_relevant(
                merged[0], "Introduction to Algorithms", "Thomas H. Cormen"
            )
        )

    def test_title_overlap_does_not_override_unrelated_author(self):
        record = self.record(
            title="Introduction to Numerical Algorithms",
            authors=["Different Researcher"],
        )
        merged = self.handler._merge_catalog_records(
            [record], "Introduction to Algorithms", "Thomas H. Cormen"
        )

        self.assertFalse(
            self.handler._catalog_record_relevant(
                merged[0], "Introduction to Algorithms", "Thomas H. Cormen"
            )
        )

    def test_crossref_book_metadata_becomes_catalog_record(self):
        response = {
            "message": {
                "total-results": 1,
                "items": [{
                    "DOI": "10.1007/978-3-030-00000-0",
                    "title": ["Reliable Distributed Systems"],
                    "author": [{"given": "Ada", "family": "Lovelace"}],
                    "publisher": "Example Academic Press",
                    "published-print": {"date-parts": [[2024, 4, 1]]},
                    "type": "book",
                    "ISBN": ["9780262046305"],
                }],
            }
        }
        with patch.object(self.handler, "_catalog_json_request", return_value=response):
            records, total = self.handler._search_crossref_catalog(
                "Reliable Distributed Systems", "Ada Lovelace"
            )

        self.assertEqual(total, 1)
        self.assertEqual(records[0]["authors"], ["Ada Lovelace"])
        self.assertEqual(records[0]["year"], "2024")
        self.assertEqual(records[0]["sources"][0]["name"], "Crossref")

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
