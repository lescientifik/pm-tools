# pm-download Implementation Plan

## Overview

`pm-download` is a Unix-style CLI tool for downloading full-text PDFs of scientific articles. It supports two primary sources:

1. **PubMed Central (PMC)** - Free full-text archive of biomedical and life sciences literature
2. **Unpaywall** - Open access database linking DOIs to legal free PDF sources

## Input/Output Design

### Input Modes

```bash
# Mode 1: JSONL from stdin (pipeline from pm-parse)
pm-search "CRISPR" | pm-fetch | pm-parse | pm-download

# Mode 2: PMIDs from stdin
echo "12345" | pm-download

# Mode 3: PMIDs from file
pm-download --input pmids.txt
```

### Output Modes

```bash
# Default: Download PDFs to current directory
pm-download                         # files: 12345.pdf, 67890.pdf

# Custom output directory
pm-download --output-dir ./pdfs/

# Output to stdout (single article only)
pm-download --stdout > article.pdf

# Dry run: show what would be downloaded
pm-download --dry-run               # prints: "Would download: PMID 12345 -> PMC1234567.pdf"
```

### Output Naming Convention

```
{pmid}.pdf              # Default: use PMID as filename
{pmid}-{doi_suffix}.pdf # If --include-doi flag (rare, DOI can have slashes)
```

## Data Flow Analysis

### Source Priority

1. **PMC Direct** (highest priority)
   - If article has PMCID, check PMC OA Service for PDF
   - Pros: Official source, stable URLs, no rate limit concerns
   - Cons: Only ~20% of PubMed articles are in PMC

2. **Unpaywall** (fallback)
   - If article has DOI, query Unpaywall API for OA PDF URL
   - Pros: Covers 50-85% of articles across all publishers
   - Cons: Rate limited (100k/day), requires email parameter

3. **No source available**
   - Article not Open Access
   - Report in summary output

### ID Requirements

| Source | Required ID | Available in pm-parse | Notes |
|--------|-------------|----------------------|-------|
| PMC OA | PMCID | No* | Need to extract from XML or use ID converter |
| Unpaywall | DOI | Yes | Already in pm-parse output |

*Currently pm-parse extracts DOI but not PMCID. Need to add PMCID extraction.

### ID Conversion Strategy

For input PMIDs without JSONL context:
1. Use NCBI ID Converter API to get DOI and PMCID
2. Base URL: `https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/`
3. Batch up to 200 IDs per request
4. Response includes: pmid, pmcid, doi

## API Details

### PMC OA Service

**Endpoint:** `https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi`

**Single article lookup:**
```bash
curl "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=PMC5334499&format=pdf"
```

**Response format:**
```xml
<OA>
  <records>
    <record id="PMC5334499" citation="..." license="CC BY">
      <link format="pdf" updated="2017-03-09 13:55:42"
            href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/..."/>
    </record>
  </records>
</OA>
```

**Rate limits:** Not explicitly documented (be conservative: ~3 req/sec like other NCBI APIs)

**Error cases:**
- No PDF available: `<error>` element in response
- Article not in OA subset: empty `<records>`

### NCBI ID Converter API

**Endpoint:** `https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/`

**Batch conversion:**
```bash
curl "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/?ids=12345,67890&format=json&tool=pm-download&email=user@example.com"
```

**Response (JSON):**
```json
{
  "status": "ok",
  "records": [
    {"pmid": "12345", "pmcid": "PMC1234567", "doi": "10.1234/example"},
    {"pmid": "67890", "pmcid": null, "doi": "10.5678/other"}
  ]
}
```

**Batch limit:** 200 IDs per request
**Rate limit:** Not documented (use 3 req/sec)

### Unpaywall API

**Endpoint:** `https://api.unpaywall.org/v2/{doi}?email={email}`

**Request:**
```bash
curl "https://api.unpaywall.org/v2/10.1038/nature12373?email=user@example.com"
```

**Response (JSON):**
```json
{
  "doi": "10.1038/nature12373",
  "is_oa": true,
  "best_oa_location": {
    "url_for_pdf": "https://europepmc.org/articles/pmc3998951?pdf=render",
    "license": "cc-by"
  }
}
```

**Rate limit:** 100,000 requests/day (no per-second limit documented)
**Requirement:** Email parameter mandatory

**Key fields:**
- `is_oa`: boolean - article is open access
- `best_oa_location.url_for_pdf`: direct PDF URL (may be null even if is_oa=true)
- `oa_locations`: array of all OA locations if multiple exist

## Edge Cases and Error Handling

