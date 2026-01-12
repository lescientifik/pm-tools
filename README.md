# PubMed CLI Tools

Unix-style command-line tools for searching and parsing PubMed articles. Designed for researchers who want quick access to publication data without leaving the terminal.

```bash
# Search, parse, and filter
pm-search "CRISPR cancer therapy" | pm-fetch | pm-parse | jq '.title'

# Full pipeline: search to PDF download
pm-search "CRISPR review" --max 5 | pm-fetch | pm-parse | pm-download --output-dir ./pdfs/
```

## Installation

```bash
# One-line install (requires curl, xml2, jq)
curl -fsSL https://raw.githubusercontent.com/lescientifik/pm-tools/main/install-remote.sh | bash
```

Or install from source:

```bash
git clone https://github.com/lescientifik/pm-tools.git
cd pm-tools
./install.sh
```

### Dependencies

```bash
# Debian/Ubuntu
sudo apt install curl xml2 jq mawk

# macOS
brew install xml2 jq mawk

# Check your setup
curl -fsSL .../install-remote.sh | bash -s -- --check-deps
```

### Uninstall

```bash
# If installed via curl
curl -fsSL https://raw.githubusercontent.com/lescientifik/pm-tools/main/uninstall.sh | bash

# Or run locally
./uninstall.sh
```

## Commands

| Command | Input | Output | Purpose |
|---------|-------|--------|---------|
| `pm-search` | Query string | PMIDs | Search PubMed |
| `pm-fetch` | PMIDs (stdin) | XML | Download article data |
| `pm-parse` | XML (stdin) | JSONL | Extract structured data |
| `pm-filter` | JSONL (stdin) | JSONL | Filter by year/journal/author |
| `pm-diff` | Two JSONL files | JSONL | Compare article collections |
| `pm-show` | JSONL (stdin) | Text | Pretty-print articles |
| `pm-download` | JSONL/PMIDs | PDFs | Download Open Access PDFs |
| `pm-quick` | Query string | Text | One-command search to pretty output |
| `pm-skill` | - | File | Install Claude Code skill |

## Quick Examples

```bash
# Simplest: one command for pretty results
pm-quick "CRISPR cancer therapy"

# Search and get titles
pm-search "machine learning diagnosis" --max 10 | pm-fetch | pm-parse | jq -r '.title'

# Filter to recent Nature papers with abstracts
pm-search "quantum computing" --max 50 | pm-fetch | pm-parse | \
  pm-filter --year 2024- --journal nature --has-abstract

# Pretty-print results in the terminal
pm-search "CRISPR" --max 5 | pm-fetch | pm-parse | pm-show

# Save results to JSONL for later use
pm-search "alzheimer biomarkers" --max 100 | pm-fetch | pm-parse > papers.jsonl

# Export to CSV
pm-search "alzheimer biomarkers" --max 100 | pm-fetch | pm-parse | \
  jq -r '[.pmid, .year, .journal, .title] | @csv' > papers.csv
```

## Filtering Results

`pm-filter` lets you filter parsed articles without writing jq queries:

```bash
# Filter by year (exact, range, or open-ended)
pm-filter --year 2024           # Exact year
pm-filter --year 2020-2024      # Range
pm-filter --year 2020-          # 2020 and later

# Filter by journal (case-insensitive substring)
pm-filter --journal nature
pm-filter --journal "cell reports"

# Filter by author (case-insensitive, matches any author)
pm-filter --author zhang

# Boolean filters
pm-filter --has-abstract        # Must have abstract
pm-filter --has-doi             # Must have DOI

# Combine filters (AND logic)
pm-filter --year 2023- --journal nature --has-abstract

# Verbose mode shows filter stats
pm-filter --year 2024 -v        # Output: "15/50 articles passed filters"
```

## Quick Search with pm-quick

For interactive use when you just want to see results quickly:

```bash
# Basic quick search (default 100 results)
pm-quick "CRISPR cancer therapy"

# Limit results
pm-quick --max 20 "machine learning diagnosis"

# Verbose mode shows progress
pm-quick -v "protein folding"
```

`pm-quick` is a convenience wrapper that runs the full pipeline (`pm-search | pm-fetch | pm-parse | pm-show`) in one command. For programmatic use or custom filtering, use the individual commands.

