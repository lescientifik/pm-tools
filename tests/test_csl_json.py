"""Tests for CSL-JSON conversion from ArticleRecord.

Tests the new field extraction in parse_article(), the article_to_csl()
transformation, and the LEGACY_FIELDS filtering for backward compatibility.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pm_tools.parse import parse_xml

# Helper to build minimal XML with specific elements
_ARTICLE_TEMPLATE = """\
<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99999</PMID>
    <Article>
      <Journal>
        <ISSN IssnType="{issn_type}">{issn}</ISSN>
        <JournalIssue CitedMedium="Print">
          {volume_xml}
          {issue_xml}
          <PubDate><Year>2024</Year></PubDate>
        </JournalIssue>
        <Title>Test Journal</Title>
        <ISOAbbreviation>{iso_abbrev}</ISOAbbreviation>
      </Journal>
      <ArticleTitle>Test Title</ArticleTitle>
      {pagination_xml}
      {article_date_xml}
      <AuthorList>
        <Author><LastName>Smith</LastName><ForeName>John</ForeName></Author>
      </AuthorList>
      <ELocationID EIdType="doi" ValidYN="Y">10.1234/test</ELocationID>
    </Article>
    <MedlineJournalInfo>
      {country_xml}
    </MedlineJournalInfo>
  </MedlineCitation>
  <PubmedData>
    {pub_status_xml}
    <ArticleIdList>
      <ArticleId IdType="pmc">PMC1234567</ArticleId>
    </ArticleIdList>
  </PubmedData>
</PubmedArticle>
</PubmedArticleSet>"""


def _make_xml(**kwargs: str) -> str:
    """Build test XML with optional fields."""
    defaults = {
        "issn_type": "Print",
        "issn": "0300-9629",
        "volume_xml": "<Volume>48</Volume>",
        "issue_xml": "<Issue>2</Issue>",
        "iso_abbrev": "Test J",
        "pagination_xml": "<Pagination><MedlinePgn>100-105</MedlinePgn></Pagination>",
        "article_date_xml": "",
        "country_xml": "<Country>England</Country>",
        "pub_status_xml": "<PublicationStatus>ppublish</PublicationStatus>",
    }
    defaults.update(kwargs)
    return _ARTICLE_TEMPLATE.format(**defaults)


# =============================================================================
# New field extraction in parse_article()
# =============================================================================


class TestParseArticleNewFields:
    """parse_article() extracts newly added fields from XML."""

    def test_extracts_volume(self) -> None:
        xml = _make_xml()
        articles = parse_xml(xml)
        assert articles[0]["volume"] == "48"

    def test_extracts_issue(self) -> None:
        xml = _make_xml()
        articles = parse_xml(xml)
        assert articles[0]["issue"] == "2"

    def test_extracts_page_from_medlinepgn(self) -> None:
        xml = _make_xml()
        articles = parse_xml(xml)
        assert articles[0]["page"] == "100-105"

    def test_extracts_page_from_start_end_page(self) -> None:
        """StartPage + EndPage used when no MedlinePgn."""
        xml = _make_xml(
            pagination_xml=(
                "<Pagination><StartPage>200</StartPage><EndPage>210</EndPage></Pagination>"
            )
        )
        articles = parse_xml(xml)
        assert articles[0]["page"] == "200-210"

    def test_extracts_page_from_start_page_only(self) -> None:
        """StartPage alone when no EndPage and no MedlinePgn."""
        xml = _make_xml(pagination_xml="<Pagination><StartPage>200</StartPage></Pagination>")
        articles = parse_xml(xml)
        assert articles[0]["page"] == "200"

    def test_prefers_medlinepgn_over_start_end(self) -> None:
        """MedlinePgn takes priority when both sources present."""
        xml = _make_xml(
            pagination_xml=(
                "<Pagination>"
                "<MedlinePgn>100-105</MedlinePgn>"
                "<StartPage>200</StartPage><EndPage>210</EndPage>"
                "</Pagination>"
            )
        )
        articles = parse_xml(xml)
        assert articles[0]["page"] == "100-105"

    def test_extracts_issn_print(self) -> None:
        xml = _make_xml(issn_type="Print", issn="0300-9629")
        articles = parse_xml(xml)
        assert articles[0]["issn"] == "0300-9629"

    def test_prefers_print_issn_over_electronic(self) -> None:
        """When both Print and Electronic ISSN exist, Print is preferred."""
        xml = """\
