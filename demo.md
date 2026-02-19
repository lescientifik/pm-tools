# pm-tools — PubMed CLI for AI Agents

*2026-02-19T10:31:12Z by Showboat 0.6.0*
<!-- showboat-id: 70d08fd4-e22c-4664-a2fe-e4f8f658af91 -->

Unix-style CLI toolkit for searching, fetching, and parsing PubMed articles. Designed for composability: each command does one thing, connected via pipes.

Install: `uv tool install pm-tools` (or `uv pip install pm-tools`)

All examples below are **live executions** against the PubMed API.

## 1. Overview

```bash
uv run pm --help
```

```output
pm - PubMed CLI tools for AI agents

Usage: pm <command> [OPTIONS]

Commands:
  init        Initialize audit trail and cache (.pm/)
  search      Search PubMed, return PMIDs
  fetch       Fetch PubMed XML by PMIDs
  parse       Parse PubMed XML to JSONL
  filter      Filter JSONL articles by field patterns
  cite        Fetch CSL-JSON citations
  download    Download full-text PDFs
  diff        Compare two JSONL files by PMID
  audit       View audit trail and PRISMA report
  quick       One-command search pipeline (outputs JSONL)

Examples:
  pm search "CRISPR cancer" | pm fetch | pm parse > results.jsonl
  pm quick "covid vaccine" --max 50
  pm filter --year 2024 --has-abstract < articles.jsonl

Use 'pm <command> --help' for command-specific help.
```

## 2. Initialize a project

`pm init` creates a `.pm/` directory for caching and audit logging.

```bash
pm init && find .pm -type f | sort
```

```output
Initialized .pm/ in /tmp/pm-demo
Audit trail: .pm/audit.jsonl
Cache: .pm/cache/
.pm/.gitignore
.pm/audit.jsonl
```

## 3. Search PubMed

`pm search` queries the PubMed E-utilities API and returns PMIDs (one per line). Use `--max` to limit results.

```bash
pm search --max 5 "CRISPR cancer therapy 2024"
```

```output
41699717
41634395
41540109
41504119
41476860
```

## 4. Fetch XML

`pm fetch` reads PMIDs from stdin and outputs PubMed XML. It batches requests (200/batch) and respects rate limits.

```bash
pm search --max 5 "CRISPR cancer therapy 2024" | pm fetch > articles.xml && echo "Fetched $(wc -c < articles.xml) bytes of XML ($(grep -c "<PubmedArticle>" articles.xml) articles)"
```

```output
pm: using cached search from 2026-02-19. Use --refresh to update.
Fetched 136487 bytes of XML (5 articles)
```

## 5. Parse XML → JSONL

`pm parse` converts PubMed XML into structured JSONL — one JSON object per article.

```bash
pm parse < articles.xml | python3 -c "
import sys, json
for line in sys.stdin:
    a = json.loads(line)
    pmid = a.get(\"pmid\", \"\")
    year = a.get(\"year\", \"\")
    journal = a.get(\"journal\", \"\")[:40]
    title = a.get(\"title\", \"\")[:60]
    print(\"%-10s  %s  %-40s  %s...\" % (pmid, year, journal, title))
"
```

```output
41699717    2026  Experimental hematology & oncology        Tumor-intrinsic PD-L1 drives lung cancer progression in resp...
41634395    2026  Annals of hematology                      Efficacy and safety of epcoritamab in relapsed or refractory...
41540109    2026  Nature medicine                           CD4+ T cells mediate CAR-T cell-associated immune-related ad...
41504119    2025  Frontiers in bioscience (Scholar edition  Genetic Regulation of DNA Double-Strand Breaks and Repair Pa...
41476860    2025  Frontiers in genome editing               Therapeutic applications of CRISPR-Cas9 gene editing....
```

```bash
pm parse < articles.xml > articles.jsonl && echo "$(wc -l < articles.jsonl) articles parsed"
```

```output
5 articles parsed
```

## 6. Full Pipeline (search → fetch → parse)

The three commands compose via Unix pipes:

```bash
pm search --max 3 "single-cell RNA-seq brain" | pm fetch | pm parse | python3 -c "
import sys, json
for line in sys.stdin:
    a = json.loads(line)
    print(\"PMID %s | %s | %s\" % (a.get(\"pmid\"), a.get(\"year\"), a.get(\"title\")[:80]))
"
```

```output
PMID 41705257 | 2026 | Soluble fermentable dietary fiber attenuates age-related cognitive impairment vi
PMID 41703343 | 2026 | Single-Cell Transcriptomic Analysis of Macaque LGN Neurons Reveals Novel Subpopu
PMID 41697880 | 2026 | Isolation of Pericytes from Mouse Cortical Tissue Using FACS for Single-cell Seq
```

Or use `pm quick` for the same pipeline in one command:

```bash
pm quick --max 3 metagenomics | python3 -c "
import sys, json
for line in sys.stdin:
    a = json.loads(line)
    print(\"PMID %s | %s | %s\" % (a.get(\"pmid\"), a.get(\"year\"), a.get(\"title\")[:80]))
"
```