## Daily Research Workflows

### Track Your Favorite Authors

```bash
# Papers by a specific researcher
pm-search "Doudna JA[author]" --max 10 | pm-fetch | pm-parse | \
  jq -r '"\(.year) - \(.title[0:70])..."'

# Multiple authors (collaborations)
pm-search "(Zhang F[author]) AND (Bhattacharya D[author])" | \
  pm-fetch | pm-parse | jq '.title'
```

### Journal Watch

Monitor specific journals for topics you care about:

```bash
# Recent Cell papers on organoids
pm-search "organoids AND Cell[journal]" --max 20 | pm-fetch | pm-parse | \
  pm-filter --year 2024- | jq -r '.title'

# Compare publication counts across journals
pm-search "immunotherapy" --max 200 | pm-fetch | pm-parse | \
  jq -r '.journal' | sort | uniq -c | sort -rn | head -10
```

### Literature Review Helper

Build a reading list with abstracts:

```bash
# Generate markdown reading list
pm-search "CAR-T cell therapy review" --max 15 | pm-fetch | pm-parse | \
  jq -r '"## \(.title)\n**\(.journal)** (\(.year)) - PMID: \(.pmid)\n\n\(.abstract // "No abstract")\n\n---\n"' \
  > reading-list.md

# Find review articles specifically
pm-search "neuroplasticity AND review[pt]" --max 10 | pm-fetch | pm-parse | \
  jq -r '.title'
```

### Quick Reference Lookup

```bash
# Look up a specific PMID
echo "12345678" | pm-fetch | pm-parse | jq .

# Batch lookup from a file
cat pmids.txt | pm-fetch | pm-parse > articles.jsonl

# Get DOI for citation
pm-search "Yamanaka induced pluripotent" --max 1 | pm-fetch | pm-parse | \
  jq -r '"DOI: \(.doi)\nTitle: \(.title)"'
```

### Download Open Access PDFs

```bash
# Preview what would be downloaded (dry-run)
pm-search "CRISPR review" --max 10 | pm-fetch | pm-parse | \
  pm-download --dry-run

# Download PDFs to a directory
pm-search "open access[filter] AND immunotherapy" --max 20 | \
  pm-fetch | pm-parse | pm-download --output-dir ./papers/

# Download with Unpaywall fallback (more coverage, requires email)
pm-search "machine learning radiology" --max 10 | pm-fetch | pm-parse | \
  pm-download --output-dir ./pdfs/ --email you@university.edu

# Download from PMID list (auto-converts to DOI/PMCID)
cat pmids.txt | pm-download --output-dir ./pdfs/
```

**Sources**: `pm-download` tries PMC Open Access first, then falls back to Unpaywall (if `--email` provided). Not all articles have free PDFs available.

## Advanced Patterns

### Build a Local Database

```bash
# Fetch your entire research area (be patient, respects rate limits)
pm-search "your niche topic" --max 1000 | pm-fetch | pm-parse > my-field.jsonl

# Then query locally (instant!)
pm-filter --year 2020- < my-field.jsonl
pm-filter --author smith --has-abstract < my-field.jsonl

# Or use jq for complex queries
jq 'select(.abstract | test("novel"; "i"))' my-field.jsonl
```

### Publication Trends

```bash
# Papers per year for a topic
pm-search "microbiome gut brain" --max 500 | pm-fetch | pm-parse | \
  jq -r '.year' | sort | uniq -c | sort -k2

# Output:
#   12 2018
#   34 2019
#   67 2020
#  145 2021
#  203 2022
```

### Integration with Other Tools

```bash
# Desktop notification for new papers (Linux)
pm-search "your topic AND 2024[dp]" --max 5 | pm-fetch | pm-parse | \
  jq -r '.title' | head -1 | xargs -I {} notify-send "New Paper" "{}"

# Email yourself a digest
pm-search "CRISPR 2024" --max 10 | pm-fetch | pm-parse | \
  jq -r '"- \(.title) (\(.journal))"' | \
  mail -s "Daily PubMed Digest" you@email.com

# Pipe to fzf for interactive selection
pm-search "protein folding" --max 50 | pm-fetch | pm-parse | \
  jq -r '"\(.pmid)\t\(.title)"' | \
  fzf --preview 'echo {} | cut -f1 | xargs -I {} curl -s "https://pubmed.ncbi.nlm.nih.gov/{}"'
```

