# PubMed CLI Tools

Unix-style command-line tools for searching and parsing PubMed articles. Designed for researchers and AI agents who want quick access to publication data without leaving the terminal.

```bash
# All-in-one: search, fetch, parse in a single command
pm collect "CRISPR cancer therapy" --max 100 > results.jsonl

# Composable pipeline: search, fetch, parse, filter
pm search "CRISPR cancer therapy" | pm fetch | pm parse | \
  pm filter --year 2024- --has-abstract > filtered.jsonl
```

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** (Python package manager)
- **Python >= 3.12** (installed automatically by uv if needed)
- **Optional**: `jq` for advanced JSON filtering (`sudo apt install jq` or `brew install jq`)

## Installation

Install directly from GitHub (no PyPI release):

```bash
uv tool install git+https://github.com/lescientifik/pm-tools.git
```

This installs the `pm` command globally. You can then run `pm` from anywhere.

### Development install (for contributors)

```bash
git clone https://github.com/lescientifik/pm-tools.git
cd pm-tools
uv sync
```

With a development install, prefix all commands with `uv run` (e.g., `uv run pm search ...`).

## For AI Agents

If you're an AI agent discovering this tool, here's the fastest way to get started:

```bash
# Run directly without installing (preferred for one-off use)
uvx --from git+https://github.com/lescientifik/pm-tools.git pm collect "your query" --max 20

# Or install permanently
uv tool install git+https://github.com/lescientifik/pm-tools.git
```

After install, **always start with `--help`** to discover commands and options:

```bash
pm --help                # All available commands
pm <command> --help      # Detailed options, input/output format, and examples
```

Every command has its own `--help` with complete documentation. Use it before guessing flags.

## Getting Started

After installation, **run `--help`** to discover all commands and options:

```bash
# Show all available commands
pm --help

# Get help for any specific command
pm collect --help
pm search --help
pm filter --help
```

**Every command supports `--help`.** This is the best way to learn what each command does, what options it accepts, and how to use it.

## Commands

All commands are subcommands of `pm`. Run `pm --help` for the full list.

| Command | Input | Output | Purpose |
|---------|-------|--------|---------|
| `pm collect` | Query string | JSONL | **Recommended**: search + fetch + parse in one command |
| `pm search` | Query string | PMIDs | Search PubMed, one PMID per line |
| `pm fetch` | PMIDs (stdin) | XML | Fetch PubMed XML from NCBI API |
| `pm parse` | XML (stdin) | JSONL | Parse PubMed XML to structured JSONL |
| `pm filter` | JSONL (stdin) | JSONL | Filter by year/journal/author/abstract/DOI |
| `pm cite` | PMIDs (stdin or args) | JSONL (CSL-JSON) | Generate bibliography citations |
| `pm download` | JSONL/PMIDs (stdin) | NXML/PDF files | Download full-text articles from PMC/Unpaywall |
| `pm refs` | NXML files | PMIDs/DOIs | Extract cited identifiers from reference lists |
| `pm diff` | Two JSONL files | JSONL | Compare article collections (added/removed/changed) |
| `pm audit` | — | Text | View operation history and PRISMA reports |
| `pm init` | — | `.pm/` directory | Initialize cache and audit trail |

## Quick Examples

```bash
# Simplest: one command for quick results
pm collect "CRISPR cancer therapy" --max 50

# Search and get titles
pm search "machine learning diagnosis" --max 10 | pm fetch | pm parse | jq -r '.title'

# Filter to recent Nature papers with abstracts
pm search "quantum computing" --max 50 | pm fetch | pm parse | \
  pm filter --year 2024- --journal nature --has-abstract

# Save results to JSONL for later use
pm search "alzheimer biomarkers" --max 100 | pm fetch | pm parse > papers.jsonl

# Export to CSV
pm search "alzheimer biomarkers" --max 100 | pm fetch | pm parse | \
  jq -r '[.pmid, .year, .journal, .title] | @csv' > papers.csv
```

## Filtering Results

`pm filter` lets you filter parsed articles without writing jq queries:

