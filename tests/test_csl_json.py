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

from pm_tools.parse import _date_str_to_parts, article_to_csl, parse_xml

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

    def test_full_record_mapping(self) -> None:
        """All fields from a full ArticleRecord map to correct CSL-JSON keys."""
        csl = article_to_csl(self._full_record())

        # Fixed metadata
        assert csl["id"] == "pmid:12345"
        assert csl["type"] == "article-journal"
        assert csl["source"] == "PubMed"

        # Renamed / uppercased identifiers
        assert csl["PMID"] == "12345"
        assert csl["DOI"] == "10.1234/test"
        assert csl["PMCID"] == "PMC1234567"
        assert csl["ISSN"] == "0300-9629"
        for raw_key in ("pmid", "doi", "pmcid", "issn"):
            assert raw_key not in csl

        # Authors renamed
        assert csl["author"] == [{"family": "Smith", "given": "John"}]
        assert "authors" not in csl

        # Journal → container-title
        assert csl["container-title"] == "Nature Medicine"
        assert "journal" not in csl
        assert csl["container-title-short"] == "Nat Med"

        # Pass-through fields
        assert csl["volume"] == "48"
        assert csl["issue"] == "2"
        assert csl["page"] == "100-105"

        # Dates
        assert csl["issued"] == {"date-parts": [[2024, 3, 15]]}
        assert csl["epub-date"] == {"date-parts": [[2024, 1, 15]]}

        # Other mapped fields
        assert csl["publisher-place"] == "England"
        assert csl["status"] == "ppublish"

        # Excluded fields
        assert "abstract" not in csl
        assert "abstract_sections" not in csl

    def test_accessed_uses_today(self) -> None:
        """accessed date-parts reflect the current date."""
        with patch("pm_tools.parse.datetime") as mock_dt:
            mock_dt.date.today.return_value = datetime.date(2026, 3, 24)
            csl = article_to_csl(self._full_record())
        assert csl["accessed"] == {"date-parts": [[2026, 3, 24]]}

    def test_issued_year_only(self) -> None:
        """Date with year only -> issued [[2024]]."""
        record = self._full_record()
        record["date"] = "2024"
        assert article_to_csl(record)["issued"] == {"date-parts": [[2024]]}

    def test_issued_year_month(self) -> None:
        """Date year-month -> issued [[2024, 3]]."""
        record = self._full_record()
        record["date"] = "2024-03"
        assert article_to_csl(record)["issued"] == {"date-parts": [[2024, 3]]}

    def test_issued_seasonal_date(self) -> None:
        """Spring 1976 -> date '1976-03' -> issued [[1976, 3]]."""
        record = self._full_record()
        record["year"] = 1976
        record["date"] = "1976-03"
        assert article_to_csl(record)["issued"] == {"date-parts": [[1976, 3]]}

    def test_epub_date_year_month_to_csl(self) -> None:
        """Partial epub_date (year-month) converts to CSL date-parts."""
        record = self._full_record()
        record["epub_date"] = "2024-03"
        assert article_to_csl(record)["epub-date"] == {"date-parts": [[2024, 3]]}

    def test_epub_date_year_only_to_csl(self) -> None:
        """Partial epub_date (year only) converts to CSL date-parts."""
        record = self._full_record()
        record["epub_date"] = "2024"
        assert article_to_csl(record)["epub-date"] == {"date-parts": [[2024]]}

    def test_absent_fields_omitted(self) -> None:
        """Fields absent in ArticleRecord produce no keys in CSL-JSON."""
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


class TestDateStrToParts:
    """Unit tests for _date_str_to_parts() helper."""

    @pytest.mark.parametrize(
        ("input_str", "expected"),
        [
            ("2024-03-15", [2024, 3, 15]),
            ("2024-03", [2024, 3]),
            ("2024", [2024]),
            ("2024-Mar-15", [2024, 15]),  # non-numeric segments dropped
            ("abc", []),
            ("", []),
        ],
        ids=[
            "full_date", "year_month", "year_only",
            "non_numeric_segment", "fully_non_numeric", "empty",
        ],
    )
    def test_date_str_to_parts(self, input_str: str, expected: list[int]) -> None:
        assert _date_str_to_parts(input_str) == expected


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

    def test_parse_main_filters_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """parse.main() without --csl filters to LEGACY_FIELDS."""
        import io
        import json

        from pm_tools.parse import LEGACY_FIELDS

        xml = _make_xml()
        fake_stdin = io.StringIO(xml)
        fake_stdin.buffer = io.BytesIO(xml.encode("utf-8"))  # type: ignore[attr-defined]
        monkeypatch.setattr("sys.stdin", fake_stdin)
        out = io.StringIO()
        monkeypatch.setattr("sys.stdout", out)

        from pm_tools.parse import main

        main([])

        output = out.getvalue().strip()
        record = json.loads(output)
        assert set(record.keys()) <= LEGACY_FIELDS

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

