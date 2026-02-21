"""Tests for pm_tools.diff — compare two sets of articles and report changes.

RED phase: tests that validate diff_jsonl() behavior and drive new features.

Core diff tests validate existing implementation. Tests for unimplemented
features (changed_fields detail, summary statistics, stable ordering) will
fail, driving new development.

Return codes: 0 = no diff, 1 = diffs found, 2 = errors.
"""

from __future__ import annotations

from pm_tools.diff import diff_jsonl

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _art(
    pmid: str = "1",
    title: str = "Title",
    authors: list[dict[str, str]] | None = None,
    journal: str = "Nature",
    year: int = 2024,
    doi: str = "10.1234/test",
    abstract: str = "Abstract text.",
    **extra: object,
) -> dict:
    d: dict = {
        "pmid": pmid,
        "title": title,
        "authors": authors if authors is not None else [{"family": "Smith", "given": "J"}],
        "journal": journal,
        "year": year,
        "doi": doi,
        "abstract": abstract,
    }
    d.update(extra)
    return d


# ---------------------------------------------------------------------------
# Identical inputs
# ---------------------------------------------------------------------------


class TestNoDifferences:
    def test_identical_lists_produce_no_output(self) -> None:
        articles = [_art(pmid="1"), _art(pmid="2")]
        result = diff_jsonl(articles, articles)
        assert result == []

    def test_both_empty_no_differences(self) -> None:
        result = diff_jsonl([], [])
        assert result == []


# ---------------------------------------------------------------------------
# Added articles
# ---------------------------------------------------------------------------


class TestAdded:
    def test_detects_added_articles(self) -> None:
        old = [_art(pmid="1")]
        new = [_art(pmid="1"), _art(pmid="2", title="New Paper")]
        result = diff_jsonl(old, new)

        added = [d for d in result if d["status"] == "added"]
        assert len(added) == 1
        assert added[0]["pmid"] == "2"
        assert added[0]["article"]["title"] == "New Paper"

    def test_empty_old_means_all_added(self) -> None:
        new = [_art(pmid="1"), _art(pmid="2")]
        result = diff_jsonl([], new)

        assert len(result) == 2
        assert all(d["status"] == "added" for d in result)


# ---------------------------------------------------------------------------
# Removed articles
# ---------------------------------------------------------------------------


class TestRemoved:
    def test_detects_removed_articles(self) -> None:
        old = [_art(pmid="1"), _art(pmid="2", title="Old Paper")]
        new = [_art(pmid="1")]
        result = diff_jsonl(old, new)

        removed = [d for d in result if d["status"] == "removed"]
        assert len(removed) == 1
        assert removed[0]["pmid"] == "2"
        assert removed[0]["article"]["title"] == "Old Paper"

    def test_empty_new_means_all_removed(self) -> None:
        old = [_art(pmid="1"), _art(pmid="2")]
        result = diff_jsonl(old, [])

        assert len(result) == 2
        assert all(d["status"] == "removed" for d in result)


# ---------------------------------------------------------------------------
# Changed articles
# ---------------------------------------------------------------------------


class TestChanged:
    def test_detects_title_change(self) -> None:
        old = [_art(pmid="1", title="Old Title")]
        new = [_art(pmid="1", title="New Title")]
        result = diff_jsonl(old, new)

        changed = [d for d in result if d["status"] == "changed"]
        assert len(changed) == 1
        assert changed[0]["pmid"] == "1"
        assert changed[0]["old"]["title"] == "Old Title"
        assert changed[0]["new"]["title"] == "New Title"

    def test_detects_author_change(self) -> None:
        old = [_art(pmid="1", authors=[{"family": "Smith", "given": "J"}])]
        new = [
            _art(
                pmid="1",
                authors=[
                    {"family": "Smith", "given": "J"},
                    {"family": "Doe", "given": "A"},
                ],
            )
        ]
        result = diff_jsonl(old, new)

        changed = [d for d in result if d["status"] == "changed"]
        assert len(changed) == 1
        assert changed[0]["pmid"] == "1"

    def test_detects_field_added(self) -> None:
        """A field present in new but absent in old counts as a change."""
        old_art = _art(pmid="1")
        del old_art["abstract"]
        new_art = _art(pmid="1", abstract="Now has abstract")
        result = diff_jsonl([old_art], [new_art])

        changed = [d for d in result if d["status"] == "changed"]
        assert len(changed) == 1

    def test_detects_field_removed(self) -> None:
        """A field present in old but absent in new counts as a change."""
        old_art = _art(pmid="1", abstract="Has abstract")
        new_art = _art(pmid="1")
        del new_art["abstract"]
        result = diff_jsonl([old_art], [new_art])

        changed = [d for d in result if d["status"] == "changed"]
        assert len(changed) == 1


# ---------------------------------------------------------------------------
# Mixed changes
# ---------------------------------------------------------------------------


class TestMixed:
    def test_mixed_added_removed_changed(self) -> None:
        old = [
            _art(pmid="1", title="Unchanged"),
            _art(pmid="2", title="Will Change"),
            _art(pmid="3", title="Will Be Removed"),
        ]
        new = [
            _art(pmid="1", title="Unchanged"),
            _art(pmid="2", title="Has Changed"),
            _art(pmid="4", title="Newly Added"),
        ]
        result = diff_jsonl(old, new)

        statuses = {d["status"] for d in result}
        assert "added" in statuses
        assert "removed" in statuses
        assert "changed" in statuses

        added = [d for d in result if d["status"] == "added"]
        assert len(added) == 1
        assert added[0]["pmid"] == "4"

        removed = [d for d in result if d["status"] == "removed"]
        assert len(removed) == 1
        assert removed[0]["pmid"] == "3"

        changed = [d for d in result if d["status"] == "changed"]
        assert len(changed) == 1
        assert changed[0]["pmid"] == "2"