```bash
# Filter by year (exact, range, or open-ended)
pm filter --year 2024           # Exact year
pm filter --year 2020-2024      # Range
pm filter --year 2020-          # 2020 and later

# Filter by journal (case-insensitive substring)
pm filter --journal nature
pm filter --journal "cell reports"

# Filter by author (case-insensitive, matches any author)
pm filter --author zhang

# Boolean filters
pm filter --has-abstract        # Must have abstract
pm filter --has-doi             # Must have DOI

# Combine filters (AND logic)
pm filter --year 2023- --journal nature --has-abstract

# Verbose mode shows filter stats
pm filter --year 2024 -v        # Output: "15/50 articles passed filters"
```

## Collecting Articles with pm collect

For interactive use when you just want results quickly:

```bash
# Basic search (default 100 results)
pm collect "CRISPR cancer therapy"

# Limit results
pm collect --max 20 "machine learning diagnosis"

# Verbose mode shows progress
pm collect -v "protein folding"
```

`pm collect` is a convenience wrapper that runs the full pipeline (`search | fetch | parse`) in one command. For custom filtering or step-by-step control, use the individual commands.

## Daily Research Workflows

### Track Your Favorite Authors

```bash
# Papers by a specific researcher
pm search "Doudna JA[author]" --max 10 | pm fetch | pm parse | \
  jq -r '"\(.year) - \(.title[0:70])..."'

# Multiple authors (collaborations)
pm search "(Zhang F[author]) AND (Bhattacharya D[author])" | \
  pm fetch | pm parse | jq '.title'
```

### Journal Watch

Monitor specific journals for topics you care about:

```bash
# Recent Cell papers on organoids
pm search "organoids AND Cell[journal]" --max 20 | pm fetch | pm parse | \
  pm filter --year 2024- | jq -r '.title'

# Compare publication counts across journals
pm search "immunotherapy" --max 200 | pm fetch | pm parse | \
  jq -r '.journal' | sort | uniq -c | sort -rn | head -10
```

### Literature Review Helper

Build a reading list with abstracts:

```bash
# Generate markdown reading list
pm search "CAR-T cell therapy review" --max 15 | pm fetch | pm parse | \
  jq -r '"## \(.title)\n**\(.journal)** (\(.year)) - PMID: \(.pmid)\n\n\(.abstract // "No abstract")\n\n---\n"' \
  > reading-list.md

# Find review articles specifically
pm search "neuroplasticity AND review[pt]" --max 10 | pm fetch | pm parse | \
  jq -r '.title'
```

### Quick Reference Lookup

```bash
# Look up a specific PMID
echo "12345678" | pm fetch | pm parse | jq .

# Batch lookup from a file
cat pmids.txt | pm fetch | pm parse > articles.jsonl

# Get DOI for citation
pm search "Yamanaka induced pluripotent" --max 1 | pm fetch | pm parse | \
  jq -r '"DOI: \(.doi)\nTitle: \(.title)"'

# Get full citation in CSL-JSON format
echo "12345678" | pm cite | jq '.'
```

### Download Full-Text Articles

`pm download` fetches articles from PMC Open Access (preferring structured NXML over PDF) with optional Unpaywall fallback.

```bash
# Preview what would be downloaded (dry-run)
pm search "CRISPR review" --max 10 | pm fetch | pm parse | \
  pm download --dry-run

# Download NXML (default) to a directory
pm search "open access[filter] AND immunotherapy" --max 20 | \
  pm fetch | pm parse | pm download --output-dir ./papers/

# Force PDF instead of NXML
pm search "open access[filter] AND immunotherapy" --max 20 | \
  pm fetch | pm parse | pm download --output-dir ./papers/ --pdf

# Download with Unpaywall fallback (more coverage, requires email)
pm search "machine learning radiology" --max 10 | pm fetch | pm parse | \
  pm download --output-dir ./pdfs/ --email you@university.edu

# Download from PMID list
cat pmids.txt | pm download --output-dir ./pdfs/
```

### Extract References from Downloaded Articles

```bash
# Extract cited PMIDs from NXML files
pm refs ./papers/*.nxml

# Extract DOIs instead
pm refs --doi ./papers/*.nxml

# Citation snowballing: find all papers cited by your results
pm refs ./papers/*.nxml | sort -u | pm fetch | pm parse > cited_articles.jsonl
```

### Generate Bibliography Citations

```bash
# Get CSL-JSON citations for specific PMIDs
pm cite 28012456 29886577 > citations.jsonl

# Pipeline: search -> cite
pm search "CRISPR review" --max 10 | pm cite > citations.jsonl

# Convert to Pandoc-compatible bibliography
jq -s '.' citations.jsonl > bibliography.json

# Use with Pandoc
pandoc paper.md --citeproc --bibliography=bibliography.json -o paper.pdf
```

