---
description: Phased TDD roadmap for 8 UX friction fixes identified in the pm CLI audit.
---

# Roadmap: UX Friction Fixes

**Objectif:** Fix 8 ergonomic issues found during a hands-on audit of `pm`, covering argument consistency, input validation, help formatting, and verbose output quality.

No spec file — requirements come from the UX audit conversation and user decisions.

The 8 fixes:
1. `collect` accepts nargs for query (Phase 1a)
2. `fetch` accepts positional PMIDs (Phase 1b)
3. `download` accepts positional PMIDs (Phase 1b)
4. Validate `--max` rejects 0 and negative (Phase 2)
5. Add `-n` alias for `--max` (Phase 2)
6. Fix `parse` help duplication (Phase 3)
7. `filter -v` with per-filter breakdown (Phase 4)
8. `refs` warning on invalid XML / 0 results (Phase 5)

---

## Phase 1 — Argument consistency (collect nargs + positional PMIDs)

**Objectif:** Make `collect` accept multi-word queries like `search`, and make `fetch`/`download` accept positional PMIDs like `cite`.

**Parallélisation:** Items 1a and 1b are independent — run as **parallel OPUS agents**.

### 1a. `collect` accepts nargs for query

**Files:** `src/pm_tools/cli.py`, `tests/test_collect.py` (new file — follows one-test-file-per-command convention)

**Reference pattern:** `search.py` already uses `query_words` with `nargs="*"` (line 143). Align `collect` to the same pattern.

**TDD Steps:**

- **RED:** Test `collect_main(["CRISPR", "cancer", "--max", "1"])` produces valid output (currently fails with argparse error, exit 2). Test `collect_main([])` prints `"Error: ..."` to stderr and returns 1.
- **GREEN:** In `_build_collect_parser()`, change:
  ```python
  # Before
  parser.add_argument("query", help="PubMed search query")
  # After
  parser.add_argument("query_words", nargs="*", help="PubMed search query")
  ```
  In `collect_main()`, join words: `query = " ".join(parsed.query_words)` and validate non-empty with `print("Error: Query cannot be empty", file=sys.stderr); return 1`.
- **REFACTOR:** Ensure help text and examples still make sense.

**Note:** Exit code changes from 2 (argparse auto-error) to 1 (explicit validation) for empty query. This is intentional — consistent with search.py behavior.

### 1b. `fetch` + `download` accept positional PMIDs

**Files:** `src/pm_tools/fetch.py`, `src/pm_tools/download.py`, `tests/test_fetch.py`, `tests/test_download.py`

**Reference pattern:** `cite.py` (lines 137-144) — positional PMIDs with `nargs="*"`, stdin as **fallback** (only read when no positional args AND stdin is not a TTY).

**TDD Steps:**

- **RED:** Test `fetch.main(["41873355"])` outputs XML (currently fails with argparse error, exit 2). Test `download.main(["41873355", "--dry-run"])` works.
- **GREEN:** Add `parser.add_argument("pmids", nargs="*", help="PMIDs (also reads from stdin)")` to both parsers.

  **Input priority (strict fallback, not merge):**
  - `fetch`: positional PMIDs > stdin. If positional args given, stdin is ignored entirely.
  - `download`: positional PMIDs > `--input FILE` > stdin. If both positional and `--input` are given, error: `"Error: cannot use both positional PMIDs and --input FILE"` (exit 1).

  Positional PMIDs are always treated as **plain PMID strings** (never JSONL). JSONL auto-detection only applies to stdin and `--input FILE`. In `download.main()`, the positional-args branch must bypass the `is_jsonl = lines[0].startswith("{")` auto-detection — feed PMIDs directly to the PMID-to-article conversion path.

- **REFACTOR:** Update epilog examples to show positional usage.

**Critères de complétion:**
- [ ] `pm collect CRISPR cancer --max 1` works
- [ ] `pm collect` (no args) prints `"Error: ..."` to stderr, exits 1
- [ ] `pm fetch 41873355` outputs XML
- [ ] `pm download 41873355 --dry-run` works
- [ ] `pm download 41873355 --input file.txt` → error about conflicting inputs
- [ ] Stdin still works for all three commands when no positional args
- [ ] All existing tests still pass

---

## Phase 2 — `--max` validation + `-n` alias

**Objectif:** Reject invalid `--max` values and add `-n` as a short alias.

**Parallélisation:** Single agent — both changes touch the same argument definitions.

