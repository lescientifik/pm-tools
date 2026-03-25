---
description: TDD roadmap for 5 simplification refactorings identified in the adversarial review (target ~250 lines removed).
---

# Roadmap: Simplification Refactoring

**Source**: `docs/research/adversarial-review-r1.md`
**Baseline**: 3,502 SLOC (source), 8,445 SLOC (tests)
**Target**: ~3,250 SLOC source (net reduction ~250 lines), zero behavior change
**Constraint**: All existing tests must pass at every phase boundary

### Methodology: TDD vs Refactoring-Under-Green

This roadmap contains two kinds of work:

- **New code** (Phases 2, 3): True TDD — write failing tests first (RED), implement (GREEN), clean up (REFACTOR).
- **Refactoring** (Phases 0, 1, 4, 5): Refactoring-under-green — existing tests are the safety net. Verify green before AND after each change. No artificial failing tests.

---

## Phase 0 — Cleanup: Delete Dead Code

**Objectif**: Remove `fetch_stream()` (dead code, 0 callers).

**Dépendances**: None.

**Steps**:
1. Verify all tests pass.
2. Delete `fetch_stream()` from `fetch.py` (lines 210-217). It returns `str` while its docstring says "yielding", has no callers, and lacks `cache_dir`/`pm_dir` params.
3. Grep codebase for remaining references.
4. Verify all tests still pass.

**Note on `count_matching()`**: The review flagged it as unused, but it has 2 test callers in `test_filter.py` (`TestFilterCount`). It's a public utility function — **keep it**.

**Parallélisation**: Single agent, trivial change.

**Critères de complétion**:
- [ ] `fetch_stream` deleted
- [ ] `grep -r fetch_stream src/ tests/` returns zero results
- [ ] All existing tests pass
- [ ] `ruff check` clean

---

## Phase 1 — Unify `cache_dir` / `pm_dir` into single `pm_dir`

**Objectif**: Replace the duplicated `cache_dir`/`pm_dir` parameters with a single `pm_dir` across all API functions. Both params always receive the same value from `find_pm_dir()` — the distinction has no real use.

**Dépendances**: Phase 0.

**Steps** (refactoring-under-green):
1. Verify all tests pass.
2. In `search.py`, `fetch.py`, `cite.py`:
   - Remove the `cache_dir` parameter from function signatures
   - Replace all internal `cache_dir` usage with `pm_dir`
   - Update each module's `main()` call site
3. Update `cli.py:collect_main()` — 3 call sites pass `cache_dir=detected_pm_dir`.
4. **Update ~28 test call sites** across `test_search.py` (12), `test_fetch.py` (8), `test_cite.py` (8): rename `cache_dir=` to `pm_dir=`.
5. Grep for any remaining `cache_dir` references.
6. Verify all tests pass.

**Scope of change**:
```
search.py   — signature + main() call site
fetch.py    — signature + main() call site
cite.py     — signature + main() call site
cli.py      — 3 call sites in collect_main
tests/      — ~28 mechanical renames (cache_dir= → pm_dir=)
```

**Parallélisation**: 3 parallel agents (one per module: search+test_search, fetch+test_fetch, cite+test_cite). Then 1 sequential agent for cli.py.

**Critères de complétion**:
- [ ] `cache_dir` parameter removed from all function signatures
- [ ] `grep -r cache_dir src/ tests/` returns zero results
- [ ] All existing tests pass
- [ ] `ruff check` clean

---

## Phase 2 — Extract Shared Utilities

**Objectif**: Extract `cached_batch_fetch()` helper, shared JSONL parser, and shared HTTP client factory.

**Dépendances**: Phase 1 (pm_dir is unified).

### Sub-phase 2.1 — Shared HTTP client factory

**TDD Steps** (new code):
- RED: Write test that `pm_tools.http.get_client()` returns an `httpx.Client` with expected timeout/redirect settings.
- GREEN: Create `src/pm_tools/http.py` with:
  ```python
  _client: httpx.Client | None = None

  def get_client(timeout: int = 30) -> httpx.Client:
      """Get or create the shared HTTP client."""
      global _client
      if _client is None:
          _client = httpx.Client(timeout=timeout, follow_redirects=True)
      return _client
  ```
- REFACTOR (under green): Replace `get_http_client()` in `cite.py` and `download.py`. Replace bare `httpx.get()` calls in `search.py` and `fetch.py` with `get_client().get()`.

