# Plan: NXML preference in `pm download` + new `pm refs` command

## Overview

Two features driven by issue #9:

**Feature A**: `pm download` extracts NXML by default from tgz archives (fallback PDF).
Add `--pdf` flag to force PDF extraction behavior.

**Feature B**: New `pm refs` command extracts cited PMIDs from NXML files (JATS `<ref-list>`).

Both features compose naturally:
```bash
# Download NXML (default) → extract cited PMIDs
pm search "CRISPR" | pm fetch | pm parse | pm download --output-dir ./articles/
pm refs ./articles/*.nxml
```

---

## Feature A: NXML-first download

### Background

Currently `pm download` extracts only the PDF from tgz archives (`_extract_pdf_from_tgz()`),
discarding the NXML. Issue #9 observes that NXML is more valuable for AI-agent workflows:
structured text, sections, references with PMIDs — all machine-readable.

**Critical gap in current code**: `pmc_lookup()` (download.py:71-118) prefers PDF over tgz
when both formats are available. This means articles with both PDF and tgz links never reach
the tgz extraction path — `pmc_lookup()` returns `PmcResult(format="pdf")` and the tgz
(which contains NXML) is never downloaded. This must be reversed.

### Design decisions

1. **`pmc_lookup()` must prefer tgz**: When both pdf and tgz links are available,
   `pmc_lookup()` now returns the tgz link. Rationale: tgz contains both NXML *and* PDF,
   so choosing tgz never loses data — we can extract either format downstream. Choosing
   PDF-only loses the NXML permanently. This is a behavior change that affects existing tests.

2. **Default behavior changes**: `pm download` now extracts NXML from tgz archives by default,
   falling back to PDF if no NXML is found. The `--pdf` flag restores the old PDF-only behavior.

3. **File naming**: Output files are named `{PMID}.nxml` for NXML and `{PMID}.pdf` for PDF.
   When `--pdf` is used, or when only PDF is available (direct pdf link, no tgz), output is `.pdf`.

4. **Direct PDF links**: When PMC returns a direct PDF link (no tgz), there is no NXML available.
   The download proceeds as before, saving a `.pdf` file. No error — this is expected.

5. **tgz extraction logic**: New `_extract_nxml_from_tgz()` function parallel to
   `_extract_pdf_from_tgz()`. Similar heuristic: prefer the `.nxml` file whose name
   contains the PMCID, otherwise pick the largest.

6. **`verify_pdf`**: Only applies when actually saving a PDF (either `--pdf` mode or
   PDF-direct sources). Skip verification for NXML files.

7. **Manifest**: Manifest entries use the actual file extension (`.nxml` or `.pdf`),
   determined at write time from the actual file saved. Not hard-coded to `.pdf`.