**Dépendances:** Phase 1a must be complete (both phases touch `cli.py`'s collect parser).

**Files:** `src/pm_tools/search.py`, `src/pm_tools/cli.py` (collect), `tests/test_search.py`, `tests/test_collect.py`

**Note:** `search` defaults `--max` to 10000, `collect` defaults to 100. These defaults are intentional and must NOT be unified.

**TDD Steps:**

- **RED:**
  - Test `search.main(["CRISPR", "--max", "0"])` returns exit code 2 with error on stderr (argparse type error).
  - Test `search.main(["CRISPR", "--max", "-5"])` returns exit code 2.
  - Test `search.main(["CRISPR", "-n", "3"])` is equivalent to `--max 3`.
  - Same tests for `collect_main`.
- **GREEN:** Custom argparse type function:
  ```python
  def positive_int(value: str) -> int:
      """Argparse type: positive integer."""
      try:
          n = int(value)
      except ValueError:
          raise argparse.ArgumentTypeError(f"expected a positive integer, got '{value}'")
      if n <= 0:
          raise argparse.ArgumentTypeError(f"must be a positive integer, got {n}")
      return n
  ```
  Add to both parsers: `parser.add_argument("-n", "--max", type=positive_int, dest="max_results", ...)`.

  **Important:** Preserve `dest="max_results"` — both `search.py` and `cli.py` reference `parsed.max_results` throughout.

  **Note:** `argparse.ArgumentTypeError` triggers argparse's own error handling, which calls `sys.exit(2)`. The `SystemExit` handler in each `main()` converts this to return code 2. Tests must expect exit code **2**, not 1.

- **REFACTOR:** Define `positive_int` in a shared module. Since `io.py` is for JSONL I/O, create `src/pm_tools/args.py` for shared argparse utilities (just `positive_int` for now). Both `search.py` and `cli.py` import from there.

**Critères de complétion:**
- [ ] `pm search "x" --max 0` → stderr error, exit 2
- [ ] `pm search "x" --max -5` → stderr error, exit 2
- [ ] `pm search "x" -n 3` works
- [ ] `pm collect "x" -n 3` works
- [ ] All existing tests still pass

---

## Phase 3 — Fix `parse` help duplication

**Objectif:** Eliminate the double-listed options in `pm parse --help`.

**Parallélisation:** Single agent — small, surgical fix.

**Files:** `src/pm_tools/parse.py`

**TDD Steps:**

- **RED:** Test that `pm parse --help` output does not contain duplicate `--csl` entries (count occurrences of `--csl` in help text, assert == 1).
- **GREEN:** Split `HELP_TEXT` into two parts following the convention used by every other command (fetch, cite, download, filter):
  - `description`: Short one-line blurb (e.g. `"Parse PubMed XML to JSONL."` + the tip about `pm collect`).
  - `epilog`: Output format documentation + examples. Use `RawDescriptionHelpFormatter`.

  Remove the manual "Options:" block entirely — argparse generates it from `add_argument` calls.
- **REFACTOR:** Verify the help layout matches the style of other commands (description → options → epilog).

**Critères de complétion:**
- [ ] `pm parse --help` shows each option exactly once
- [ ] Help still includes output format documentation and examples (now in epilog)
- [ ] Layout follows the same pattern as `pm fetch --help`, `pm cite --help`
- [ ] All existing tests pass

---

## Phase 4 — `filter -v` with per-filter breakdown

**Objectif:** When `-v` is used, show how many articles survive each filter stage. **Replaces** the current `"{N} articles passed filters"` message entirely.

**Parallélisation:** Single agent — touches filter internals.

**Files:** `src/pm_tools/filter.py`, `tests/test_filter.py`

**Target output:**
```
200 read
  → 180 after --year 2024-
  → 5 after --has-abstract
5/200 passed (195 excluded)
```

**TDD Steps:**

- **RED:** Write tests for a new `filter_with_breakdown()` function that returns both the filtered list and a steps list:
  ```python
  # Returns: (filtered_articles, steps)
  # steps = [("--year 2024-", 180), ("--has-abstract", 5)]
  ```
  Test cases:
  - 0 active filters → steps is empty, all articles pass
  - 1 filter → single step
  - Multiple filters → steps in application order. **Only the 6 CLI-exposed filters are relevant:** year → journal → journal_exact → author → has_abstract → has_doi (matching the order in `filter_articles` internals). The 3 API-only filters (pmid, title, min_authors) are not exposed by `_build_parser()` and will never appear in CLI breakdown output.
  - Test the formatted stderr string for each case
- **GREEN:** Create `filter_with_breakdown()` that applies filters **sequentially, one at a time**, in the same order as `filter_articles()`. Each step calls `filter_articles()` with a single keyword argument:
  ```python
  active_filters: list[tuple[str, dict[str, Any]]] = []
  if year is not None:
      active_filters.append((f"--year {year}", {"year": year}))
  if has_abstract:
      active_filters.append(("--has-abstract", {"has_abstract": True}))
  # ... etc, in the same order as filter_articles internals

  remaining = list(articles)
  steps: list[tuple[str, int]] = []
  for label, single_kwarg in active_filters:
      remaining = list(filter_articles(iter(remaining), **single_kwarg))
      steps.append((label, len(remaining)))
  ```
  In `main()`, replace the old verbose message with the formatted breakdown.

  **Performance:** Each step materializes the list. For typical workloads (<100k articles, 2-3 filters), this is negligible. The non-verbose path and the streaming path (when no `.pm/` dir and no `-v`) remain untouched.

  **Audit log:** The audit log entry schema (`{"op": "filter", "input": N, "output": M, ...}`) is **unchanged**. Per-step data is stderr-only and NOT written to audit log, to avoid breaking `pm audit` and PRISMA report parsing.

- **REFACTOR:** Clean up `filter_articles_audited` — it can delegate to `filter_with_breakdown` internally, but must preserve the `criteria` dict construction and `audit_log()` call with the same schema (`{"op": "filter", "input": N, "output": M, "excluded": N-M, "criteria": {...}}`).

**Critères de complétion:**
- [ ] `filter -v` with 0 active filters → `N read\nN/N passed (0 excluded)`
- [ ] `filter -v` with 1 filter → shows the step
- [ ] `filter -v` with multiple filters → shows each step with arrow, in correct order
- [ ] Old `"{N} articles passed filters"` message is gone
- [ ] Audit log entry unchanged (same schema, same keys)
- [ ] Streaming (non-verbose, no .pm/ dir) path unchanged
- [ ] All existing tests pass

---

## Phase 5 — `refs` warning on invalid XML / 0 results

**Objectif:** Emit a stderr warning when `refs` finds nothing or gets bad XML.

**Parallélisation:** Single agent — small change.

**Files:** `src/pm_tools/refs.py`, `tests/test_refs.py`

**Exit code policy (decided):** exit **0** with warning. Unix-conventional: no match is not an error (grep returns 1, but refs is more like a parser than a search tool — 0 is safer).

**TDD Steps:**

- **RED:**
  - Test: piping invalid XML → stderr contains `"warning: could not parse XML"`, exit 0.
  - Test: piping valid XML with no `<ref-list>` → stderr warning `"warning: no references found"`.
  - Test: piping valid NXML with refs → no warning (existing behavior preserved).
  - Test: multi-file with one invalid XML + one valid with refs → warning for the bad file, refs output for the good one, exit 0.
- **GREEN:** Change `extract_refs()` to signal parse errors without changing its return type:
  - Have `extract_refs()` raise `ET.ParseError` on bad XML instead of catching it silently. The `try/except ET.ParseError: return []` block (line 24-26) is removed. `main()` catches the exception, emits `"warning: could not parse XML"` on stderr, and continues (for multi-file: per-file warning, continue to next file).

  For "parsed OK but 0 refs": check in `main()` after collecting all refs:
  ```python
  if not unique_refs and not had_error:
      print("warning: no references found", file=sys.stderr)
  ```

**Critères de complétion:**
- [ ] Invalid XML → stderr warning, exit 0
- [ ] Valid XML, no refs → stderr warning, exit 0
- [ ] Valid NXML with refs → no warning (existing behavior)
- [ ] `extract_refs()` return type unchanged (still `list[str]`)
- [ ] All existing tests pass

---

## Review Gate

After all 5 phases: run `/adversarial-review` on the full changeset.

---

## Out of scope

- Changing `--max` defaults (10000 vs 100) — intentional design.
- Adding verbose/breakdown to `audit` or other commands.
- Changing `download` `--input FILE` behavior (except mutual exclusivity with positional args).
- Any new subcommands or features.
- PMID format validation on positional args (could be a follow-up).
- Unifying "no input" behavior across commands (`fetch`/`cite` silently exit 0, `download`/`refs` error — this is pre-existing and not introduced by this roadmap).