```output
PMID 41709052 | 2026 | Revealing actinobacterial diversity inhabiting Malaysian Beach Ridges Interspers
PMID 41708925 | 2026 | Deciphering the etiology of the 2024 outbreak of undiagnosed febrile illness in 
PMID 41708882 | 2026 | Characterisation of Salmonella Typhimurium from a fatal equine nosocomial outbre
```

## 7. Filter results

`pm filter` selects articles matching criteria. Multiple filters combine with AND logic.

```bash
pm search --max 20 "CRISPR" | pm fetch | pm parse > crispr.jsonl
echo "Total articles: $(wc -l < crispr.jsonl)"
echo ""
echo "--- Filter by year 2026 ---"
pm filter --year 2026 -v < crispr.jsonl > /dev/null
echo ""
echo "--- Filter by year 2025 + has abstract ---"
pm filter --year 2025 --has-abstract -v < crispr.jsonl > /dev/null
echo ""
echo "--- Filter by journal containing Nature ---"
pm filter --journal nature -v < crispr.jsonl > /dev/null
```

```output
pm: using cached search from 2026-02-19. Use --refresh to update.
Total articles: 20

--- Filter by year 2026 ---
20 articles passed filters

--- Filter by year 2025 + has abstract ---
0 articles passed filters

--- Filter by journal containing Nature ---
2 articles passed filters
```

Show the Nature articles:

```bash
pm filter --journal nature < crispr.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    a = json.loads(line)
    print(\"PMID %s | %s | %s\" % (a.get(\"pmid\"), a.get(\"year\"), a.get(\"journal\")))
    print(\"  %s\" % a.get(\"title\")[:100])
    print()
"
```

```output
PMID 41708664 | 2026 | Nature communications
  Engineered Un1Cas12f1 for multiplex genome editing with enhanced activity and targeting scope.

PMID 41708610 | 2026 | Nature communications
  Cell-cell communication as underlying principle governing color pattern formation in teleost fishes.

```

## 8. Fetch CSL-JSON Citations

`pm cite` fetches structured CSL-JSON citation data from NCBI. Useful for generating bibliographies.

```bash
pm search --max 1 "CRISPR cancer therapy 2024" | pm cite | python3 -c "
import sys, json
for line in sys.stdin:
    c = json.loads(line)
    print(json.dumps(c, indent=2, ensure_ascii=False)[:600])
"
```

```output
{
  "source": "PubMed",
  "accessed": {
    "date-parts": [
      [
        2026,
        2,
        19
      ]
    ]
  },
  "id": "pmid:41699717",
  "title": "Tumor-intrinsic PD-L1 drives lung cancer progression in response to TLR stimulation by promoting autophagy through the TRAF6-BECN1 signaling axis",
  "author": [
    {
      "family": "Sung",
      "given": "Yoolim"
    },
    {
      "family": "Lee",
      "given": "Ha-Jeong"
    },
    {
      "family": "Kim",
      "given": "Mi-Jeong"
    },
    {
      "family": "Shin",
      "given": "Ji Hye"
    },
    {
      "family": "Kim",
   
```

## 9. Compare Datasets with pm diff

`pm diff` compares two JSONL files by PMID. Reports added, removed, and changed articles.

```bash
# Create two overlapping datasets
pm search --max 5 "CRISPR cancer therapy 2024" | pm fetch | pm parse > set_a.jsonl
pm search --max 5 "CRISPR gene editing 2024" | pm fetch | pm parse > set_b.jsonl
echo "Set A: $(wc -l < set_a.jsonl) articles"
echo "Set B: $(wc -l < set_b.jsonl) articles"
echo ""
pm diff set_a.jsonl set_b.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line)
    print(\"%s: PMID %s\" % (d.get(\"status\").upper(), d.get(\"pmid\")))
"
```

```output
pm: using cached search from 2026-02-19. Use --refresh to update.
Set A: 5 articles
Set B: 5 articles

REMOVED: PMID 41699717
REMOVED: PMID 41634395
REMOVED: PMID 41540109
REMOVED: PMID 41504119
REMOVED: PMID 41476860
ADDED: PMID 41703314
ADDED: PMID 41683605
ADDED: PMID 41677721
ADDED: PMID 41673558
ADDED: PMID 41627751
```

## 10. Audit Trail

Every operation is logged in `.pm/audit.jsonl` for PRISMA-compatible reproducibility.

```bash
pm audit
```

```output
Audit Trail Summary
===================

Total operations: 24

  cite             1
  fetch            8
  filter           4
  init             1
  search          10
```

```bash
pm audit --searches
```