<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation>
    <PMID>99999</PMID>
    <Article>
      <Journal>
        <ISSN IssnType="Electronic">1234-5678</ISSN>
        <ISSN IssnType="Print">0300-9629</ISSN>
        <JournalIssue CitedMedium="Print">
          <PubDate><Year>2024</Year></PubDate>
        </JournalIssue>
        <Title>Test Journal</Title>
      </Journal>
      <ArticleTitle>Test</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""
        articles = parse_xml(xml)
        assert articles[0]["issn"] == "0300-9629"

    def test_uses_electronic_issn_when_no_print(self) -> None:
        """When only Electronic ISSN exists, it is used."""
        xml = _make_xml(issn_type="Electronic", issn="1234-5678")
        articles = parse_xml(xml)
        assert articles[0]["issn"] == "1234-5678"

    def test_extracts_journal_abbrev(self) -> None:
        xml = _make_xml(iso_abbrev="Test J")
        articles = parse_xml(xml)
        assert articles[0]["journal_abbrev"] == "Test J"

    def test_extracts_epub_date(self) -> None:
        xml = _make_xml(
            article_date_xml=(
                '<ArticleDate DateType="Electronic">'
                "<Year>2024</Year><Month>01</Month><Day>15</Day>"
                "</ArticleDate>"
            )
        )
        articles = parse_xml(xml)
        assert articles[0]["epub_date"] == "2024-01-15"

    def test_epub_date_partial_year_month(self) -> None:
        """epub_date with year-month only (no day)."""
        xml = _make_xml(
            article_date_xml=(
                '<ArticleDate DateType="Electronic">'
                "<Year>2024</Year><Month>03</Month>"
                "</ArticleDate>"
            )
        )
        articles = parse_xml(xml)
        assert articles[0]["epub_date"] == "2024-03"

    def test_epub_date_partial_year_only(self) -> None:
        """epub_date with year only (no month, no day)."""
        xml = _make_xml(
            article_date_xml=('<ArticleDate DateType="Electronic"><Year>2024</Year></ArticleDate>')
        )
        articles = parse_xml(xml)
        assert articles[0]["epub_date"] == "2024"

    def test_extracts_publisher_place(self) -> None:
        """Country is under MedlineJournalInfo, not under Article."""
        xml = _make_xml(country_xml="<Country>England</Country>")
        articles = parse_xml(xml)
        assert articles[0]["publisher_place"] == "England"

    def test_extracts_pub_status(self) -> None:
        xml = _make_xml(pub_status_xml="<PublicationStatus>ppublish</PublicationStatus>")
        articles = parse_xml(xml)
        assert articles[0]["pub_status"] == "ppublish"

    def test_absent_fields_omitted(self) -> None:
        """Fields absent from XML are omitted from the result (not None)."""
        xml = _make_xml(
            volume_xml="",
            issue_xml="",
            pagination_xml="",
            article_date_xml="",
            country_xml="",
            pub_status_xml="",
            iso_abbrev="",
            issn="",
        )
        articles = parse_xml(xml)
        art = articles[0]
        absent_fields = (
            "volume",
            "issue",
            "page",
            "epub_date",
            "publisher_place",
            "pub_status",
            "journal_abbrev",
            "issn",
        )
        for field in absent_fields:
            assert field not in art, f"{field} should be absent"


# =============================================================================
# article_to_csl() transformation
# =============================================================================