### Sub-phase 2.2 — Shared JSONL utilities

**TDD Steps** (new code):
- RED: Write tests for `read_jsonl(stream) -> Iterator[dict]`:
  - Valid JSONL lines yield dicts
  - Malformed lines skipped silently
  - Empty lines skipped
  - Non-dict JSON values skipped
- GREEN: Create utility in a new `src/pm_tools/io.py` module.
- REFACTOR (under green): Replace `filter.py:parse_jsonl_stream()`, `diff.py:load_jsonl()`, and inline parsing in `download.py:main()`.

### Sub-phase 2.3 — `cached_batch_fetch()` helper

The pattern shared by `fetch()` and `cite()`:
```
1. Split IDs into cached / uncached
2. Batch-fetch uncached with rate limiting
3. Cache individual results
4. Audit log
5. Reassemble in original order
```

**TDD Steps** (new code):
- RED: Write tests for a generic `cached_batch_fetch()`:
  ```python
  def cached_batch_fetch(
      ids: list[str],
      *,
      pm_dir: Path | None,
      cache_category: str,       # "fetch" or "cite"
      cache_ext: str,            # ".xml" or ".json"
      fetch_batch: Callable[[list[str]], list[tuple[str, str]]],
      batch_size: int = 200,
      rate_limit_delay: float = 0.34,
      refresh: bool = False,
      verbose: bool = False,
      deduplicate: bool = False,
  ) -> dict[str, str]:  # id → cached/fetched data (raw strings)
  ```
  Tests: all-cached, all-uncached, mixed, rate limiting, audit logged, deduplication. The `fetch_batch` callback is a pure function injection — tests supply a fake, no HTTP mocking needed.

- GREEN: Implement in `cache.py`.

- REFACTOR (under green): Rewrite `fetch()` and `cite()` to use the helper.

**Design notes**:
- Returns `dict[str, str]` (id → raw data as string). `cite()` will `json.loads()` each value — minor cost, acceptable for simplicity.
- The `fetch_batch` callback for `cite` must handle per-batch error recovery internally (catch `HTTPError`, skip failed batch, return what succeeded). This differs from `fetch` which lets errors propagate.
- Also fix `audit_log()` mutation: copy the event dict before adding `ts` (latent bug from m1 in review).

**Critères de complétion (Phase 2 total)**:
- [ ] `http.py` exists with shared client factory
- [ ] JSONL utility extracted, 3+ call sites refactored
- [ ] `cached_batch_fetch()` implemented and tested
- [ ] `fetch()` and `cite()` use the helper
- [ ] Duplicate `get_http_client()` removed from cite.py and download.py
- [ ] `audit_log()` no longer mutates caller's dict
- [ ] All existing tests pass
- [ ] `ruff check` clean

---

## Review Gate 1: `/adversarial-review`

After Phase 2, review the refactored cache/HTTP/JSONL layer. This is the foundation for Phases 3-4.

---

## Phase 3 — Define TypedDicts for Implicit Schemas

**Objectif**: Replace `dict[str, Any]` with typed dicts for all domain objects with well-known schemas. Also resolve the `PmcResult` dataclass/dict paradigm conflict in `download.py`.

**Dépendances**: Phase 2 (shared utilities are in place).

### New types to add in `types.py`:

```python
class DownloadSource(TypedDict, total=False):
    pmid: Required[str]
    source: str | None        # "pmc", "unpaywall", or None
    url: str | None
    pmcid: str
    doi: str
    pmc_format: str           # "pdf" or "tgz"

class DiffResult(TypedDict, total=False):
    pmid: Required[str]
    status: Required[str]     # "added", "removed", "changed"
    article: dict[str, Any]   # for added/removed
    old: dict[str, Any]       # for changed
    new: dict[str, Any]       # for changed
    changed_fields: list[str] # for changed

class AuditEvent(TypedDict, total=False):
    ts: Required[str]
    op: Required[str]
    db: str
    query: str
    count: int
    cached: bool | int
    requested: int
    fetched: int
    refreshed: bool
    input: int
    output: int
    excluded: int
    total: int
    downloaded: int
    skipped: int
    failed: int
    criteria: dict[str, Any]
    original_ts: str
    max: int

class SearchCacheEntry(TypedDict):
    query: str
    max_results: int
    pmids: list[str]
    count: int
    timestamp: str
```