### Working with Baseline Files

For bulk analysis, download PubMed baseline files directly:

```bash
# Parse local baseline file (30,000 articles)
zcat pubmed25n0001.xml.gz | pm-parse > baseline.jsonl

# Find all papers from a specific institution
jq 'select(.authors[]? | test("Harvard"))' baseline.jsonl
```

### Comparing Article Collections

Use `pm-diff` to compare two JSONL files and find added, removed, or changed articles:

```bash
# Stream all differences as JSONL
pm-diff baseline_v1.jsonl baseline_v2.jsonl

# Get list of new PMIDs (for fetching updates)
pm-diff old.jsonl new.jsonl | jq -r 'select(.status=="added") | .pmid' | pm-fetch | pm-parse > new_articles.jsonl

# Filter to just changed articles
pm-diff old.jsonl new.jsonl | jq 'select(.status=="changed")'

# Summary counts by status
pm-diff old.jsonl new.jsonl | jq -s 'group_by(.status) | map({(.[0].status): length}) | add'

# Compare only metadata (ignore abstract changes)
pm-diff old.jsonl new.jsonl --ignore abstract

# Quick check if files differ (for scripts)
if pm-diff file1.jsonl file2.jsonl --quiet; then
    echo "Files are identical"
else
    echo "Files differ"
fi
```

**Output format**: Streaming JSONL with `{"pmid":"...","status":"added|removed|changed",...}`

**Exit codes**: 0 = identical, 1 = differences found, 2 = error

## Claude Code Integration

Install a skill to teach Claude how to use pm-tools:

```bash
# Install skill for current project
pm-skill

# Install for all projects (global)
pm-skill --global

# Force overwrite if exists
pm-skill --force
```

Once installed, Claude will understand how to search PubMed, fetch articles, and process results using the pm-tools pipeline.

## Output Format

Each article is output as a JSON object (JSONL format):

```json
{
  "pmid": "12345678",
  "title": "Article title here",
  "authors": ["Smith John", "Doe Jane"],
  "journal": "Nature",
  "year": "2024",
  "date": "2024-03-15",
  "doi": "10.1038/xxxxx",
  "pmcid": "PMC1234567",
  "abstract": "Full abstract text..."
}
```

Fields `doi`, `pmcid`, `date`, and `abstract` are omitted when not available.

## PubMed Query Syntax

Use standard [PubMed search syntax](https://pubmed.ncbi.nlm.nih.gov/help/#search-tags):

| Query | Meaning |
|-------|---------|
| `cancer AND therapy` | Both terms |
| `"gene editing"` | Exact phrase |
| `Smith J[author]` | Author search |
| `Nature[journal]` | Journal filter |
| `2024[dp]` | Publication date |
| `review[pt]` | Publication type |
| `2020:2024[dp]` | Date range |

## Tips

- **Rate Limits**: Tools respect NCBI's 3 requests/second limit automatically
- **Batch Size**: `pm-fetch` batches 200 PMIDs per request for efficiency
- **Large Queries**: Use `--max` to limit results, or paginate with date ranges
- **Verbose Mode**: Add `--verbose` to `pm-parse` to see progress on large files

## Performance

Benchmark on Intel Celeron N5105 @ 2.00GHz (low-power CPU):

| Operation | Records | Time | Throughput |
|-----------|---------|------|------------|
| `pm-parse` (30k baseline file) | 30,000 | 5.1s | ~5,850 articles/sec |

```bash
# Reproduce benchmark
zcat pubmed25n0001.xml.gz | pm-parse | wc -l
```

Performance scales with CPU. Uses `mawk` when available (auto-detected) for ~2x speedup over `gawk`.

## Dependencies

- `curl` - HTTP requests
- `xml2` - XML parsing
- `jq` - JSON processing (for filtering results)
- `grep` - Pattern matching
- `mawk` - Fast awk implementation (optional, auto-detected for 2x speedup)

```bash
# Debian/Ubuntu
sudo apt install curl xml2 jq mawk

# macOS
brew install xml2 jq mawk
```

## License

MIT