### ID-Related

| Scenario | Handling |
|----------|----------|
| PMID with no DOI or PMCID | Skip, report in summary |
| PMID not in PMC | Fall back to Unpaywall via DOI |
| DOI returns is_oa=false | Report as "not available" |
| DOI returns is_oa=true but no pdf_url | Try landing page or skip |

### Download-Related

| Scenario | Handling |
|----------|----------|
| PDF URL returns 404 | Log error, continue with next |
| PDF URL returns non-PDF content | Detect via Content-Type, skip |
| PDF already exists locally | Skip by default, --overwrite to redownload |
| Network timeout | Configurable timeout (default 30s), log and continue |
| Disk full | Exit with error |

### Rate Limiting

| API | Strategy |
|-----|----------|
| NCBI (ID Converter, OA Service) | 0.34s delay between requests (~3/sec) |
| Unpaywall | No delay needed (100k/day is generous) |
| PDF downloads | Parallel (--parallel N, default 1) |

## CLI Interface Design

### Options

```
pm-download - Download full-text PDFs from PubMed Central and Unpaywall

Usage:
  pm-parse output | pm-download [OPTIONS]
  pm-download [OPTIONS] < pmids.txt
  pm-download [OPTIONS] --input pmids.txt

Input Options:
  --input FILE         Read PMIDs from file (one per line)
  --jsonl              Input is JSONL (auto-detected from pm-parse)

Output Options:
  --output-dir DIR     Output directory (default: current directory)
  --overwrite          Overwrite existing files
  --dry-run            Show what would be downloaded, don't download

Download Options:
  --parallel N         Parallel downloads (default: 1)
  --timeout SECS       Download timeout in seconds (default: 30)
  --email EMAIL        Email for Unpaywall API (required for Unpaywall)

Source Options:
  --pmc-only           Only use PMC (skip Unpaywall)
  --unpaywall-only     Only use Unpaywall (skip PMC)

General:
  -v, --verbose        Show progress on stderr
  -h, --help           Show this help message

Exit Codes:
  0 - All requested PDFs downloaded successfully
  1 - Some PDFs failed to download (partial success)
  2 - No PDFs downloaded (complete failure)
  3 - Usage error or missing dependencies
```

### Progress Output (--verbose)

```
[1/100] PMID 12345: Found in PMC (PMC1234567), downloading...
[2/100] PMID 67890: Not in PMC, trying Unpaywall...
[2/100] PMID 67890: Found via Unpaywall, downloading...
[3/100] PMID 11111: No DOI or PMCID, skipping
...
Summary: 85 downloaded, 10 not available, 5 errors
```

### Dry Run Output

```
$ pm-download --dry-run < pmids.txt
PMID 12345: Would download from PMC (PMC1234567)
PMID 67890: Would download via Unpaywall (10.1038/nature12373)
PMID 11111: No source available (no DOI or PMCID)

Summary: 2 available, 1 not available
```

## Implementation Phases (TDD)

### Phase 1: Prerequisites - Add PMCID to pm-parse

Before implementing pm-download, pm-parse needs to extract PMCID from XML.

**1.1 Test: pm-parse extracts PMCID when present**
```bash
@test "pm-parse extracts PMCID when present" {
    # Given: XML with PMCID
    local xml='<PubmedArticle>...<ArticleId IdType="pmc">PMC1234567</ArticleId>...</PubmedArticle>'

    # When: parsing
    result=$(echo "$xml" | pm-parse | jq -r '.pmcid')

    # Then: PMCID is extracted
    [ "$result" == "PMC1234567" ]
}
```

**1.2 Test: pm-parse omits pmcid field when not present**

**1.3 Implementation: Add PMCID extraction to pm-parse awk script**

### Phase 2: Core Infrastructure

**2.1 Test: pm-download --help shows usage**

**2.2 Test: pm-download requires input (fails with no stdin and no --input)**

**2.3 Test: pm-download --dry-run parses JSONL input correctly**

**2.4 Test: pm-download --dry-run parses PMID input correctly**

**2.5 Implementation: Argument parsing, input handling**

### Phase 3: ID Conversion (for PMID-only input)

**3.1 Test: ID converter batches requests (max 200 per call)**

**3.2 Test: ID converter extracts PMCID and DOI from response**

**3.3 Test: ID converter handles missing IDs gracefully**

**3.4 Test: ID converter respects rate limit (mock timing)**

**3.5 Implementation: lib/pm-idconv.sh or inline function**

### Phase 4: PMC OA Service Integration