**Output format (CSL-JSON):**
```json
{
  "id": "pmid:28012456",
  "type": "article-journal",
  "title": "Article title...",
  "author": [{"family": "Smith", "given": "John"}],
  "container-title": "Nature",
  "issued": {"date-parts": [[2024, 3, 15]]},
  "volume": "627",
  "page": "123-130",
  "PMID": "28012456",
  "DOI": "10.1038/xxxxx"
}
```

**pm cite vs pm parse:**
| Feature | pm parse | pm cite |
|---------|----------|---------|
| Abstract | Yes | No |
| Page numbers | No | Yes |
| Volume/Issue | No | Yes |
| Citation tools | Needs conversion | Direct (Zotero, Pandoc) |

Use `pm cite` for generating bibliographies; `pm parse` for content analysis.

### Comparing Article Collections

```bash
# Stream all differences as JSONL
pm diff baseline_v1.jsonl baseline_v2.jsonl

# Get list of new PMIDs
pm diff old.jsonl new.jsonl | jq -r 'select(.status=="added") | .pmid'

# Compare only metadata (ignore abstract changes)
pm diff old.jsonl new.jsonl --ignore abstract

# Quick check if files differ (for scripts)
if pm diff file1.jsonl file2.jsonl --quiet; then
    echo "Files are identical"
else
    echo "Files differ"
fi
```

**Output format**: Streaming JSONL with one line per difference:
```json
{"pmid":"...","status":"added","article":{...}}
{"pmid":"...","status":"removed","article":{...}}
{"pmid":"...","status":"changed","old":{...},"new":{...}}
```

**Exit codes**: 0 = identical, 1 = differences found, 2 = error

## Audit Trail and Caching

`pm` automatically caches API responses and logs operations when a `.pm/` directory exists.

```bash
# Initialize cache and audit trail in current directory
pm init

# View operation history
pm audit

# Cache is per-query (search) and per-PMID (fetch, cite)
# Use --refresh on search to bypass cache
pm search "CRISPR" --refresh
```

## Output Format

Each article is output as a JSON object (JSONL format, one per line):

```json
{
  "pmid": "12345678",
  "title": "Article title here",
  "authors": [
    {"family": "Smith", "given": "John"},
    {"family": "Doe", "given": "Jane"}
  ],
  "journal": "Nature",
  "year": 2024,
  "date": "2024-03-15",
  "doi": "10.1038/xxxxx",
  "pmcid": "PMC1234567",
  "abstract": "Full abstract text..."
}
```

- **`pmid`** (string): always present
- **`authors`**: array of CSL-JSON name objects (`family`/`given`, or `literal` for collective names)
- **`year`** (integer): publication year
- **`date`** (string): ISO 8601 date (YYYY, YYYY-MM, or YYYY-MM-DD)
- Fields `doi`, `pmcid`, `date`, `abstract` are omitted when not available
- Structured abstracts also include an `abstract_sections` array with `label`/`text` pairs

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

## Advanced Patterns

### Build a Local Database

```bash
# Fetch your entire research area (be patient, respects rate limits)
pm search "your niche topic" --max 1000 | pm fetch | pm parse > my-field.jsonl

# Then query locally (instant!)
pm filter --year 2020- < my-field.jsonl
pm filter --author smith --has-abstract < my-field.jsonl

# Or use jq for complex queries
jq 'select(.abstract | test("novel"; "i"))' my-field.jsonl
```

### Publication Trends

```bash
# Papers per year for a topic
pm search "microbiome gut brain" --max 500 | pm fetch | pm parse | \
  jq -r '.year' | sort | uniq -c | sort -k2
```

### Working with Baseline Files

For bulk analysis, download PubMed baseline files directly:

```bash
# Parse local baseline file (30,000 articles)
zcat pubmed25n0001.xml.gz | pm parse > baseline.jsonl
```

## Tips

- **Rate Limits**: Tools respect NCBI's 3 requests/second limit automatically
- **Batch Size**: `pm fetch` batches 200 PMIDs per request for efficiency
- **Large Queries**: Use `--max` to limit results, or paginate with date ranges
- **Caching**: Run `pm init` to enable per-query caching and audit trail
- **Verbose Mode**: Add `-v` / `--verbose` to see progress on long operations

## License

MIT