# ---------------------------------------------------------------------------
# --ignore option
# ---------------------------------------------------------------------------


class TestIgnoreFields:
    def test_ignore_abstract_excludes_from_comparison(self) -> None:
        old = [_art(pmid="1", abstract="Old abstract")]
        new = [_art(pmid="1", abstract="New abstract")]

        result_with = diff_jsonl(old, new)
        assert len(result_with) == 1

        result_ignored = diff_jsonl(old, new, ignore_fields=["abstract"])
        assert result_ignored == []

    def test_ignore_multiple_fields(self) -> None:
        old = [_art(pmid="1", abstract="Old", year=2020)]
        new = [_art(pmid="1", abstract="New", year=2024)]

        result = diff_jsonl(old, new, ignore_fields=["abstract", "year"])
        assert result == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestDiffEdgeCases:
    def test_malformed_entry_skipped(self) -> None:
        """Non-dict or dict without pmid should be silently skipped."""
        old = [_art(pmid="1"), "not-a-dict"]  # type: ignore[list-item]
        new = [_art(pmid="1")]
        result = diff_jsonl(old, new)  # type: ignore[arg-type]
        assert result == []

    def test_handles_unicode_in_fields(self) -> None:
        old = [_art(pmid="1", title="Etude des proteines")]
        new = [_art(pmid="1", title="Etude des proteines modifiees")]
        result = diff_jsonl(old, new)

        changed = [d for d in result if d["status"] == "changed"]
        assert len(changed) == 1
        assert changed[0]["old"]["title"] == "Etude des proteines"
        assert changed[0]["new"]["title"] == "Etude des proteines modifiees"


# ---------------------------------------------------------------------------
# Return code semantics
# ---------------------------------------------------------------------------


class TestDiffReturnCode:
    def test_no_diff_empty_result(self) -> None:
        result = diff_jsonl([_art(pmid="1")], [_art(pmid="1")])
        assert len(result) == 0

    def test_diffs_found_nonempty_result(self) -> None:
        result = diff_jsonl([_art(pmid="1")], [])
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Unimplemented features (RED phase)
# ---------------------------------------------------------------------------


class TestChangedFieldsDetail:
    """Changed records should include a 'changed_fields' list showing which fields differ.

    Not yet implemented -- drives richer diff output.
    """

    def test_changed_record_includes_changed_fields_list(self) -> None:
        old = [_art(pmid="1", title="Old Title", year=2020)]
        new = [_art(pmid="1", title="New Title", year=2024)]
        result = diff_jsonl(old, new)

        changed = [d for d in result if d["status"] == "changed"]
        assert len(changed) == 1
        assert "changed_fields" in changed[0], (
            "Changed records should include 'changed_fields' listing which fields differ"
        )
        assert set(changed[0]["changed_fields"]) == {"title", "year"}

    def test_changed_fields_excludes_unchanged(self) -> None:
        old = [_art(pmid="1", title="Old Title")]
        new = [_art(pmid="1", title="New Title")]
        result = diff_jsonl(old, new)

        changed = result[0]
        assert "changed_fields" in changed
        assert "journal" not in changed["changed_fields"], "Unchanged fields should be excluded"


class TestDiffSummary:
    """diff module should expose a diff_summary() function for aggregate stats.

    Not yet implemented -- drives adding summary statistics.
    """

    def test_summary_returns_counts(self) -> None:
        from pm_tools.diff import diff_summary

        old = [_art(pmid="1"), _art(pmid="2", title="Will Change"), _art(pmid="3")]
        new = [_art(pmid="1"), _art(pmid="2", title="Changed"), _art(pmid="4")]

        summary = diff_summary(old, new)
        assert summary["added"] == 1
        assert summary["removed"] == 1
        assert summary["changed"] == 1
        assert summary["unchanged"] == 1


class TestDiffStableOrdering:
    """Diff results should be ordered: removed first, then changed, then added.

    Not yet implemented -- the current implementation uses dict iteration order.
    """

    def test_results_ordered_removed_changed_added(self) -> None:
        old = [
            _art(pmid="1", title="Unchanged"),
            _art(pmid="2", title="Will Change"),
            _art(pmid="3", title="Will Be Removed"),
        ]
        new = [
            _art(pmid="1", title="Unchanged"),
            _art(pmid="2", title="Has Changed"),
            _art(pmid="4", title="Newly Added"),
        ]
        result = diff_jsonl(old, new)

        statuses = [d["status"] for d in result]
        # All removed should come before changed, which should come before added
        removed_indices = [i for i, s in enumerate(statuses) if s == "removed"]
        changed_indices = [i for i, s in enumerate(statuses) if s == "changed"]
        added_indices = [i for i, s in enumerate(statuses) if s == "added"]

        if removed_indices and changed_indices:
            assert max(removed_indices) < min(changed_indices), "Removed should come before changed"
        if changed_indices and added_indices:
            assert max(changed_indices) < min(added_indices), "Changed should come before added"