### PmcResult resolution

`PmcResult` (dataclass) is created in `pmc_lookup()` then immediately destructured into a plain dict in `find_sources()`. Replace: `pmc_lookup()` returns a `DownloadSource` dict directly (or the relevant fields). Delete `PmcResult` dataclass — one fewer paradigm.

### TDD Steps (new code + refactoring):
- RED: Write type-checking tests: construct each TypedDict, verify required fields. Test `pmc_lookup()` returns a dict instead of `PmcResult`.
- GREEN: Add types to `types.py`. Update function signatures:
  - `download.py`: `find_sources() -> list[DownloadSource]`, `_download_one(source: DownloadSource)`. Remove `PmcResult`, refactor `pmc_lookup()`.
  - `diff.py`: `diff_jsonl() -> list[DiffResult]`
  - `audit.py`: `_read_events() -> list[AuditEvent]`
  - `search.py`: cache entry typed as `SearchCacheEntry`
  - `cite.py`: `cite() -> list[CslJsonRecord]`
- REFACTOR: Update `parse_article()` construction variable from `dict[str, Any]` to `ArticleRecord`. Same for `article_to_csl()` → `CslJsonRecord`.

**Parallélisation**: 3 parallel agents:
1. Agent A: `DownloadSource` + `download.py` (incl. `PmcResult` removal)
2. Agent B: `DiffResult` + `diff.py` + `AuditEvent` + `audit.py`
3. Agent C: `SearchCacheEntry` + `search.py` + `parse.py` construction types + `cite.py` return type

**Critères de complétion**:
- [ ] All new TypedDicts defined in `types.py`
- [ ] `PmcResult` dataclass removed, replaced by `DownloadSource`
- [ ] Function signatures updated across all modules
- [ ] `parse_article()` and `article_to_csl()` use typed construction
- [ ] All existing tests pass
- [ ] `ruff check` clean

---

## Phase 4 — Replace Hand-Rolled Arg Parsing with `argparse`

**Objectif**: Replace 10 hand-rolled argument parsers (~289 lines total) with `argparse`. Zero new dependencies (stdlib).

**Dépendances**: Phase 3 (types are stable).

### Architecture

Each module keeps its library function unchanged. Only `main(argv)` functions change.

```python
# cli.py — new dispatcher
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pm", description="PubMed CLI tools")
    sub = parser.add_subparsers(dest="command")
    # Each subcommand registers its parser
    return parser
```

### Important: Error message format

argparse produces different error format than hand-rolled parsers:
- Hand-rolled: `"Error: Unknown option: --foo"` (exit 1 or 2, inconsistent)
- argparse: `"error: unrecognized arguments: --foo"` (always exit 2)

**Decision**: Accept argparse's default format and standardize on exit code 2 for usage errors. Update any tests that assert on specific error message text (~16 occurrences across test files).

### Steps (refactoring-under-green):

1. Verify all tests pass.
2. For each module, in order of complexity:
   - Replace the hand-rolled `while`/`for` arg loop with `argparse.ArgumentParser`
   - argparse handles `--flag=value` natively (currently inconsistent across modules)
   - Update tests that check stderr error messages to match argparse format
3. Verify all tests pass after each module migration.

**Migration order** (simplest first):
1. `fetch.py` (2 flags: --verbose)
2. `parse.py` (3 flags: --verbose, --csl)
3. `refs.py` (2 flags + positional files)
4. `cite.py` (2 flags + positional PMIDs)
5. `audit.py` (2 flags)
6. `search.py` (3 flags + positional query)
7. `diff.py` (3 flags + 2 positional)
8. `collect` in cli.py (4 flags + positional query)
9. `filter.py` (8 flags)
10. `download.py` (11 flags)

**Parallélisation**:
- Batch 1 (parallel, 3 agents): fetch + parse + refs
- Batch 2 (parallel, 3 agents): cite + audit + search
- Batch 3 (parallel, 3 agents): diff + collect + filter
- Batch 4 (single agent): download (most complex, 11 flags)

**Critères de complétion**:
- [ ] All 10 `main()` functions use `argparse`
- [ ] `--flag=value` works consistently everywhere
- [ ] `--help` output is clean and consistent
- [ ] No hand-rolled while/for arg loops remain
- [ ] Error exit codes standardized to 2
- [ ] All existing tests pass (updated for argparse error format)
- [ ] `ruff check` clean

