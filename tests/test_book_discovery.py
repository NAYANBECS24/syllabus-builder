"""Focused, offline regression tests for the Book Finder catalog pipeline."""

import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

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

    def test_same_provider_variants_are_not_false_catalog_agreement(self):
        first = self.record(id="gutenberg:1", identifiers=[], year="")
        second = self.record(id="gutenberg:2", identifiers=[], year="")
        first["sources"] = [{"name": "Project Gutenberg", "url": "https://www.gutenberg.org/ebooks/1"}]
        second["sources"] = [{"name": "Project Gutenberg", "url": "https://www.gutenberg.org/ebooks/2"}]

        merged = self.handler._merge_catalog_records(
            [first, second], "Introduction to Algorithms", "Thomas H. Cormen"
        )

        self.assertEqual(len(merged), 2)

    def test_same_title_and_year_with_different_publishers_remain_distinct(self):
        first = self.record(identifiers=[], publisher="First Press")
        second = self.record(
            id="provider:2",
            identifiers=[],
            publisher="Second Press",
            sources=[{"name": "Second catalog", "url": "https://example.test/second"}],
        )

        merged = self.handler._merge_catalog_records(
            [first, second], "Introduction to Algorithms", "Thomas H. Cormen"
        )

        self.assertEqual(len(merged), 2)

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

    def test_project_gutenberg_exposes_public_epub_download(self):
        search_feed = ET.fromstring("""
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry>
                <title>Pride and Prejudice</title>
                <link rel="subsection" href="/ebooks/1342.opds" />
              </entry>
            </feed>
        """)
        detail_feed = ET.fromstring("""
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry>
                <id>urn:gutenberg:1342:2</id>
                <title>Pride and Prejudice</title>
                <rights>Public domain in the USA.</rights>
                <author><name>Austen, Jane</name></author>
                <link rel="http://opds-spec.org/acquisition" type="application/epub+zip"
                      title="EPUB" href="https://www.gutenberg.org/ebooks/1342.epub.noimages" />
              </entry>
            </feed>
        """)
        with patch.object(
            self.handler,
            "_catalog_xml_request",
            side_effect=[search_feed, detail_feed],
        ):
            records, total = self.handler._search_project_gutenberg_catalog(
                "Pride and Prejudice", "Jane Austen"
            )

        self.assertEqual(total, 1)
        self.assertEqual(records[0]["authors"], ["Jane Austen"])
        self.assertEqual(records[0]["availability"], "Public-domain EPUB")
        self.assertEqual(records[0]["downloads"][0]["format"], "EPUB")

    def test_doab_exposes_open_access_pdf(self):
        response = [{
            "uuid": "doab-test-id",
            "handle": "20.500.12854/12345",
            "name": "Open Research Methods",
            "metadata": [
                {"key": "dc.title", "value": "Open Research Methods"},
                {"key": "dc.contributor.author", "value": "Ada Lovelace"},
                {"key": "dc.date.issued", "value": "2025"},
                {"key": "dc.publisher", "value": "Open Academic Press"},
                {"key": "dc.identifier.isbn", "value": "9780262046305"},
                {"key": "dc.relation", "value": "https://books.example.org/open-research.pdf"},
                {"key": "dc.rights", "value": "CC BY 4.0"},
            ],
            "bitstreams": [],
        }]
        with patch.object(self.handler, "_catalog_json_value_request", return_value=response):
            records, total = self.handler._search_doab_catalog(
                "Open Research Methods", "Ada Lovelace"
            )

        self.assertEqual(total, 1)
        self.assertEqual(records[0]["availability"], "Open-access PDF")
        self.assertEqual(records[0]["download_url"], "https://books.example.org/open-research.pdf")
        self.assertEqual(records[0]["downloads"][0]["format"], "PDF")

    def test_missing_google_key_is_reported_as_setup_required(self):
        empty = ([], 0)
        with patch.object(sylex_server, "DEFAULT_GOOGLE_BOOKS_API_KEY", ""), patch.object(
            self.handler, "_search_open_library_catalog", return_value=empty
        ), patch.object(
            self.handler, "_search_internet_archive_catalog", return_value=empty
        ), patch.object(
            self.handler, "_search_project_gutenberg_catalog", return_value=empty
        ), patch.object(
            self.handler, "_search_doab_catalog", return_value=empty
        ), patch.object(
            self.handler, "_search_crossref_catalog", return_value=empty
        ):
            payload = self.handler._discover_catalog_books("Provider Setup Probe", "")

        google = next(item for item in payload["providers"] if item["name"] == "Google Books")
        self.assertEqual(google["status"], "configuration_required")
        self.assertEqual(payload["configuration"]["google_books"]["state"], "required")

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

    def test_encrypted_archive_loan_pdf_is_not_exposed(self):
        metadata = {
            "metadata": {"access-restricted": "false"},
            "files": [{"name": "loan_encrypted.pdf", "format": "Encrypted PDF"}],
        }
        with patch.object(self.handler, "_catalog_json_request", return_value=metadata):
            download_url = self.handler._archive_pdf_download_url("loan-book")

        self.assertEqual(download_url, "")

    def test_archive_access_verification_does_not_duplicate_provider_evidence(self):
        record = self.record(
            archive_identifier="public-book",
            sources=[{"name": "Internet Archive", "url": "https://archive.org/details/public-book"}],
        )
        with patch.object(
            self.handler,
            "_archive_pdf_download_url",
            return_value="https://archive.org/download/public-book/public-book_text.pdf",
        ):
            self.handler._add_archive_pdf_links([record])

        self.assertEqual([source["name"] for source in record["sources"]], ["Internet Archive"])
        self.assertEqual(record["availability"], "Free PDF")


if __name__ == "__main__":
    unittest.main()