```output
Search History
=============

  [2026-02-19] "CRISPR cancer therapy 2024" → 5 PMIDs
  [2026-02-19] "CRISPR cancer therapy 2024" → 5 PMIDs (cached)
  [2026-02-19] "CRISPR cancer therapy 2024" → 5 PMIDs (cached)
  [2026-02-19] "single-cell RNA-seq brain" → 3 PMIDs
  [2026-02-19] "metagenomics" → 3 PMIDs
  [2026-02-19] "CRISPR" → 20 PMIDs
  [2026-02-19] "CRISPR" → 20 PMIDs (cached)
  [2026-02-19] "CRISPR cancer therapy 2024" → 1 PMIDs
  [2026-02-19] "CRISPR cancer therapy 2024" → 5 PMIDs (cached)
  [2026-02-19] "CRISPR gene editing 2024" → 5 PMIDs
```

## 11. Smart Caching

Results are cached in `.pm/cache/` by category (search, fetch, cite). Repeated queries hit cache automatically.

```bash
find .pm/cache -type f | head -15 && echo "..." && echo "Total cached files: $(find .pm/cache -type f | wc -l)"
```

```output
.pm/cache/search/e11c16d48b102482e404f1e85b00e9762d56d1fbedf7ba596dbea332bd7cd0d6.json
.pm/cache/search/c196cb19c1b81c437effb2c6626b2fbd783674e8028caf005644d277559b6bbe.json
.pm/cache/search/4682413ac603175506e5ea72c3544a4cb09cf6d2b97e7231947cdcadda49f9c6.json
.pm/cache/search/5605a7af4dc51f4edcd2ebaff7f741038eebe919efaa4399495889e9267a4737.json
.pm/cache/search/bdf71e6a8ecb196a0bd8bf3031d70e649207f685d053ea34614822b9e9b096a9.json
.pm/cache/search/802b38b7cb7ada625f16b14ff53c8d5945b22ae1121d40eab6f1742e2d1f61e3.json
.pm/cache/fetch/41707986.xml
.pm/cache/fetch/41708925.xml
.pm/cache/fetch/41706890.xml
.pm/cache/fetch/41540109.xml
.pm/cache/fetch/41706704.xml
.pm/cache/fetch/41706060.xml
.pm/cache/fetch/41699717.xml
.pm/cache/fetch/41707086.xml
.pm/cache/fetch/41705810.xml
...
Total cached files: 43
```

Re-running the same search is instant (served from cache):

```bash
time pm search --max 20 "CRISPR" > /dev/null
```

```output
pm: using cached search from 2026-02-19. Use --refresh to update.

real	0m0.254s
user	0m0.210s
sys	0m0.040s
```

## 12. Edge Cases

Handles structured abstracts (BACKGROUND/METHODS/RESULTS sections), Unicode, and articles with missing fields.

```bash
# Structured abstracts are flattened with section labels
pm search --max 1 "randomized controlled trial diabetes" | pm fetch | pm parse | python3 -c "
import sys, json
art = json.loads(sys.stdin.readline())
abstract = art.get(\"abstract\", \"\")
# Show first 400 chars to see the structure
print(\"PMID:\", art.get(\"pmid\"))
print(\"Abstract (first 400 chars):\")
print(abstract[:400])
print(\"...\")
"
```

```output
PMID: 41706448
Abstract (first 400 chars):
Severe hypoglycemia is a life-threatening, iatrogenic complication of diabetes medications associated with increased risks of falls, cardiovascular events, cognitive decline, and mortality. To determine whether proactive outreach by a clinical pharmacist applying an evidence-based hypoglycemia-prevention algorithm (Hypoglycemia on a Page) would result in safer prescribing of diabetes regimens amon
...
```

Unicode in author names and titles is preserved:

```bash
pm search --max 3 "Müller épigénétique" | pm fetch | pm parse | python3 -c "
import sys, json
for line in sys.stdin:
    a = json.loads(line)
    authors = a.get(\"authors\", [])[:3]
    print(\"PMID %s: %s\" % (a.get(\"pmid\"), \", \".join(authors)))
"
```

```output
PMID 40195606: Sastourné-Haletou Romain, Marynberg Sacha, Pereira Arthur
PMID 26799652: Klionsky Daniel J, Abdelmohsen Kotb, Abe Akihisa
```

## 13. Test Suite & Code Quality

```bash
uv run pytest --tb=no -q 2>&1 | tail -5
```

```output
=========================== short test summary info ============================
FAILED tests/test_download.py::TestDownloadManifest::test_writes_manifest_jsonl
FAILED tests/test_download.py::TestDownloadVerify::test_non_pdf_content_counted_as_failed
FAILED tests/test_download.py::TestConcurrentDownload::test_concurrent_downloads
3 failed, 222 passed in 5.32s
```

The 3 failures are RED-phase TDD tests for `pm download` features not yet implemented.

```bash
uv run ruff check src/ tests/ && echo "ruff: all checks passed"
```

```output
All checks passed!
ruff: all checks passed
```

```bash
uv run ruff format --check src/ tests/ && echo "ruff format: all files formatted"
```

```output
24 files already formatted
ruff format: all files formatted
```
