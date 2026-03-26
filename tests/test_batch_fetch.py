"""Tests for cached_batch_fetch() — generic cache-aware batch fetcher.

Tests use a fake fetch_batch callback (no HTTP mocking needed).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pm_tools.cache import cached_batch_fetch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



def _fake_fetch_batch(ids: list[str]) -> list[tuple[str, str]]:
    """Fake fetch_batch that returns (id, f"data-{id}") pairs."""
    return [(id_, f"data-{id_}") for id_ in ids]


class _CallTracker:
    """Callable that records each call and delegates to _fake_fetch_batch."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, ids: list[str]) -> list[tuple[str, str]]:
        self.calls.append(ids)
        return _fake_fetch_batch(ids)


# ---------------------------------------------------------------------------
# Tests — cache behavior
# ---------------------------------------------------------------------------


class TestEmptyIds:
    """Edge case: empty IDs list."""

    def test_empty_ids_returns_empty_dict(self, pm_dir: Path) -> None:
        """cached_batch_fetch with no IDs returns empty dict immediately."""
        tracker = _CallTracker()
        result = cached_batch_fetch(
            ids=[],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=tracker,
        )
        assert result == {}
        assert tracker.calls == []

    def test_empty_ids_no_pm_dir(self) -> None:
        """cached_batch_fetch with no IDs and no pm_dir returns empty dict."""
        result = cached_batch_fetch(
            ids=[],
            pm_dir=None,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=_fake_fetch_batch,
        )
        assert result == {}


class TestAllCached:
    """When all IDs are already cached, fetch_batch should not be called."""

    def test_all_cached_no_fetch(self, pm_dir: Path) -> None:

        # Pre-populate cache
        for id_ in ("A", "B"):
            (pm_dir / "cache" / "test" / f"{id_}.txt").parent.mkdir(parents=True, exist_ok=True)
            (pm_dir / "cache" / "test" / f"{id_}.txt").write_text(f"cached-{id_}")

        tracker = _CallTracker()
        result = cached_batch_fetch(
            ids=["A", "B"],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=tracker,
        )

        assert tracker.calls == [], "fetch_batch should not be called when all IDs are cached"
        assert result == {"A": "cached-A", "B": "cached-B"}


class TestAllUncached:
    """When nothing is cached, fetch_batch is called with all IDs."""

    def test_all_uncached_fetches_all(self, pm_dir: Path) -> None:
        tracker = _CallTracker()

        result = cached_batch_fetch(
            ids=["A", "B", "C"],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=tracker,
        )

        # All IDs should have been fetched
        fetched_ids = [id_ for call in tracker.calls for id_ in call]
        assert set(fetched_ids) == {"A", "B", "C"}
        assert result == {"A": "data-A", "B": "data-B", "C": "data-C"}

    def test_fetched_data_written_to_cache(self, pm_dir: Path) -> None:

        cached_batch_fetch(
            ids=["A"],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=_fake_fetch_batch,
        )

        cached_file = pm_dir / "cache" / "test" / "A.txt"
        assert cached_file.exists()
        assert cached_file.read_text() == "data-A"

    def test_no_pm_dir_still_works(self) -> None:
        """Without pm_dir (None), fetch_batch is called and results returned."""
        tracker = _CallTracker()
        result = cached_batch_fetch(
            ids=["A", "B"],
            pm_dir=None,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=tracker,
        )

        assert len(tracker.calls) == 1
        assert result == {"A": "data-A", "B": "data-B"}


class TestMixedCacheUncached:
    """When some IDs are cached and some are not, only uncached are fetched."""

    def test_mixed_fetches_only_uncached(self, pm_dir: Path) -> None:

        # Cache "A" only
        (pm_dir / "cache" / "test").mkdir(parents=True, exist_ok=True)
        (pm_dir / "cache" / "test" / "A.txt").write_text("cached-A")

        tracker = _CallTracker()
        result = cached_batch_fetch(
            ids=["A", "B", "C"],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=tracker,
        )

        # Only B and C should be fetched
        fetched_ids = [id_ for call in tracker.calls for id_ in call]
        assert "A" not in fetched_ids
        assert set(fetched_ids) == {"B", "C"}

        # All results present
        assert result["A"] == "cached-A"
        assert result["B"] == "data-B"
        assert result["C"] == "data-C"


# ---------------------------------------------------------------------------
# Tests — batching
# ---------------------------------------------------------------------------


class TestBatching:
    """IDs should be split into batch_size chunks for fetch_batch calls."""

    def test_single_batch_when_under_limit(self, pm_dir: Path) -> None:
        tracker = _CallTracker()

        cached_batch_fetch(
            ids=["A", "B", "C"],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=tracker,
            batch_size=10,
        )

        assert len(tracker.calls) == 1
        assert tracker.calls[0] == ["A", "B", "C"]

    def test_splits_into_batches(self, pm_dir: Path) -> None:
        tracker = _CallTracker()

        ids = [str(i) for i in range(5)]
        cached_batch_fetch(
            ids=ids,
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=tracker,
            batch_size=2,
            rate_limit_delay=0,
        )

        assert len(tracker.calls) == 3  # [0,1], [2,3], [4]
        assert tracker.calls[0] == ["0", "1"]
        assert tracker.calls[1] == ["2", "3"]
        assert tracker.calls[2] == ["4"]

    def test_batching_only_uncached(self, pm_dir: Path) -> None:
        """Batch size applies to uncached IDs, not total IDs."""

        # Cache 3 IDs
        (pm_dir / "cache" / "test").mkdir(parents=True, exist_ok=True)
        for i in range(3):
            (pm_dir / "cache" / "test" / f"{i}.txt").write_text(f"cached-{i}")

        tracker = _CallTracker()
        ids = [str(i) for i in range(7)]  # 3 cached + 4 uncached
        cached_batch_fetch(
            ids=ids,
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=tracker,
            batch_size=2,
            rate_limit_delay=0,
        )

        # Only 4 uncached → 2 batches of 2
        assert len(tracker.calls) == 2