8. **Overwrite check**: When checking for existing files, must check the correct
   extension. In default mode, check for `{PMID}.nxml`; in `--pdf` mode, check for
   `{PMID}.pdf`. When an existing file has a *different* extension from what would be
   written (e.g., `.pdf` exists but we'd write `.nxml`), the new file is written alongside
   (no conflict — different filename).

### API changes

- `pmc_lookup()`: reversed preference — prefers tgz over pdf when both available
- `_extract_nxml_from_tgz(content: bytes, pmcid: str = "") -> bytes | None` — new function
- `_download_one()` gains `prefer_pdf: bool` parameter (default `False`)
- `download_pdfs()` gains `prefer_pdf: bool` parameter (default `False`)
- `download_pdfs()` returns actual output extension in manifest entries
- CLI `pm download` gains `--pdf` flag
- `ThreadPoolExecutor.submit()` call updated to pass `prefer_pdf` to `_download_one()`

### Behavior matrix

| PMC format | --pdf flag | Action | Output file |
|------------|-----------|--------|-------------|
| tgz | no | Extract NXML, fallback PDF | `{PMID}.nxml` or `{PMID}.pdf` |
| tgz | yes | Extract PDF only (current behavior) | `{PMID}.pdf` |
| pdf (direct) | no | Download PDF directly | `{PMID}.pdf` |
| pdf (direct) | yes | Download PDF directly | `{PMID}.pdf` |
| unpaywall | any | Download PDF directly | `{PMID}.pdf` |

### Existing tests that require updates

The following tests assert the *old* behavior and must be updated:

| Test | File:Line | Current assertion | New assertion |
|------|-----------|-------------------|---------------|
| `test_both_formats_prefers_pdf` | test_download.py:837 | `result.format == "pdf"` | `result.format == "tgz"` (rename to `test_both_formats_prefers_tgz`) |
| `test_tgz_source_no_pdf_counted_as_failed` | test_download.py:1281 | archive with only NXML → failed | archive with only NXML → downloaded as `.nxml` (move to new NXML test class) |
| `test_tgz_failure_progress_callback` | test_download.py:1410 | only-NXML archive → `tgz_no_pdf` reason | only-NXML archive → `downloaded` status (move to new NXML test class) |

These tests are updated in Phase 10.1b (`_download_one()` NXML preference phase, RED step).

---

## Feature B: `pm refs` command

### Design

`pm refs` reads one or more NXML files and extracts cited PMIDs from the
JATS `<ref-list>` section.

**JATS reference structure** (from NXML):
```xml
<ref-list>
  <ref id="ref1">
    <mixed-citation>
      ...
      <pub-id pub-id-type="pmid">12345678</pub-id>
    </mixed-citation>
  </ref>
  <ref id="ref2">
    <element-citation>
      ...
      <pub-id pub-id-type="pmid">87654321</pub-id>
      <pub-id pub-id-type="doi">10.1234/example</pub-id>
    </element-citation>
  </ref>
</ref-list>
```

**Output**: One PMID per line on stdout (for piping into `pm fetch`).

**Usage**:
```bash
pm refs article.nxml                   # Extract PMIDs from one file
pm refs *.nxml                         # Multiple files
pm refs --doi article.nxml             # Extract DOIs instead of PMIDs
cat article.nxml | pm refs             # From stdin
```

Note: directory traversal (`pm refs dir/`) is out of scope for this plan.
Shell glob (`pm refs dir/*.nxml`) handles this use case with explicit intent.

### API

- `extract_refs(nxml_content: str, id_type: str = "pmid") -> list[str]` — core function
- `main(args)` — CLI entry point

### Edge cases

- No `<ref-list>` in NXML: return empty list (exit 0)
- `<pub-id>` without `pub-id-type="pmid"`: skip
- Duplicate PMIDs across refs: deduplicate (preserve order)
- Invalid XML: log warning, continue to next file
- Whitespace-only PMID text: skip (don't emit blank lines)

---

## Test fixtures

### NXML fixture file: `fixtures/sample.nxml`

A minimal but realistic JATS NXML file used across test phases. Contains:
- `<front>` with PMID and PMCID article-ids
- `<body>` with one section (minimal)
- `<back>` with `<ref-list>` containing 3 refs:
  - Ref with both PMID and DOI (`mixed-citation`)
  - Ref with PMID only (`element-citation`)
  - Ref with DOI only, no PMID (should be skipped by default `pm refs`)

### Golden file: `fixtures/golden/sample-refs-pmids.txt`

Expected output of `pm refs fixtures/sample.nxml`:
```
11111111
22222222
```

### Golden file: `fixtures/golden/sample-refs-dois.txt`

Expected output of `pm refs --doi fixtures/sample.nxml`:
```
10.1038/example
10.1000/other
```

These fixtures are created in Phase 10.3 (before writing `extract_refs` tests).

---

## TDD Phases

### Phase 10.0 — `_extract_nxml_from_tgz()` (pure function, TDD)

**Deliverable**: New function to extract NXML from tgz archives.

**RED — Tests to write first** (`tests/test_download.py`, new class `TestExtractNxmlFromTgz`):
- [ ] Test: archive with NXML in subdirectory (`PMC12345/paper.nxml`) -> returns content
- [ ] Test: archive with multiple NXML files -> prefers one matching PMCID
- [ ] Test: archive with multiple NXML files, no PMCID match -> returns largest
- [ ] Test: archive with no NXML files (only PDF/images) -> returns None
- [ ] Test: invalid data (not a tgz) -> returns None
- [ ] Test: empty archive -> returns None
- [ ] Test: empty NXML file (0 bytes) -> returns None
- [ ] Test: member > MAX size guard -> skipped

**GREEN — Implementation**:
- Add `_extract_nxml_from_tgz()` to `download.py`
- Parallel structure to `_extract_pdf_from_tgz()` but matching `.nxml` extension
- Same security: `extractfile()` only, no disk writes, size guard

**REFACTOR**:
- Extract shared logic between `_extract_pdf_from_tgz()` and `_extract_nxml_from_tgz()`
  into a common `_extract_member_from_tgz(content, extension, pmcid)` helper if duplication
  is significant (>10 lines duplicated). If not, keep them separate — premature abstraction
  is worse than a little duplication.

**Success criteria**:
- [ ] All tests pass (new + existing)
- [ ] `uv run ruff check src/ tests/`

**Commit**: `feat: add _extract_nxml_from_tgz()`

**Dependencies**: None

---

### Phase 10.1a — `pmc_lookup()` prefers tgz (TDD)

**Deliverable**: `pmc_lookup()` returns tgz when both formats are available.

**RED — Tests to write first**:
- [ ] Test: update `test_both_formats_prefers_pdf` → rename to `test_both_formats_prefers_tgz`,
      assert `result.format == "tgz"` (was `"pdf"`)
- [ ] Test: tgz-only still returns tgz (existing test, should still pass)
- [ ] Test: pdf-only still returns pdf (existing test behavior unchanged)

**GREEN — Implementation**:
- In `pmc_lookup()`, swap the preference order:
  ```python
  # Before: if pdf_href: return pdf; if tgz_href: return tgz
  # After:  if tgz_href: return tgz; if pdf_href: return pdf
  ```
- Update docstring: "Prefers tgz over pdf when both are available (tgz contains NXML + PDF)."

**REFACTOR**:
- Update log messages: `"found tgz link"` (not `"found tgz link (no pdf available)"`)

**Success criteria**:
- [ ] Updated test passes
- [ ] All other `pmc_lookup` tests still pass
- [ ] `uv run ruff check src/ tests/`

**Commit**: `feat: pmc_lookup prefers tgz over pdf`

**Dependencies**: None (can run in parallel with Phase 10.0)

---

### Phase 10.1b — `_download_one()` NXML preference (TDD)

**Deliverable**: `_download_one()` extracts NXML by default from tgz, falls back to PDF.

**RED — Tests to write first** (new class `TestDownloadOneNxml`):
- [ ] Test: tgz source, default (prefer_pdf=False), archive has NXML -> saves `{PMID}.nxml`
- [ ] Test: tgz source, default, archive has NXML + PDF -> saves NXML (not PDF)
- [ ] Test: tgz source, default, archive has only PDF (no NXML) -> falls back to `{PMID}.pdf`
- [ ] Test: tgz source, default, archive has neither NXML nor PDF -> failed
- [ ] Test: tgz source, prefer_pdf=True -> extracts PDF (current behavior), saves `{PMID}.pdf`
- [ ] Test: tgz source, prefer_pdf=True, archive has only NXML (no PDF) -> failed
- [ ] Test: pdf direct source (no tgz) -> saves `{PMID}.pdf` regardless of prefer_pdf
- [ ] Test: unpaywall source -> saves `{PMID}.pdf` regardless of prefer_pdf
- [ ] Test: verify_pdf=True skipped when saving NXML (no false positive on NXML content)
- [ ] Test: verify_pdf=True applied on fallback to PDF (NXML not found, PDF extracted)
- [ ] Test: progress callback reports `downloaded` status for NXML download
- [ ] Test: existing `{PMID}.nxml` file is skipped when overwrite=False
- [ ] Test: existing `{PMID}.pdf` does NOT block `{PMID}.nxml` write (different filename)
- [ ] Test: `_download_one()` sets `output_ext` key on returned source dict (`.nxml` or `.pdf`)

**Update existing tests** (backward compatibility):
These tests assumed PDF-only extraction from tgz. They are split in this phase's RED step
(tests written/updated before implementation, then implementation makes them pass):
- [ ] `test_tgz_source_no_pdf_counted_as_failed` (line 1281): Archive with only NXML currently
      expects `failed`. → **Split into two tests**:
      - `test_tgz_nxml_only_extracts_nxml` (default) → `downloaded`, saves `{PMID}.nxml`
      - `test_tgz_nxml_only_prefer_pdf_fails` (`prefer_pdf=True`) → `failed` (preserves original)
- [ ] `test_tgz_failure_progress_callback` (line 1410): Archive with only NXML expects `tgz_no_pdf`.
      → **Split into two tests**:
      - `test_tgz_nxml_only_progress_downloaded` (default) → `downloaded` status
      - `test_tgz_nxml_only_prefer_pdf_progress_failed` (`prefer_pdf=True`) → `tgz_no_pdf`
- [ ] `test_tgz_source_extracts_and_saves_pdf` (line 1252): Archive has *only* PDF (no NXML).
      Fallback to PDF still applies. **No change needed** — verify it still passes.
- [ ] `test_pmc_format_tgz_when_tgz_only` (line 932): Tests `find_pdf_sources` with tgz-only
      fixture. Source dict constructed directly, never calls `_download_one()`. **No change needed**.

**GREEN — Implementation**:
- Add `prefer_pdf: bool` parameter to `_download_one()` signature
- **Overwrite check**: Move `out_file` computation *after* tgz extraction (not before HTTP
  request). For tgz sources when `prefer_pdf is False`:
  1. Download the tgz content
  2. Try `_extract_nxml_from_tgz(content, pmcid)` → if found, `ext = ".nxml"`
  3. If not found, try `_extract_pdf_from_tgz(content, pmcid)` → if found, `ext = ".pdf"`
  4. If neither found, return failed
  5. Compute `out_file = output_dir / f"{pmid}{ext}"`
  6. Check `out_file.exists()` and `overwrite` flag *here* (after format is known)
  7. Save content, set `source["output_ext"] = ext`
  For non-tgz sources and `prefer_pdf=True`: compute `out_file` as `{pmid}.pdf` early
  (current behavior, format is known upfront).
- `verify_pdf` check: apply only when `ext == ".pdf"` (skip for NXML)
- Return `(status, source_dict)` — source_dict gains `"output_ext"` key for manifest

**REFACTOR**:
- Consider extracting the tgz dispatch logic into a small helper if `_download_one()` grows
  beyond ~60 lines of tgz handling.

**Success criteria**:
- [ ] All new tests pass
- [ ] All updated existing tests pass
- [ ] All *unmodified* existing tests still pass
- [ ] `uv run ruff check src/ tests/`

**Commit**: `feat: _download_one extracts NXML by default from tgz`

**Dependencies**: Phase 10.0, Phase 10.1a

---

### Phase 10.2 — `download_pdfs()` and CLI `--pdf` flag (TDD)

**Deliverable**: Public API and CLI updated.

**RED — Tests to write first**:
- [ ] Test: `download_pdfs(prefer_pdf=False)` passes `prefer_pdf=False` to `_download_one()`
- [ ] Test: `download_pdfs(prefer_pdf=True)` passes `prefer_pdf=True` to `_download_one()`
- [ ] Test: `ThreadPoolExecutor` path also passes `prefer_pdf` (max_concurrent > 1)
- [ ] Test: CLI `--pdf` flag sets prefer_pdf=True
- [ ] Test: CLI default (no --pdf) uses prefer_pdf=False
- [ ] Test: `--help` documents `--pdf` flag
- [ ] Test: dry-run message shows "available via pmc" for tgz sources
- [ ] Test: summary counts NXML downloads as "downloaded"
- [ ] Test: manifest entry uses actual file extension (`.nxml` when NXML saved)
- [ ] Test: manifest entry uses `.pdf` when PDF saved (--pdf mode or fallback)

**GREEN — Implementation**:
- `download_pdfs()` gains `prefer_pdf: bool = False` as keyword-only parameter (after `*`)
  to match the existing convention for `verify_pdf`, `max_concurrent`, `manifest`, `pm_dir`
- Pass `prefer_pdf` to `_download_one()` in both sequential and ThreadPoolExecutor paths
- Manifest writes actual extension from `source.get("output_ext", ".pdf")`
- CLI parses `--pdf` flag, passes to `download_pdfs(prefer_pdf=True)`
- Update HELP_TEXT to document `--pdf` (following cli-design-for-agents.md)

**REFACTOR**:
- Review HELP_TEXT for clarity, progressive disclosure, error-teaching style
- Ensure `--pdf` is documented in the right section (Download Options)
- Update `download_pdfs()` docstring: mention NXML-first default behavior
- Update module-level docstring: "Download full-text articles (NXML or PDF)"

**Success criteria**:
- [ ] All tests pass
- [ ] `uv run ruff check src/ tests/`

**Commit**: `feat: download_pdfs prefer_pdf param + CLI --pdf flag`

**Dependencies**: Phase 10.1b

---

### Phase 10.3 — `pm refs` core function + fixtures (TDD)

**Deliverable**: `extract_refs()` function in new `refs.py` module, plus NXML fixture files.

**Fixture setup** (before writing tests):
- [ ] Create `fixtures/sample.nxml` with the reference structure shown in Fixtures section
- [ ] Create `fixtures/golden/sample-refs-pmids.txt` with expected PMID output
- [ ] Create `fixtures/golden/sample-refs-dois.txt` with expected DOI output

**RED — Tests to write first** (`tests/test_refs.py`, new file):
- [ ] Test: NXML with ref-list containing PMIDs -> returns list of PMID strings
- [ ] Test: NXML with mixed-citation and element-citation -> finds PMIDs in both
- [ ] Test: NXML with ref containing DOI and PMID -> returns only PMIDs (default)
- [ ] Test: NXML with ref containing DOI and PMID, id_type="doi" -> returns DOIs
- [ ] Test: NXML with no ref-list -> returns empty list
- [ ] Test: NXML with refs but no pub-id type=pmid -> returns empty list
- [ ] Test: duplicate PMIDs across refs -> deduplicated, order preserved
- [ ] Test: empty string input -> returns empty list
- [ ] Test: invalid XML input -> returns empty list (no crash)
- [ ] Test: whitespace-only PMID text -> skipped (not emitted)
- [ ] Test: golden file `sample-refs-pmids.txt` matches `extract_refs(sample.nxml)`
- [ ] Test: golden file `sample-refs-dois.txt` matches `extract_refs(sample.nxml, "doi")`

**GREEN — Implementation**:
- New file: `src/pm_tools/refs.py`
- Use `xml.etree.ElementTree` (consistent with parse.py)
- XPath: `.//ref-list//pub-id[@pub-id-type='{id_type}']`
- Strip whitespace from extracted text
- Deduplicate with `dict.fromkeys()` to preserve order

**REFACTOR**:
- Verify XPath handles both `mixed-citation` and `element-citation` correctly
- Check if any helper could be shared with parse.py (unlikely, but verify)

**Success criteria**:
- [ ] All tests pass including golden file validation
- [ ] Function handles real-world NXML structure
- [ ] `uv run ruff check src/ tests/`

**Commit**: `feat: extract_refs() core function + NXML fixtures`

**Dependencies**: None (independent of Feature A)

---

### Phase 10.4 — `pm refs` CLI (TDD)

**Deliverable**: CLI entry point for `pm refs`.

**RED — Tests to write first** (`tests/test_refs.py`, new class):
- [ ] Test: `pm refs file.nxml` reads file and prints PMIDs to stdout (one per line)
- [ ] Test: `pm refs` with stdin reads NXML from stdin
- [ ] Test: `pm refs *.nxml` processes multiple files, output is union (deduplicated)
- [ ] Test: `pm refs --doi file.nxml` prints DOIs instead
- [ ] Test: `pm refs --help` prints help text (check key phrases)
- [ ] Test: `pm refs nonexistent.nxml` prints error to stderr, exit 1
- [ ] Test: `pm refs` with no input and stdin is tty -> error message, exit 1
- [ ] Test: `pm refs file.nxml` output lines are all-digit PMIDs (pipeable to `pm fetch`)

**GREEN — Implementation**:
- Add `main(args)` function to `refs.py`
- Add `refs` to `SUBCOMMANDS` in cli.py, add `from pm_tools import refs` to imports
- Update `MAIN_HELP` to include `refs` command
- Read files from positional args or stdin (stdin when no args and stdin is not tty)
- `--doi` flag selects DOI extraction
- `-v, --verbose` for logging
- Exit 0 on success (even if no refs found), exit 1 on error
- HELP_TEXT follows cli-design-for-agents.md principles

**REFACTOR**:
- Review help text: does it teach via examples? progressive disclosure?
- Ensure exit codes documented in help text match implementation

**Success criteria**:
- [ ] All tests pass
- [ ] `uv run ruff check src/ tests/`
- [ ] Registered in cli.py SUBCOMMANDS
- [ ] `pm --help` shows `refs`

**Commit**: `feat: pm refs CLI command`

**Dependencies**: Phase 10.3

---

### Phase 10.5 — Integration tests (TDD)

**Deliverable**: End-to-end tests composing Feature A and Feature B.

**RED — Tests to write first** (new class in `tests/test_download.py` or new file):
- [ ] Test: E2E: tgz with NXML + PDF -> `pm download` (default) -> `{PMID}.nxml` file created
      -> `pm refs {PMID}.nxml` -> PMIDs on stdout
- [ ] Test: E2E: tgz with only PDF (no NXML) -> `pm download` -> falls back to `{PMID}.pdf`
- [ ] Test: E2E: `pm download --pdf` + tgz with NXML -> saves `{PMID}.pdf`, not `.nxml`
- [ ] Test: mixed sources (tgz + direct PDF) -> correct file types for each article
- [ ] Test: `pm refs` on a PDF file -> empty output (no crash, exit 0)

**GREEN — Implementation**:
- Create tgz fixtures containing the `sample.nxml` fixture + a fake PDF
- Wire up full pipeline tests using subprocess or function calls

**REFACTOR**:
- Factor out shared tgz fixture creation if used in multiple test files

**Success criteria**:
- [ ] All 300+ existing tests still pass
- [ ] New integration tests pass
- [ ] `uv run ruff check src/ tests/`

**Commit**: `test: integration tests for NXML download + pm refs pipeline`

**Dependencies**: Phases 10.2, 10.4

---

### Phase 10.6 — Quality gate

- [ ] All tests pass (`uv run pytest`)
- [ ] Lint passes (`uv run ruff check src/ tests/`)
- [ ] Format passes (`uv run ruff format --check src/ tests/`)
- [ ] HELP_TEXT for `pm download` updated (documents `--pdf`, default NXML behavior)
- [ ] HELP_TEXT for `pm refs` complete (follows cli-design-for-agents.md)
- [ ] `pm --help` lists `refs` command
- [ ] Golden files match actual output
- [ ] `plan.md` checkboxes updated
- [ ] Code review via `/reviewing-code`

**Dependencies**: All previous phases

---

## Dependency Graph

```
Phase 10.0 (_extract_nxml_from_tgz)    Phase 10.1a (pmc_lookup prefers tgz)
    |                                        |
    v                                        v
    +----------> Phase 10.1b (_download_one NXML preference + test updates)
                     |
                     v
              Phase 10.2 (download_pdfs + CLI --pdf)
                     |                                  Phase 10.3 (extract_refs + fixtures)
                     |                                      |
                     v                                      v
                     +----> Phase 10.5 (integration) <-- Phase 10.4 (pm refs CLI)
                                    |
                                    v
                              Phase 10.6 (quality gate)
```

Feature A track: 10.0 + 10.1a → 10.1b → 10.2
Feature B track: 10.3 → 10.4
Both converge at 10.5 for integration testing.

---

## Files to create

| File | Purpose |
|------|---------|
| `src/pm_tools/refs.py` | `extract_refs()` + `main()` for `pm refs` |
| `tests/test_refs.py` | Tests for `pm refs` |
| `fixtures/sample.nxml` | Realistic NXML fixture for testing |
| `fixtures/golden/sample-refs-pmids.txt` | Golden file: expected PMID output |
| `fixtures/golden/sample-refs-dois.txt` | Golden file: expected DOI output |

## Files to modify

| File | Change |
|------|--------|
| `src/pm_tools/download.py` | `pmc_lookup()` tgz preference, `_extract_nxml_from_tgz()`, `prefer_pdf` param, manifest ext, HELP_TEXT |
| `src/pm_tools/cli.py` | Add `refs` to SUBCOMMANDS, import refs, update MAIN_HELP |
| `tests/test_download.py` | Update 3 existing tests, add NXML extraction + preference tests |

## Files NOT modified

- `src/pm_tools/parse.py` — parse stays XML-focused (PubMed XML, not JATS/NXML)
- `spec.md` — update after implementation
- `plan.md` — checkboxes updated after each phase

## NXML fixture content (`fixtures/sample.nxml`)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Archiving and Interchange DTD v1.1 20151215//EN"
  "JATS-archivearticle1.dtd">
<article>
  <front>
    <article-meta>
      <article-id pub-id-type="pmid">12345678</article-id>
      <article-id pub-id-type="pmc">PMC9273392</article-id>
      <title-group>
        <article-title>Sample Article for Testing</article-title>
      </title-group>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Introduction</title>
      <p>This is a minimal NXML fixture for testing pm refs.</p>
    </sec>
  </body>
  <back>
    <ref-list>
      <title>References</title>
      <ref id="B1">
        <mixed-citation publication-type="journal">
          <person-group person-group-type="author">
            <name><surname>Smith</surname><given-names>J</given-names></name>
          </person-group>
          <article-title>Example article</article-title>
          <source>Nature</source>
          <year>2020</year>
          <pub-id pub-id-type="pmid">11111111</pub-id>
          <pub-id pub-id-type="doi">10.1038/example</pub-id>
        </mixed-citation>
      </ref>
      <ref id="B2">
        <element-citation publication-type="journal">
          <person-group person-group-type="author">
            <name><surname>Doe</surname><given-names>A</given-names></name>
          </person-group>
          <article-title>Another article</article-title>
          <pub-id pub-id-type="pmid">22222222</pub-id>
        </element-citation>
      </ref>
      <ref id="B3">
        <mixed-citation publication-type="journal">
          <person-group person-group-type="author">
            <name><surname>Lee</surname><given-names>K</given-names></name>
          </person-group>
          <article-title>DOI-only reference</article-title>
          <pub-id pub-id-type="doi">10.1000/other</pub-id>
        </mixed-citation>
      </ref>
    </ref-list>
  </back>
</article>
```

## Principles

- TDD strict: RED → GREEN → REFACTOR for every phase
- One commit per phase (commit message in each phase section)
- Backward-compatible: `--pdf` restores old behavior exactly
- NXML extraction is parallel to PDF extraction (same security model)
- `pm refs` follows Unix philosophy: reads files or stdin, outputs text to stdout
- Composable: `pm download` -> `pm refs` -> `pm fetch` (citation chaining)
- Existing tests updated explicitly (no silent breakage)
- Golden files validate output against known-good data
- No `--recursive` flag (shell glob is explicit and composable)
