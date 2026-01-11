# PubMed CLI Tools

Unix-style command-line tools for searching and parsing PubMed articles. Designed for researchers who want quick access to publication data without leaving the terminal.

```bash
pm-search "CRISPR cancer therapy" | pm-fetch | pm-parse | jq '.title'
```

## Installation

```bash
# Clone and install
git clone https://github.com/youruser/pubmed_parser.git
cd pubmed_parser
./install.sh

# Dependencies (Debian/Ubuntu)
sudo apt install xml2 curl jq
```

## The Three Commands

| Command | Input | Output | Purpose |
|---------|-------|--------|---------|
| `pm-search` | Query string | PMIDs | Search PubMed |
| `pm-fetch` | PMIDs (stdin) | XML | Download article data |
| `pm-parse` | XML (stdin) | JSONL | Extract structured data |

## Quick Examples

```bash
# Search and get titles
pm-search "machine learning diagnosis" --max 10 | pm-fetch | pm-parse | jq -r '.title'

# Get recent Nature papers on a topic
pm-search "quantum computing" --max 50 | pm-fetch | pm-parse | \
  jq -r 'select(.journal | test("Nature")) | "\(.pmid): \(.title)"'

# Export to CSV
pm-search "alzheimer biomarkers" --max 100 | pm-fetch | pm-parse | \
  jq -r '[.pmid, .year, .journal, .title] | @csv' > papers.csv
```

## Daily Research Workflows

### Morning Paper Alert

Check for new papers in your field every morning:

```bash
# ~/.local/bin/daily-papers
#!/bin/bash
# Run with: daily-papers "your research topic"

QUERY="${1:-CRISPR gene therapy}"
TODAY=$(date +%Y/%m/%d)
YESTERDAY=$(date -d "yesterday" +%Y/%m/%d)

pm-search "${QUERY} AND ${YESTERDAY}:${TODAY}[dp]" --max 20 | \
  pm-fetch | pm-parse | \
  jq -r '"[\(.year)] \(.title)\n    → \(.journal)\n    https://pubmed.ncbi.nlm.nih.gov/\(.pmid)/\n"'
```

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
  jq -r 'select(.year == "2024" or .year == "2025") | .title'

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

## Advanced Patterns

### Build a Local Database

```bash
# Fetch your entire research area (be patient, respects rate limits)
pm-search "your niche topic" --max 1000 | pm-fetch | pm-parse > my-field.jsonl

# Then query locally with jq (instant!)
jq 'select(.year >= "2020")' my-field.jsonl
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

## Output Format

Each article is output as a JSON object (JSONL format):

```json
{
  "pmid": "12345678",
  "title": "Article title here",
  "authors": ["Smith John", "Doe Jane"],
  "journal": "Nature",
  "year": "2024",
  "doi": "10.1038/xxxxx",
  "abstract": "Full abstract text..."
}
```

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
- **Performance**: `pm-parse` processes ~6,000 articles/sec with mawk (auto-detected), ~3,500/sec with gawk

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