**4.1 Test: PMC lookup returns PDF URL for valid PMCID**

**4.2 Test: PMC lookup returns empty for non-OA article**

**4.3 Test: PMC lookup handles API errors gracefully**

**4.4 Test: PMC lookup respects rate limit**

**4.5 Implementation: lib/pm-pmc.sh or inline function**

### Phase 5: Unpaywall Integration

**5.1 Test: Unpaywall lookup returns PDF URL for valid DOI**

**5.2 Test: Unpaywall lookup handles is_oa=false**

**5.3 Test: Unpaywall lookup handles missing url_for_pdf**

**5.4 Test: Unpaywall requires --email parameter**

**5.5 Implementation: lib/pm-unpaywall.sh or inline function**

### Phase 6: PDF Download

**6.1 Test: Downloads PDF to correct location**

**6.2 Test: Skips existing files (without --overwrite)**

**6.3 Test: --overwrite replaces existing files**

**6.4 Test: Handles download timeout**

**6.5 Test: Detects non-PDF response (Content-Type check)**

**6.6 Implementation: Download function with curl**

### Phase 7: Full Pipeline Integration

**7.1 Test: Pipeline from pm-parse works end-to-end (with mocks)**

**7.2 Test: PMID-only input works (with mocks)**

**7.3 Test: --parallel downloads multiple files concurrently**

**7.4 Test: Exit codes reflect success/partial/failure**

**7.5 Test: Summary output is correct**

### Phase 8: Edge Cases and Polish

**8.1 Test: Handles empty input gracefully**

**8.2 Test: --pmc-only skips Unpaywall**

**8.3 Test: --unpaywall-only skips PMC**

**8.4 Test: Articles with neither DOI nor PMCID are reported**

**8.5 Integration test with real APIs (optional, @skip in CI)**

## Dependencies

### Required
- `curl` - HTTP requests
- `jq` - JSON parsing (for API responses)

### Optional
- `parallel` - For --parallel > 1 downloads

## File Structure

```
bin/
  pm-download            # Main executable

lib/
  pm-common.sh           # Existing shared functions
  pm-download-lib.sh     # Download-specific functions (optional)

test/
  pm-download.bats       # Main tests

fixtures/
  mock-responses/        # Canned API responses for testing
    pmc-oa-success.xml
    pmc-oa-no-pdf.xml
    idconv-success.json
    unpaywall-success.json
    unpaywall-not-oa.json
```

## Risk Assessment

### High Risk
- **API changes**: Both PMC and Unpaywall APIs may change
  - Mitigation: Use versioned endpoints, handle errors gracefully
- **Rate limiting**: Hitting limits could block downloads
  - Mitigation: Conservative delays, clear --email requirement for Unpaywall

### Medium Risk
- **PDF availability**: Many articles aren't OA
  - Mitigation: Clear reporting, try multiple sources
- **Redirect handling**: Some PDF URLs redirect multiple times
  - Mitigation: Use curl -L (follow redirects)

### Low Risk
- **Filename collisions**: PMIDs are unique
- **Disk space**: User responsibility, but detect and fail gracefully

## Success Criteria

1. Downloads PDFs from PMC for articles with PMCID in OA subset
2. Falls back to Unpaywall for articles with DOI
3. Reports unavailable articles clearly
4. Respects rate limits for all APIs
5. --dry-run shows accurate preview without downloading
6. Exit codes accurately reflect success/partial/failure
7. Integrates seamlessly with existing pm-* pipeline

## Open Questions

1. **Should pm-parse extract PMCID?**
   - Pros: Avoids extra API call when PMCID is in XML
   - Cons: Increases pm-parse complexity slightly
   - **Recommendation: Yes** - PMCID is already in ~7% of baseline articles

2. **Should --email be required or optional?**
   - If required: Clear error message, Unpaywall always works
   - If optional: PMC-only by default, Unpaywall requires explicit --email
   - **Recommendation: Optional** - PMC-only works without email

3. **Parallel downloads default?**
   - 1 = safe default, user can increase
   - **Recommendation: 1** - conservative default, explicit --parallel N for speed

## References

- [PMC OA Web Service API](https://pmc.ncbi.nlm.nih.gov/tools/oa-service/)
- [PMC ID Converter API](https://pmc.ncbi.nlm.nih.gov/tools/id-converter-api/)
- [Unpaywall API](https://unpaywall.org/products/api)
- [Unpaywall Data Format](https://support.unpaywall.org/support/solutions/articles/44002142311-what-do-the-fields-in-the-api-response-and-snapshot-records-mean-)
