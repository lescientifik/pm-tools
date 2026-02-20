---
name: using-pm-tools
description: Searches and parses PubMed articles using pm-tools CLI. Use when user asks about PubMed, scientific papers, literature search, downloading PDFs, generating citations/bibliographies, or mentions any pm-* command (pm search, pm fetch, pm parse, pm filter, pm show, pm download, pm diff, pm cite).
---

# Using pm-tools

Unix-style CLI tools for PubMed: search -> fetch -> parse -> filter.

## Commands

| Command | Input | Output | Purpose |
|---------|-------|--------|---------|
| `pm search` | Query | PMIDs | Search PubMed |
| `pm fetch` | PMIDs | XML | Download article data |
| `pm parse` | XML | JSONL | Extract structured fields |
| `pm filter` | JSONL | JSONL | Filter by year/journal/author |
| `pm show` | JSONL | Text | Pretty-print for humans |
| `pm download` | JSONL | PDFs | Download Open Access PDFs |
| `pm diff` | Two JSONL files | JSONL | Compare article collections |
| `pm cite` | PMIDs | CSL-JSON | Fetch citations for bibliographies |

## AI Workflow (REQUIRED)

**NEVER use `pm collect`** - it's for human terminal use only.

**ALWAYS save results to files** to avoid re-querying PubMed API:

### Step 1: Search and cache results
```bash
# Save to project directory if research is relevant, otherwise /tmp
pm search "QUERY" --max 50 | pm fetch | pm parse > results.jsonl
```

### Step 2: Browse titles first (prevent context flooding)
```bash
jq -r '{pmid, title}' results.jsonl
```

### Step 3: Drill into specific articles if needed
```bash
# Get abstract for specific PMID
jq -r 'select(.pmid == "12345678") | .abstract' results.jsonl

# Or get full details for a few articles
jq -r 'select(.pmid == "12345678" or .pmid == "87654321")' results.jsonl
```

### Step 4: Apply filters as needed
```bash
pm filter --year 2024- --has-abstract < results.jsonl > filtered.jsonl
jq -r '{pmid, title}' filtered.jsonl
```

## File Naming Convention

```bash
# Temporary exploration
/tmp/pubmed-$(date +%Y%m%d-%H%M%S).jsonl

# Research the user wants to keep
./pubmed-TOPIC.jsonl           # e.g., pubmed-crispr-therapy.jsonl
./data/pubmed-TOPIC.jsonl      # if data/ directory exists
```

## Common Patterns

### Initial exploration
```bash
pm search "CRISPR therapy" --max 30 | pm fetch | pm parse > /tmp/crispr.jsonl
jq -r '{pmid, title}' /tmp/crispr.jsonl
```

### Narrow down by year
```bash
pm filter --year 2024- < /tmp/crispr.jsonl | jq -r '{pmid, title, year}'
```

### Read specific abstracts
```bash
jq -r 'select(.pmid == "39341234") | "\(.title)\n\n\(.abstract)"' /tmp/crispr.jsonl
```

### Export for user
```bash
jq -r '[.pmid, .year, .journal, .title] | @csv' results.jsonl > papers.csv
```

### Compare collections
```bash
pm diff old.jsonl new.jsonl | jq -r 'select(.status=="added") | .pmid'
```

### Generate bibliography citations
```bash
# Get CSL-JSON citations for specific PMIDs
pm cite 28012456 29886577 > citations.jsonl

# Pipeline: search -> cite
pm search "CRISPR therapy" --max 10 | pm cite > citations.jsonl
```

## Bibliography with pm cite

`pm cite` fetches CSL-JSON citations from NCBI's Citation Exporter API. Use it when:
- User needs formatted citations (APA, Vancouver, etc.)
- Generating bibliographies for papers
- Exporting to Zotero, Mendeley, or Pandoc

### CSL-JSON Output Format

```json
{
  "id": "pmid:28012456",
  "type": "article-journal",
  "title": "Article title...",
  "author": [{"family": "Smith", "given": "John"}, ...],
  "container-title": "Nature",
  "issued": {"date-parts": [[2024, 3, 15]]},
  "volume": "627",
  "issue": "8003",
  "page": "123-130",
  "PMID": "28012456",
  "DOI": "10.1038/xxxxx"
}
```

### Common Citation Workflows

```bash
# Save citations from a search
pm search "immunotherapy cancer" --max 20 | pm cite > refs.jsonl

# Convert to Pandoc-compatible JSON array
jq -s '.' refs.jsonl > bibliography.json

# Use with Pandoc for document generation
pandoc paper.md --citeproc --bibliography=bibliography.json -o paper.pdf

# Extract formatted author list
jq -r '.author | map(.family + " " + .given[0:1]) | join(", ")' refs.jsonl

# Get DOIs for citation linking
jq -r 'select(.DOI) | .DOI' refs.jsonl
```

### pm cite vs pm parse

| Feature | pm parse | pm cite |
|---------|----------|---------|
| Abstract | Yes | No |
| Page numbers | No | Yes |
| Volume/Issue | No | Yes |
| Citation tools | Needs conversion | Direct (CSL-JSON) |
| Use case | Content analysis | Bibliography generation |

**Rule of thumb:**
- Reading/analyzing papers -> `pm parse`
- Creating citations/references -> `pm cite`

## Output Format (JSONL)

```json
{
  "pmid": "12345678",
  "title": "Article title",
  "authors": ["Smith John", "Doe Jane"],
  "journal": "Nature",
  "year": "2024",
  "doi": "10.1038/xxxxx",
  "abstract": "Full abstract..."
}
```

## Filter Options

```bash
pm filter --year 2024           # Exact year
pm filter --year 2020-2024      # Range
pm filter --year 2020-          # 2020 onwards
pm filter --journal nature      # Case-insensitive
pm filter --author zhang        # Any author matches
pm filter --has-abstract        # Must have abstract
pm filter --has-doi             # Must have DOI
```

## Human Commands (NOT for AI)

`pm collect` and `pm show` produce pretty output for humans reading terminals.
AI should read JSONL directly with `jq` for structured access.

## Notes

- Rate limit: 3 req/sec (automatic)
- Batch size: 200 PMIDs per fetch
- Use `--max N` to limit search results
- **Always cache to file** - never run the same query twice
