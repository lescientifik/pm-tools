---
description: Phased TDD roadmap for 6 UX improvements from the second pm CLI audit (JSONL stdin unification, TTY detection, init idempotency, --count, help examples, verbose counts).
---

# Roadmap: UX Fixes v2

**Objectif:** Fix 6 ergonomic issues found during a second hands-on audit of `pm`, covering JSONL stdin interoperability, TTY detection, and quality-of-life improvements.

No spec file — requirements come from the UX audit conversation and user decisions.

The 6 fixes:

1. Unify JSONL stdin acceptance for `fetch` and `cite` (Phase 1 — HIGH)
2. Detect TTY on stdin for `parse` — show usage instead of blocking (Phase 2 — MEDIUM)
3. `pm init` idempotent when `.pm/` already exists (Phase 3 — LOW)
4. Add `--count` flag to `collect` and `filter` (Phase 3 — LOW)
5. Fix misleading pipeline example in `pm download --help` (Phase 3 — LOW)
6. `-v` on search/collect shows total server-side result count (Phase 3 — LOW)

---

## Phase 1 — JSONL stdin unification (HIGH)

**Objectif:** Make `fetch` and `cite` accept JSONL on stdin (like `download` already does).

**Parallélisation:** Single OPUS agent — `fetch` and `cite` changes are near-identical and share the new utility function.

**Files:** `src/pm_tools/io.py`, `src/pm_tools/fetch.py`, `src/pm_tools/cite.py`, `tests/test_io.py`, `tests/test_fetch.py`, `tests/test_cite.py`

**Context:** `download.py` (lines 674-706) already auto-detects JSONL vs plain PMIDs on stdin. `fetch.py` (lines 191-195) and `cite.py` (lines 147-151) read stdin as raw lines and pass them to `validate_pmid()`, which rejects anything non-numeric.

**Design:** Extract a shared utility in `io.py` that `fetch` and `cite` use. `download.py` is **NOT refactored** — it needs the full JSONL dict (pmcid, doi) and has its own richer logic that cannot be replaced by a PMID-only extractor. Instead, extract a small helper `detect_input_format()` that all three can share for format detection only:

```python
def detect_input_format(first_line: str) -> Literal["jsonl", "plain"]:
    """Detect whether input lines are JSONL or plain PMIDs from first non-empty line."""

def read_pmids_from_lines(lines: Iterable[str]) -> list[str]:
    """Extract PMIDs from lines that may be plain PMIDs or JSONL.

    Auto-detects format from first non-empty line (strips whitespace before parsing):
    - If it parses as a JSON dict with a 'pmid' key → JSONL mode, extract pmid from each line
    - Otherwise → plain PMID mode (one PMID per line, stripped)

    Returns a list of PMID strings (not validated — caller validates).
    Emits a warning to stderr if JSONL is detected but lines have no 'pmid' field.
    """
```

**TDD Steps:**