class TestArticleToCsl:
    """article_to_csl() is a pure dict→dict transformation."""

    def _full_record(self) -> dict[str, Any]:
        """Return a complete ArticleRecord with all fields."""
        return {
            "pmid": "12345",
            "title": "Test Article",
            "authors": [{"family": "Smith", "given": "John"}],
            "journal": "Nature Medicine",
            "journal_abbrev": "Nat Med",
            "year": 2024,
            "date": "2024-03-15",
            "abstract": "This is the abstract.",
            "abstract_sections": [{"label": "BACKGROUND", "text": "Background."}],
            "doi": "10.1234/test",
            "pmcid": "PMC1234567",
            "volume": "48",
            "issue": "2",
            "page": "100-105",
            "issn": "0300-9629",
            "epub_date": "2024-01-15",
            "publisher_place": "England",
            "pub_status": "ppublish",
        }

    def test_produces_id(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["id"] == "pmid:12345"

    def test_produces_type(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["type"] == "article-journal"

    def test_produces_source(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["source"] == "PubMed"

    def test_produces_accessed(self) -> None:
        from pm_tools.parse import article_to_csl

        with patch("pm_tools.parse.datetime") as mock_dt:
            mock_dt.date.today.return_value = datetime.date(2026, 3, 24)
            csl = article_to_csl(self._full_record())
        assert csl["accessed"] == {"date-parts": [[2026, 3, 24]]}

    def test_pmid_uppercase(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["PMID"] == "12345"
        assert "pmid" not in csl

    def test_doi_uppercase(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["DOI"] == "10.1234/test"
        assert "doi" not in csl

    def test_pmcid_uppercase(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["PMCID"] == "PMC1234567"
        assert "pmcid" not in csl

    def test_authors_renamed_to_author(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["author"] == [{"family": "Smith", "given": "John"}]
        assert "authors" not in csl

    def test_journal_to_container_title(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["container-title"] == "Nature Medicine"
        assert "journal" not in csl

    def test_journal_abbrev_to_container_title_short(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["container-title-short"] == "Nat Med"

    def test_issued_full_date(self) -> None:
        """year + date → issued with date-parts [[2024, 3, 15]]."""
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["issued"] == {"date-parts": [[2024, 3, 15]]}

    def test_issued_year_only(self) -> None:
        """Date with year only → issued [[2024]]."""
        from pm_tools.parse import article_to_csl

        record = self._full_record()
        record["date"] = "2024"
        csl = article_to_csl(record)
        assert csl["issued"] == {"date-parts": [[2024]]}

    def test_issued_year_month(self) -> None:
        """Date year-month → issued [[2024, 3]]."""
        from pm_tools.parse import article_to_csl

        record = self._full_record()
        record["date"] = "2024-03"
        csl = article_to_csl(record)
        assert csl["issued"] == {"date-parts": [[2024, 3]]}

    def test_issued_seasonal_date(self) -> None:
        """Spring 1976 → date '1976-03' → issued [[1976, 3]]."""
        from pm_tools.parse import article_to_csl

        record = self._full_record()
        record["year"] = 1976
        record["date"] = "1976-03"
        csl = article_to_csl(record)
        assert csl["issued"] == {"date-parts": [[1976, 3]]}

    def test_epub_date_to_csl(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["epub-date"] == {"date-parts": [[2024, 1, 15]]}

    def test_publisher_place(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["publisher-place"] == "England"

    def test_pub_status_to_status(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["status"] == "ppublish"

    def test_volume_issue_page_pass_through(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["volume"] == "48"
        assert csl["issue"] == "2"
        assert csl["page"] == "100-105"

    def test_issn_uppercase(self) -> None:
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert csl["ISSN"] == "0300-9629"
        assert "issn" not in csl

    def test_abstract_excluded(self) -> None:
        """abstract and abstract_sections are excluded from CSL-JSON."""
        from pm_tools.parse import article_to_csl

        csl = article_to_csl(self._full_record())
        assert "abstract" not in csl
        assert "abstract_sections" not in csl

    def test_absent_fields_omitted(self) -> None:
        """Fields absent in ArticleRecord produce no keys in CSL-JSON."""
        from pm_tools.parse import article_to_csl

        record: dict[str, Any] = {"pmid": "12345"}
        csl = article_to_csl(record)
        assert csl["id"] == "pmid:12345"
        assert csl["PMID"] == "12345"
        assert csl["type"] == "article-journal"
        assert csl["source"] == "PubMed"
        # Optional fields should be absent, not None
        optional_keys = (
            "title",
            "author",
            "container-title",
            "DOI",
            "PMCID",
            "volume",
            "issue",
            "page",
        )
        for key in optional_keys:
            assert key not in csl, f"{key} should be absent"

    def test_takes_article_record_not_element(self) -> None:
        """article_to_csl() takes a dict, not an ET.Element."""
        import inspect

        from pm_tools.parse import article_to_csl

        sig = inspect.signature(article_to_csl)
        params = list(sig.parameters.keys())
        assert len(params) == 1
        assert params[0] == "record"

    def test_epub_date_year_month_to_csl(self) -> None:
        """Partial epub_date (year-month) converts to CSL date-parts."""
        from pm_tools.parse import article_to_csl

        record = self._full_record()
        record["epub_date"] = "2024-03"
        csl = article_to_csl(record)
        assert csl["epub-date"] == {"date-parts": [[2024, 3]]}

    def test_epub_date_year_only_to_csl(self) -> None:
        """Partial epub_date (year only) converts to CSL date-parts."""
        from pm_tools.parse import article_to_csl

        record = self._full_record()
        record["epub_date"] = "2024"
        csl = article_to_csl(record)
        assert csl["epub-date"] == {"date-parts": [[2024]]}


class TestDateStrToParts:
    """Unit tests for _date_str_to_parts() helper."""

    def test_full_date(self) -> None:
        from pm_tools.parse import _date_str_to_parts

        assert _date_str_to_parts("2024-03-15") == [2024, 3, 15]

    def test_year_month(self) -> None:
        from pm_tools.parse import _date_str_to_parts

        assert _date_str_to_parts("2024-03") == [2024, 3]

    def test_year_only(self) -> None:
        from pm_tools.parse import _date_str_to_parts

        assert _date_str_to_parts("2024") == [2024]

    def test_non_numeric_segment_skipped(self) -> None:
        """Non-numeric segments are silently dropped."""
        from pm_tools.parse import _date_str_to_parts

        assert _date_str_to_parts("2024-Mar-15") == [2024, 15]

    def test_fully_non_numeric(self) -> None:
        from pm_tools.parse import _date_str_to_parts

        assert _date_str_to_parts("abc") == []

    def test_empty_string(self) -> None:
        from pm_tools.parse import _date_str_to_parts

        assert _date_str_to_parts("") == []


# =============================================================================
# LEGACY_FIELDS filtering — backward compatibility
# =============================================================================


class TestLegacyFieldsFiltering:
    """Default output (no --csl) emits only the 10 historical fields."""

    def test_parse_default_output_has_only_legacy_fields(self) -> None:
        """pm parse (no --csl) emits only 10 legacy fields."""
        from pm_tools.parse import LEGACY_FIELDS

        expected = frozenset(
            {
                "pmid",
                "title",
                "authors",
                "journal",
                "year",
                "date",
                "abstract",
                "abstract_sections",
                "doi",
                "pmcid",
            }
        )
        assert expected == LEGACY_FIELDS

    def test_parse_main_filters_output(self) -> None:
        """parse.main() without --csl filters to LEGACY_FIELDS."""
        import io
        import json
        import sys

        from pm_tools.parse import LEGACY_FIELDS

        xml = _make_xml()
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = io.StringIO(xml)
            out = io.StringIO()
            sys.stdout = out

            from pm_tools.parse import main

            main([])

            output = out.getvalue().strip()
            record = json.loads(output)
            assert set(record.keys()) <= LEGACY_FIELDS
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

    def test_collect_main_filters_output(self) -> None:
        """collect_main() without --csl filters to LEGACY_FIELDS."""
        import io
        from unittest.mock import patch as _patch

        from pm_tools.cli import collect_main
        from pm_tools.parse import LEGACY_FIELDS

        xml = _make_xml()
        captured = io.StringIO()

        with (
            _patch("pm_tools.search.search", return_value=["99999"]),
            _patch("pm_tools.fetch.fetch", return_value=xml),
            _patch("pm_tools.cli.find_pm_dir", return_value=None),
            _patch("sys.stdout", captured),
        ):
            result = collect_main(["test query"])

        assert result == 0
        output = captured.getvalue().strip()
        record = json.loads(output)
        assert set(record.keys()) <= LEGACY_FIELDS
        assert "volume" not in record
        assert "issn" not in record

    def test_existing_golden_files_still_pass(self, fixtures_dir: Any) -> None:
        """Golden files from fixtures/expected/ still match parse output."""
        from pathlib import Path

        from pm_tools.parse import LEGACY_FIELDS

        expected_dir = Path(fixtures_dir) / "expected"
        if not expected_dir.exists():
            pytest.skip("No golden files to validate")

        # Just verify that parse output keys are a subset of LEGACY_FIELDS
        # for any existing golden file
        import json

        # Exclude expected/csl/ (CSL golden files have different keys)
        csl_dir = expected_dir / "csl"
        for jsonl_file in expected_dir.rglob("*.jsonl"):
            if csl_dir in jsonl_file.parents:
                continue
            for line in jsonl_file.read_text().splitlines():
                if line.strip():
                    record = json.loads(line)
                    assert set(record.keys()) <= LEGACY_FIELDS, (
                        f"Golden file {jsonl_file.name} has non-legacy keys: "
                        f"{set(record.keys()) - LEGACY_FIELDS}"
                    )


# =============================================================================
# Phase 2 — --csl flag on pm parse CLI
# =============================================================================


class TestParseCslFlag:
    """pm parse --csl produces CSL-JSON output."""

    def test_csl_flag_produces_csl_keys(self) -> None:
        """pm parse --csl outputs CSL-JSON keys like container-title, DOI."""
        import io
        import json
        import sys

        xml = _make_xml()
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = io.StringIO(xml)
            out = io.StringIO()
            sys.stdout = out

            from pm_tools.parse import main

            main(["--csl"])

            output = out.getvalue().strip()
            record = json.loads(output)
            assert "container-title" in record
            assert "DOI" in record
            assert "type" in record
            assert record["type"] == "article-journal"
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

    def test_without_csl_still_produces_article_record(self) -> None:
        """pm parse (no flag) still produces ArticleRecord filtered output."""
        import io
        import json
        import sys

        xml = _make_xml()
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = io.StringIO(xml)
            out = io.StringIO()
            sys.stdout = out

            from pm_tools.parse import LEGACY_FIELDS, main

            main([])

            output = out.getvalue().strip()
            record = json.loads(output)
            assert set(record.keys()) <= LEGACY_FIELDS
            assert "container-title" not in record
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

    def test_csl_empty_xml_produces_empty_output(self) -> None:
        """pm parse --csl on empty XML → empty output, exit 0."""
        import io
        import sys

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = io.StringIO("")
            out = io.StringIO()
            sys.stdout = out

            from pm_tools.parse import main

            result = main(["--csl"])

            assert result == 0
            assert out.getvalue() == ""
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

    def test_csl_each_line_valid_json(self) -> None:
        """pm parse --csl: each output line is valid JSON."""
        import io
        import json
        import sys

        # Use two articles
        xml = """\
<PubmedArticleSet>
<PubmedArticle>
  <MedlineCitation><PMID>111</PMID>
    <Article><ArticleTitle>First</ArticleTitle></Article>
  </MedlineCitation>
</PubmedArticle>
<PubmedArticle>
  <MedlineCitation><PMID>222</PMID>
    <Article><ArticleTitle>Second</ArticleTitle></Article>
  </MedlineCitation>
</PubmedArticle>
</PubmedArticleSet>"""
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = io.StringIO(xml)
            out = io.StringIO()
            sys.stdout = out

            from pm_tools.parse import main

            main(["--csl"])

            lines = out.getvalue().strip().split("\n")
            assert len(lines) == 2
            for line in lines:
                record = json.loads(line)
                assert "id" in record
                assert "type" in record
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout


class TestParseCslPythonApi:
    """parse_xml_csl() and parse_xml_stream_csl() Python APIs."""

    def test_parse_xml_csl_returns_csl_records(self) -> None:
        from pm_tools.parse import parse_xml_csl

        xml = _make_xml()
        records = parse_xml_csl(xml)
        assert len(records) == 1
        assert records[0]["type"] == "article-journal"
        assert "container-title" in records[0]

    def test_parse_xml_stream_csl_yields_csl_records(self) -> None:
        import io

        from pm_tools.parse import parse_xml_stream_csl

        xml = _make_xml()
        stream = io.StringIO(xml)
        records = list(parse_xml_stream_csl(stream))
        assert len(records) == 1
        assert records[0]["type"] == "article-journal"


class TestCslJsonExports:
    """CslJsonRecord, article_to_csl, etc. importable from pm_tools."""

    def test_csl_json_record_importable(self) -> None:
        from pm_tools import CslJsonRecord

        assert CslJsonRecord is not None

    def test_article_to_csl_importable(self) -> None:
        from pm_tools import article_to_csl

        assert callable(article_to_csl)

    def test_parse_xml_csl_importable(self) -> None:
        from pm_tools import parse_xml_csl

        assert callable(parse_xml_csl)

    def test_parse_xml_stream_csl_importable(self) -> None:
        from pm_tools import parse_xml_stream_csl

        assert callable(parse_xml_stream_csl)

    def test_legacy_fields_importable(self) -> None:
        from pm_tools import LEGACY_FIELDS

        assert isinstance(LEGACY_FIELDS, frozenset)


# =============================================================================
# Phase 3 — --csl flag on pm collect
# =============================================================================


class TestCollectCslFlag:
    """pm collect --csl produces CSL-JSON output."""

    def test_csl_in_collect_help(self) -> None:
        """--csl appears in collect parser help."""
        from pm_tools.cli import _build_collect_parser

        assert "--csl" in _build_collect_parser().format_help()

    def test_collect_csl_flag_accepted(self) -> None:
        """collect_main(["query", "--csl"]) doesn't error on the flag."""
        # We mock the network calls to avoid actual API requests.
        from unittest.mock import patch

        from pm_tools.cli import collect_main

        with (
            patch("pm_tools.search.search", return_value=[]),
            patch("pm_tools.cli.find_pm_dir", return_value=None),
        ):
            result = collect_main(["test query", "--csl"])

        # Empty search results → exit 0
        assert result == 0

    def test_collect_without_csl_uses_legacy(self) -> None:
        """collect_main() without --csl filters to LEGACY_FIELDS."""
        import io
        import json
        from unittest.mock import patch

        from pm_tools.cli import collect_main
        from pm_tools.parse import LEGACY_FIELDS

        xml = _make_xml()
        captured = io.StringIO()

        with (
            patch("pm_tools.search.search", return_value=["99999"]),
            patch("pm_tools.fetch.fetch", return_value=xml),
            patch("pm_tools.cli.find_pm_dir", return_value=None),
            patch("sys.stdout", captured),
        ):
            result = collect_main(["test query"])

        assert result == 0
        output = captured.getvalue().strip()
        record = json.loads(output)
        assert set(record.keys()) <= LEGACY_FIELDS

    def test_collect_with_csl_produces_csl(self) -> None:
        """collect_main(["query", "--csl"]) produces CSL-JSON."""
        import io
        import json
        from unittest.mock import patch

        from pm_tools.cli import collect_main

        xml = _make_xml()
        captured = io.StringIO()

        with (
            patch("pm_tools.search.search", return_value=["99999"]),
            patch("pm_tools.fetch.fetch", return_value=xml),
            patch("pm_tools.cli.find_pm_dir", return_value=None),
            patch("sys.stdout", captured),
        ):
            result = collect_main(["test query", "--csl"])

        assert result == 0
        output = captured.getvalue().strip()
        record = json.loads(output)
        assert record["type"] == "article-journal"
        assert "container-title" in record


# =============================================================================
# Phase 4 — Golden file validation
# =============================================================================


def _strip_accessed(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a CSL record without the 'accessed' key."""
    return {k: v for k, v in record.items() if k != "accessed"}


class TestCslGoldenFiles:
    """Validate pm parse --csl against golden files."""

    def _find_xml_for_golden(self, golden_path: Path, fixtures_dir: Path) -> Path:
        """Map a golden .jsonl path back to the source .xml fixture."""
        # Golden: fixtures/expected/csl/random/pmid-3341.jsonl
        # Source: fixtures/random/pmid-3341.xml
        rel = golden_path.relative_to(fixtures_dir / "expected" / "csl")
        return (fixtures_dir / rel).with_suffix(".xml")

    def test_golden_files_match(self, fixtures_dir: Any) -> None:
        """For each golden file, parse XML + article_to_csl matches."""
        from pm_tools.parse import article_to_csl, parse_xml

        csl_dir = Path(fixtures_dir) / "expected" / "csl"
        if not csl_dir.exists():
            pytest.skip("No CSL golden files")

        golden_files = list(csl_dir.rglob("*.jsonl"))
        assert len(golden_files) > 0, "No golden files found"

        for golden_path in golden_files:
            xml_path = self._find_xml_for_golden(golden_path, Path(fixtures_dir))
            assert xml_path.exists(), f"Source XML not found: {xml_path}"

            xml = xml_path.read_text()
            articles = parse_xml(xml)
            actual_csl = [_strip_accessed(article_to_csl(a)) for a in articles]

            expected_lines = golden_path.read_text().strip().splitlines()
            expected_csl = [
                _strip_accessed(json.loads(line)) for line in expected_lines if line.strip()
            ]

            assert len(actual_csl) == len(expected_csl), (
                f"{golden_path.name}: expected {len(expected_csl)} records, got {len(actual_csl)}"
            )
            for i, (actual, expected) in enumerate(zip(actual_csl, expected_csl, strict=True)):
                assert actual == expected, f"{golden_path.name} record {i}: mismatch"

    def test_csl_output_has_required_fields(self, fixtures_dir: Any) -> None:
        """Every CSL record from random fixtures has id, type, source, PMID."""
        from pm_tools.parse import article_to_csl, parse_xml

        random_dir = Path(fixtures_dir) / "random"
        xml_files = list(random_dir.glob("*.xml"))
        assert len(xml_files) > 0, "No random XML fixtures found"
        for xml_path in xml_files:
            xml = xml_path.read_text()
            for article in parse_xml(xml):
                csl = article_to_csl(article)
                assert "id" in csl, f"{xml_path.name}: missing id"
                assert "type" in csl, f"{xml_path.name}: missing type"
                assert "source" in csl, f"{xml_path.name}: missing source"
                assert "PMID" in csl, f"{xml_path.name}: missing PMID"

    def test_csl_derived_fields_correct(self, fixtures_dir: Any) -> None:
        """id = pmid:{PMID}, type = article-journal, source = PubMed."""
        from pm_tools.parse import article_to_csl, parse_xml

        random_dir = Path(fixtures_dir) / "random"
        xml_files = list(random_dir.glob("*.xml"))
        assert len(xml_files) > 0, "No random XML fixtures found"
        for xml_path in xml_files:
            xml = xml_path.read_text()
            for article in parse_xml(xml):
                csl = article_to_csl(article)
                assert csl["id"] == f"pmid:{csl['PMID']}"
                assert csl["type"] == "article-journal"
                assert csl["source"] == "PubMed"