# ---------------------------------------------------------------------------
# Tests — deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    """When deduplicate=True, duplicate IDs should be fetched only once."""

    def test_dedup_removes_duplicates(self, pm_dir: Path) -> None:
        tracker = _CallTracker()

        result = cached_batch_fetch(
            ids=["A", "B", "A", "C", "B"],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=tracker,
            deduplicate=True,
        )

        fetched_ids = [id_ for call in tracker.calls for id_ in call]
        assert sorted(fetched_ids) == ["A", "B", "C"]
        assert result == {"A": "data-A", "B": "data-B", "C": "data-C"}

    def test_no_dedup_by_default(self, pm_dir: Path) -> None:
        """Without deduplicate=True, duplicate IDs are NOT removed."""
        tracker = _CallTracker()

        cached_batch_fetch(
            ids=["A", "A"],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=tracker,
            deduplicate=False,
        )

        # Without dedup, both "A" IDs appear in the input list.
        # The key invariant: duplicates are NOT removed before fetching.
        fetched_ids = [id_ for call in tracker.calls for id_ in call]
        assert fetched_ids.count("A") == 2, "Without dedup, duplicate IDs should be preserved"


# ---------------------------------------------------------------------------
# Tests — refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    """When refresh=True, cache is bypassed and all IDs are fetched."""

    def test_refresh_bypasses_cache(self, pm_dir: Path) -> None:

        # Pre-cache
        (pm_dir / "cache" / "test").mkdir(parents=True, exist_ok=True)
        (pm_dir / "cache" / "test" / "A.txt").write_text("old-A")

        tracker = _CallTracker()
        result = cached_batch_fetch(
            ids=["A"],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=tracker,
            refresh=True,
        )

        assert len(tracker.calls) == 1, "Should fetch even though cached"
        assert result["A"] == "data-A"


# ---------------------------------------------------------------------------
# Tests — audit logging
# ---------------------------------------------------------------------------


class TestAuditLogging:
    """cached_batch_fetch writes an audit event to pm_dir/audit.jsonl."""

    def test_writes_audit_event(self, pm_dir: Path) -> None:

        cached_batch_fetch(
            ids=["A", "B"],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=_fake_fetch_batch,
        )

        lines = (pm_dir / "audit.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["op"] == "test"
        assert event["requested"] == 2
        assert event["cached"] == 0
        assert event["fetched"] == 2
        assert "ts" in event

    def test_audit_counts_cached_and_fetched(self, pm_dir: Path) -> None:

        # Cache one ID
        (pm_dir / "cache" / "test").mkdir(parents=True, exist_ok=True)
        (pm_dir / "cache" / "test" / "A.txt").write_text("cached-A")

        cached_batch_fetch(
            ids=["A", "B", "C"],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=_fake_fetch_batch,
        )

        event = json.loads((pm_dir / "audit.jsonl").read_text().strip().splitlines()[0])
        assert event["cached"] == 1
        assert event["fetched"] == 2

    def test_no_audit_without_pm_dir(self) -> None:
        """When pm_dir is None, no audit log is written (no crash)."""
        # Should not raise
        cached_batch_fetch(
            ids=["A"],
            pm_dir=None,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=_fake_fetch_batch,
        )


# ---------------------------------------------------------------------------
# Tests — verbose mode
# ---------------------------------------------------------------------------


class TestVerbose:
    """Verbose mode prints progress to stderr."""

    def test_verbose_prints_progress(
        self, pm_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:

        cached_batch_fetch(
            ids=["A", "B", "C"],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=_fake_fetch_batch,
            verbose=True,
            batch_size=2,
            rate_limit_delay=0,
        )

        captured = capsys.readouterr()
        assert "Fetching batch 1 (2 IDs)..." in captured.err

    def test_quiet_by_default(self, pm_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:

        cached_batch_fetch(
            ids=["A", "B"],
            pm_dir=pm_dir,
            cache_category="test",
            cache_ext=".txt",
            fetch_batch=_fake_fetch_batch,
            verbose=False,
        )

        captured = capsys.readouterr()
        assert captured.err == ""


# ---------------------------------------------------------------------------
# Tests — audit_log mutation bug
# ---------------------------------------------------------------------------


class TestAuditLogMutationBug:
    """audit_log() must NOT mutate the caller's dict."""

    def test_audit_log_does_not_mutate_event(self, pm_dir: Path) -> None:
        from pm_tools.cache import audit_log

        event = {"op": "test", "count": 42}

        audit_log(pm_dir, event)

        assert "ts" not in event, "audit_log() should not mutate the caller's dict"