---

## Review Gate 2: `/adversarial-review`

After Phase 4, review the full refactored CLI layer + type system before the riskiest phase.

---

## Phase 5 — Real Streaming with `ET.iterparse`

**Objectif**: Replace the fake `parse_xml_stream()` with true incremental XML parsing. O(1) memory per article.

**Dépendances**: Phases 2+ (utilities in place), Phase 4 (CLI clean).

**This is the riskiest phase** — it changes the parsing core.

### Steps (refactoring-under-green):

Existing golden file tests (`test_csl_json.py:test_existing_golden_files_still_pass`, `test_csl_json.py:test_golden_files_match`) and `parse_xml_stream` tests in `test_parse.py` are the safety net. The current `parse_xml_stream` literally calls `parse_xml` internally, so they produce identical output today.

1. Verify all tests pass.
2. Rewrite `parse_xml_stream()`:
   ```python
   def parse_xml_stream(input_stream: IO[str] | IO[bytes]) -> Iterator[ArticleRecord]:
       """Parse PubMed XML from a stream, yielding article dicts incrementally."""
       for event, elem in ET.iterparse(input_stream, events=("end",)):
           if elem.tag == "PubmedArticle":
               yield parse_article(elem)
               elem.clear()
   ```
   Note: `ET.iterparse` works with file-like objects (`IO[str]`/`IO[bytes]`). `parse_article(elem)` only accesses the element's own subtree via `.find()`/`.findall()` — no parent context needed. `elem.clear()` after yield is safe.
3. Keep `parse_xml()` using `ET.fromstring` for string input (no change).
4. Update `parse_xml_stream_csl()` to delegate to the new streaming path.
5. Run all golden file tests — output must be byte-identical.
6. Verify all tests pass.

**Optional enhancement**: Write a memory regression test that processes N articles and asserts peak memory stays below a threshold. This is the one genuinely new test for this phase.

**Parallélisation**: Single agent (core change, must be sequential).

**Critères de complétion**:
- [ ] `parse_xml_stream()` uses `ET.iterparse`
- [ ] `parse_xml_stream_csl()` uses streaming path
- [ ] All golden file tests pass
- [ ] All edge case tests pass
- [ ] All existing tests pass
- [ ] `ruff check` clean
- [ ] Memory usage is O(1) per article (no full XML materialization)

---

## Final Review Gate: `/adversarial-review`

Full codebase review. Must pass with **0 CRITICAL, 0 MAJOR** on the simplification axis.

---

## Out of Scope

- **Streaming fetch→parse pipeline** (fetch yields batches, parse consumes incrementally): **MAJOR finding (M1) from review, explicitly deferred.** Requires API design changes beyond refactoring. Noted in `todos.md` for future work.
- **Cache double-parse on read** (M9 from review): Performance optimization, not simplification. Defer to benchmarking phase. Could be addressed opportunistically in Phase 2.3 if the `cached_batch_fetch` design makes it natural.
- **lxml**: Performance optimization, not simplification. Consider only if measured.
- **click/typer/Pydantic**: Not justified for this codebase.
- **Thread safety for HTTP client**: Low risk, defer unless concurrency is extended.
- **`find_pm_dir()` walking parent directories**: Behavioral change, not refactoring.
- **MINOR findings** (m1-m12 from review): Not in scope but may be addressed opportunistically (m1/audit_log mutation is addressed in Phase 2.3).

---

## Summary

| Phase | Description | Est. Lines Changed | Parallel Agents |
|-------|-------------|-------------------|-----------------|
| 0 | Delete dead code | -8 | 1 |
| 1 | Unify cache_dir/pm_dir | -50 (src) -28 (tests) | 3+1 |
| 2 | Extract shared utilities | -80 +60 (new modules) | 1+1+1+2 |
| — | **Review Gate 1** | — | 3 |
| 3 | TypedDicts for implicit schemas | +60 (types) ~0 (net) | 3 |
| 4 | argparse migration | -150 (net, replacing ~289 lines of parsing) | 3+3+3+1 |
| — | **Review Gate 2** | — | 3 |
| 5 | Real streaming (iterparse) | -10 (net) | 1 |
| — | **Final Review** | — | 3 |
| **Total** | | **~250 net reduction (source)** | |