- **RED:**
  - Test `read_pmids_from_lines(["12345", "67890"])` → `["12345", "67890"]` (plain mode)
  - Test `read_pmids_from_lines(['{"pmid": "12345", "title": "X"}'])` → `["12345"]` (JSONL mode)
  - Test `read_pmids_from_lines(["", "  ", "12345"])` → `["12345"]` (skips blanks)
  - Test `read_pmids_from_lines(['  {"pmid": "12345"}  '])` → `["12345"]` (strips whitespace before JSON parse)
  - Test `read_pmids_from_lines(['{"no_pmid": true}'])` → `[]` with warning on stderr (JSONL without pmid field)
  - Test `read_pmids_from_lines(['{"pmid": "111"}', 'not json'])` → `["111"]` (JSONL mode committed, non-JSON lines skipped with warning)
  - Test `read_pmids_from_lines(['12345', '{"pmid": "67890"}'])` → `["12345", '{"pmid": "67890"}']` (plain mode committed from first line, later JSON lines returned as-is — caller's validate_pmid will reject them)
  - Test `read_pmids_from_lines([])` → `[]`
  - Test `read_pmids_from_lines(['{"pmid": "123"', '{"pmid": "456"}'])` → first line is truncated JSON, fails to parse → plain mode committed, both lines returned as raw strings
  - Integration test: `echo '{"pmid":"41875885"}' | pm fetch` succeeds (currently fails with `Error: Invalid PMID`)
  - Integration test: `echo '{"pmid":"41875885"}' | pm cite` succeeds (currently fails with `Error: Invalid PMID`)
  - Integration test: `pm collect "X" --max 1 | pm fetch` works (full pipeline)
  - Integration test: `pm collect "X" --max 1 | pm cite` works (full pipeline)

- **GREEN:**
  1. Add `detect_input_format()` and `read_pmids_from_lines()` to `io.py`. Strip whitespace from each line before JSON parsing (consistent with existing `read_jsonl()` behavior at io.py:38).
  2. In `fetch.py` main(), replace lines 191-195:
     ```python
     # Before
     if not pmids and not sys.stdin.isatty():
         for line in sys.stdin:
             stripped = line.strip()
             if stripped:
                 pmids.append(stripped)
     # After
     if not pmids and not sys.stdin.isatty():
         pmids = read_pmids_from_lines(sys.stdin)
     ```
  3. Same change in `cite.py` main() lines 147-151.

- **REFACTOR:** Optionally have `download.py` use `detect_input_format()` for its format detection (line 677), but keep download's own JSONL processing for the full-dict path. This is a nice-to-have, not required.

**Note on exit codes:** The previous audit reported `pm fetch` returning exit 0 on invalid PMIDs. Code review shows `fetch.py:206-208` correctly returns 1 on `ValueError` from `validate_pmid()`, and `cli.py:169` (`sys.exit(result or 0)`) correctly propagates it. The observed exit 0 was likely a shell/uv-run artifact. After this phase, JSONL input will be parsed correctly, making the invalid-PMID path unreachable for JSONL input. No separate exit code fix is needed — but the completion criteria include a verification test.

**Critères de complétion:**
- [ ] `pm collect "X" --max 1 | pm fetch` works (JSONL stdin → XML output)
- [ ] `pm collect "X" --max 1 | pm cite` works (JSONL stdin → CSL-JSON output)
- [ ] `echo '{"pmid":"41875885"}' | pm fetch` outputs XML
- [ ] `echo '{"pmid":"41875885"}' | pm cite` outputs CSL-JSON
- [ ] `pm fetch not-a-pmid` exits with code 1 (verified, not fixed — already works)
- [ ] Plain PMID stdin still works: `echo 41875885 | pm fetch`
- [ ] `download.py` still works with both JSONL and plain PMIDs (untouched)
- [ ] All existing tests pass

**Review gate:** `/adversarial-review` after Phase 1 — this phase touches shared I/O and two commands.

---

## Phase 2 — TTY detection for `parse` (MEDIUM)

**Objectif:** When `pm parse` is invoked with no stdin pipe, show usage and exit instead of blocking.

**Parallélisation:** Single agent — small, surgical fix.

**Dépendances:** None (independent of Phase 1).

**Files:** `src/pm_tools/parse.py`, `tests/test_parse.py`

**Context:**
- `fetch.py` already has TTY detection (line 191): `if not pmids and not sys.stdin.isatty()` — when stdin is a TTY and no args, it returns 0 silently. That's fine for fetch since it also takes positional PMIDs.
- `parse.py` has NO TTY detection — it dives straight into `parse_xml_stream(sys.stdin.buffer)` (line 560), which blocks waiting for XML input.

**Exit code decision:** Use exit **1** (same as `search.py:171` for no-query case). `fetch`/`cite` return 0 silently on no input because they also accept positional PMIDs — no input is a valid "nothing to do" case. `parse` takes no positional args — if stdin is a TTY, the user made a mistake and deserves a helpful message + non-zero exit code.

**TDD Steps:**

- **RED:**
  - Test: calling `parse.main([])` with a mocked `sys.stdin.isatty()` returning True → stderr contains usage hint, returns 1.
  - Test: calling `parse.main([])` with stdin piped (isatty False) and valid XML → works as before.
  - Test: calling `parse.main(["--csl"])` with TTY stdin → still shows usage hint (TTY check runs regardless of flags).

- **GREEN:** Add TTY check at the top of `main()`, after argument parsing (between line 556 and 560):
  ```python
  if sys.stdin.isatty():
      print(
          'Usage: pm fetch 41875885 | pm parse\n'
          '       cat pubmed.xml | pm parse\n'
          "hint: use 'pm collect' for a simpler workflow",
          file=sys.stderr,
      )
      return 1
  ```
  Message style follows `search.py:170` (Usage line first, then hint).

- **REFACTOR:** None needed — the change is minimal.

**Critères de complétion:**
- [ ] `pm parse` (no stdin pipe) prints usage hint to stderr and exits 1
- [ ] `pm parse --csl` (no stdin pipe) also prints usage hint
- [ ] `pm fetch 41875885 | pm parse` still works
- [ ] `cat file.xml | pm parse` still works
- [ ] All existing tests pass

---

## Phase 3 — Low-priority quality-of-life improvements (LOW)

**Objectif:** Four small independent fixes that improve polish.

**Parallélisation:** Four parallel OPUS agents — all items are independent.

**Dépendances:** Phase 1 must be complete (3c touches download help which references the JSONL stdin behavior).

### 3a. `pm init` idempotent

**Files:** `src/pm_tools/init.py`, `tests/test_init.py`

**TDD Steps:**

- **RED:**
  - Test: calling `init()` when `.pm/` already exists → returns 0 (currently returns 1).
  - Test: message on stderr says `"already initialized"` (not `"Error:"`).
  - Test: first call still creates everything as before.

- **GREEN:** Replace the FileExistsError handler (init.py:47-49):
  ```python
  except FileExistsError:
      print(f"{PM_DIR}/ already initialized in {Path.cwd()}", file=sys.stderr)
      return 0
  ```
  Also update the docstring (init.py:40-41) from "Returns 0 on success, 1 if .pm/ already exists" to "Returns 0 on success (including if already initialized)".

### 3b. `--count` flag on `collect` and `filter`

**Files:** `src/pm_tools/cli.py` (collect), `src/pm_tools/filter.py`, `tests/test_collect.py`, `tests/test_filter.py`

**Design:** `--count` suppresses normal output and prints a single integer to stdout. Incompatible with `--csl` on collect (argparse mutually exclusive group or manual check).

**TDD Steps:**

- **RED:**
  - Test: `collect_main(["CRISPR", "--max", "5", "--count"])` outputs a single line with an integer on stdout, nothing else.
  - Test: `collect_main(["CRISPR", "--max", "5", "--count", "--csl"])` → argparse error, exit 2 (mutually exclusive).
  - Test: `collect_main(["CRISPR", "--max", "5", "--count", "-v"])` → integer on stdout, verbose progress on stderr.
  - Test: `filter` with `--count --year 2026` on JSONL input → outputs just the count.
  - Test: `--count` combined with `-v` on filter → count on stdout, breakdown on stderr (both work together).
  - Test: `filter` with `--count` and `.pm/` present → audit log still fires with correct input/output counts.

- **GREEN:**
  - `collect`: Add `--count` flag in a mutually exclusive group with `--csl`:
    ```python
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--csl", action="store_true", help="Output CSL-JSON instead of ArticleRecord")
    output_group.add_argument("--count", action="store_true", help="Print result count instead of articles")
    ```
    In `collect_main()`, replace the streaming loop (cli.py:82-84) with:
    ```python
    count = 0
    for article in parse.parse_xml_stream(io.BytesIO(xml.encode("utf-8"))):
        count += 1
        if not args.count:
            output = parse.format_article(article, csl=args.csl)
            print(json.dumps(output, ensure_ascii=False))
    if args.count:
        print(count)
    ```
    This counts in the existing loop without buffering. The full fetch+parse pipeline still runs; only stdout output changes.

  - `filter`: `--count` integrates with the existing `verbose or audit` path — not a separate code path. In `filter.py:main()`, the `if parsed.verbose or detected_pm_dir is not None` branch (lines 447-472) already materializes the input list and computes `result`. With `--count`, replace the article-printing loop (line 451-452) with `print(len(result))`:
    ```python
    if parsed.count:
        print(len(result))
    else:
        for article in result:
            print(json.dumps(article, ensure_ascii=False))
    ```
    For the streaming path (no `-v`, no `.pm/`, lines 473-476), same pattern:
    ```python
    if parsed.count:
        print(sum(1 for _ in filtered))
    else:
        for article in filtered:
            print(json.dumps(article, ensure_ascii=False))
    ```
    Audit logging and verbose breakdown are unaffected — they happen before the output decision.

### 3c. Fix download help pipeline example

**Files:** `src/pm_tools/download.py`, `tests/test_download.py`

**TDD Steps:**

- **RED:** Test that `pm download --help` output does NOT contain `pm search "CRISPR" | pm fetch | pm parse | pm download`.
- **GREEN:** Replace the misleading example (download.py:579) with:
  ```
  pm collect "CRISPR" --max 100 | pm download --output-dir ./articles/
  pm search "CRISPR" -n 100 | pm download --output-dir ./articles/
  ```
  These both work because (after Phase 1) both plain PMIDs and JSONL are accepted.

### 3d. Verbose shows server-side result count

**Files:** `src/pm_tools/search.py`, `src/pm_tools/cli.py` (collect verbose)

**Context:** The PubMed E-utilities esearch response XML contains a `<Count>` element with the total number of matches on the server, independent of `retmax`. Currently `search()` extracts PMIDs from `<Id>` elements but ignores `<Count>`.

**TDD Steps:**

- **RED:**
  - Test: `search()` with `verbose=True` prints a message containing the total count to stderr. Mock the API response to include `<Count>5000</Count>` with `retmax=10` → stderr should contain `"5000 found, returning 10"` or similar.
  - Test: when total == returned (small result set), message is simpler: `"Found 3 results"`.

- **GREEN:**
  In `search()` (search.py), after parsing the XML response:
  ```python
  count_elem = root.find(".//Count")
  total = int(count_elem.text) if count_elem is not None and count_elem.text else len(pmids)
  if verbose:
      if total > len(pmids):
          print(f"Found {total} results, returning {len(pmids)}", file=sys.stderr)
      else:
          print(f"Found {total} results", file=sys.stderr)
  ```
  For the cached path (line 71-88), the total isn't available in the cache entry. Two options:
  - **(A)** Store `total` in `SearchCacheEntry` and display it on cache hit.
  - **(B — RECOMMENDED)** Only show the count on fresh API calls. On cache hit, the existing `"using cached search from ..."` message is sufficient.

  Choose **(B)** — simpler, no cache schema change.

  **Verbose message deduplication (DECIDED):** `collect_main()` (cli.py:57-58) prints `Searching PubMed: "..." (max N)...` before calling `search()`. `search()` (search.py:91-92) also prints `Searching PubMed for "..."...` when verbose. This results in two redundant search messages on stderr.

  **Fix:** Replace `search()`'s verbose message (search.py:91-92) with **only** the count line. Remove the `Searching PubMed for "..."...` message entirely from `search()`. The result:
  - `pm search -v "CRISPR" -n 5` → stderr shows: `Found 15234 results, returning 5` (the search.main() caller does NOT print a "starting" message, which is fine — the result count is informative enough for the low-level command)
  - `pm collect -v "CRISPR" --max 5` → stderr shows: `Searching PubMed: "CRISPR" (max 5)...` then `Found 15234 results, returning 5` (collect provides context, search provides count — no duplication)

  ```python
  # search.py — replace line 91-92 with:
  # (removed: print(f'Searching PubMed for "{query}"...', file=sys.stderr))
  # After root = ET.fromstring(...) and pmids extraction:
  if verbose:
      if total > len(pmids):
          print(f"Found {total} results, returning {len(pmids)}", file=sys.stderr)
      else:
          print(f"Found {total} results", file=sys.stderr)
  ```

**Critères de complétion (Phase 3, all items):**
- [ ] `pm init` in already-initialized dir → exit 0, `"already initialized"` message
- [ ] `pm collect "X" --max 5 --count` → prints just a number
- [ ] `pm collect "X" --count --csl` → argparse error, exit 2
- [ ] `pm collect "X" --max 5 --count -v` → integer on stdout, verbose on stderr
- [ ] `pm filter --count --year 2026 < results.jsonl` → prints just a number
- [ ] `pm filter --count -v < results.jsonl` → integer on stdout, breakdown on stderr
- [ ] `pm download --help` shows correct pipeline examples
- [ ] `pm search "CRISPR" -v -n 5` shows `"Found N results, returning 5"` on stderr (on fresh API call)
- [ ] All existing tests pass

**Review gate:** `/adversarial-review` after Phase 3 — final review on full changeset.

---

## Out of scope

- Changing `filter` behavior on 100% malformed input (user excluded from this batch).
- Changing `fetch`/`cite` TTY behavior (already return 0 silently on no input, not a blocker — they accept positional PMIDs so "no input" is a valid "nothing to do" case).
- Adding `--pretty` or `--tsv` output modes.
- Changing `--max` defaults (10000 vs 100) — intentional design.
- Refactoring `download.py`'s JSONL processing to use shared utilities — download needs the full JSONL dict (pmcid, doi) and has its own richer logic. Only the format detection helper (`detect_input_format`) may optionally be shared.
- Adding `--count` to `pm search` — `wc -l` suffices for plain PMID output, and Phase 3d's verbose count addresses the "how many total?" question.
