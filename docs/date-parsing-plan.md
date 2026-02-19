# Complete Date Parsing Implementation Plan

## Executive Summary

This document details the plan for implementing complete date parsing in `pm parse`, enhancing the current year-only extraction to support full dates with ISO 8601 output format.

---

## 1. Current State Analysis

### Current Implementation (pm parse)

```awk
# Extract year from PubDate/Year
/\/PubDate\/Year=/ {
    if (year == "") {  # Take first year only
        split($0, parts, "=")
        year = parts[2]
    }
    next
}

# Extract year from MedlineDate (format: "YYYY Mon-Mon" or "YYYY Mon")
/\/PubDate\/MedlineDate=/ {
    if (year == "") {
        val = substr($0, index($0, "=") + 1)
        # Extract first 4-digit year
        if (match(val, /[0-9][0-9][0-9][0-9]/)) {
            year = substr(val, RSTART, 4)
        }
    }
    next
}
```

**Current output:** `"year": "1975"`

**Limitation:** Only the year is extracted; month, day, and season information is discarded.

---

## 2. Date Format Analysis (30,000 articles baseline)

### 2.1 PubDate Structure Distribution

| Format | Count | Percentage | Example |
|--------|-------|------------|---------|
| Year + Month + Day | 7,494 | 25.0% | `<Year>1975</Year><Month>Oct</Month><Day>27</Day>` |
| Year + Month | 14,309 | 47.7% | `<Year>1975</Year><Month>Jun</Month>` |
| Year only | 5,478 | 18.3% | `<Year>1976</Year>` |
| Year + Season | 86 | 0.3% | `<Year>1975</Year><Season>Summer</Season>` |
| MedlineDate | 2,633 | 8.8% | `<MedlineDate>1975 Jul-Aug</MedlineDate>` |

**Total: 30,000 articles**

### 2.2 DTD Specification

From `pubmed_250101.dtd`:
```dtd
<!ELEMENT PubDate ((Year, ((Month, Day?) | Season)?) | MedlineDate) >
<!ELEMENT Year (#PCDATA) >
<!ELEMENT Month (#PCDATA) >
<!ELEMENT Day (#PCDATA )>
<!ELEMENT Season (#PCDATA) >
<!ELEMENT MedlineDate (#PCDATA) >
```

**Valid combinations:**
1. `Year` only
2. `Year` + `Month`
3. `Year` + `Month` + `Day`
4. `Year` + `Season`
5. `MedlineDate` (free-text, no structured fields)

### 2.3 Month Format Variations

Months appear in two formats within PubDate elements:
- **Text format:** Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec
- **Numeric format:** 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12 (also: 1-12 without leading zero in some contexts)

**Note:** PubDate uses text format (Jan, Feb...); DateCompleted/DateRevised use numeric format.

### 2.4 Season Values

| Season | Count |
|--------|-------|
| Summer | 29 |
| Winter | 21 |
| Spring | 19 |
| Fall | 17 |

**Total: 86 articles with seasons**

### 2.5 MedlineDate Pattern Analysis

| Pattern | Count | Example |
|---------|-------|---------|
| Year + Month range (YYYY Mon-Mon) | 2,526 | `1975 Jul-Aug`, `1976 Nov-Dec` |
| Year + Day range (YYYY Mon D-D) | 90 | `1977 Jul 4-7`, `1976 Dec 13-15` |
| Year range (YYYY-YYYY) | 8 | `1975-1976`, `1976-1977` |
| Cross-year range (YYYY Mon-YYYY Mon) | 4 | `1975 Dec-1976 Jan` |
| Year range + Season | 3 | `1976-1977 Winter`, `1977-1978 Fall-Winter` |
| Cross-month day range | 2 | `1976 Sep 30-Oct 2` |

**Total: 2,633 MedlineDate entries**

**Notable patterns found:**
- Case variations: `MAR-APR`, `JAN-FEB`, `Jul-AUG` (mixed case)
- Quarter ranges: `1976 Apr-Jun`, `1977 Jan-Mar`
- Extended ranges: `1975 Jul-Dec`, `1976 Jan-Jun`

---

## 3. Output Format Design

### 3.1 Proposed Fields

```json
{
  "year": "1975",
  "date": "1975-06-27"
}
```

**Design decisions:**

1. **Keep `year` field** for backwards compatibility
2. **Add new `date` field** containing the most precise date representation
3. **Use ISO 8601 format** for `date` field

### 3.2 Date Field Format Rules

| Source Data | `date` Output | `year` Output |
|-------------|---------------|---------------|
| Year + Month + Day | `"1975-06-27"` (YYYY-MM-DD) | `"1975"` |
| Year + Month | `"1975-06"` (YYYY-MM) | `"1975"` |
| Year only | `"1975"` (YYYY) | `"1975"` |
| Year + Season | `"1975"` + special handling* | `"1975"` |
| MedlineDate | Best-effort extraction** | First year found |

### 3.3 Season Handling Strategy

**Option A: Map to quarter start date (Recommended)**
- Spring -> 03 (March)
- Summer -> 06 (June)
- Fall -> 09 (September)
- Winter -> 12 (December)

Output: `"date": "1975-06"` for `<Year>1975</Year><Season>Summer</Season>`

**Option B: Add season field**
```json
{
  "year": "1975",
  "date": "1975",
  "season": "Summer"
}
```

**Recommendation:** Option A is simpler and maintains consistent date format. Option B provides more information but adds complexity.

### 3.4 MedlineDate Handling Strategy

For MedlineDate entries, extract the most precise parseable date:

| MedlineDate | `date` Output | Notes |
|-------------|---------------|-------|
| `1975 Jul-Aug` | `"1975-07"` | Start month of range |
| `1975 Jul 4-7` | `"1975-07-04"` | Start date of range |
| `1975-1976` | `"1975"` | Start year only |
| `1975 Dec-1976 Jan` | `"1975-12"` | Start month |
| `1976-1977 Winter` | `"1976"` | Start year (season ambiguous across years) |

**Parsing rules:**
1. Extract first 4-digit year
2. If text month follows, extract and convert to numeric
3. If day follows month, extract if parseable
4. Ignore ranges (use start date only)

### 3.5 Month Name to Number Mapping

```awk
function month_to_num(m) {
    m = tolower(m)
    if (m == "jan") return "01"
    if (m == "feb") return "02"
    if (m == "mar") return "03"
    if (m == "apr") return "04"
    if (m == "may") return "05"
    if (m == "jun") return "06"
    if (m == "jul") return "07"
    if (m == "aug") return "08"
    if (m == "sep") return "09"
    if (m == "oct") return "10"
    if (m == "nov") return "11"
    if (m == "dec") return "12"
    return ""  # Unknown month
}
```

---

## 4. Test Plan

### 4.1 Test Categories

#### Category 1: Structured Dates (PubDate with Year/Month/Day)

| Test Case | Input XML | Expected `date` | Expected `year` |
|-----------|-----------|-----------------|-----------------|
| Full date (text month) | `<Year>1975</Year><Month>Oct</Month><Day>27</Day>` | `"1975-10-27"` | `"1975"` |
| Full date (single-digit day) | `<Year>1975</Year><Month>Jun</Month><Day>5</Day>` | `"1975-06-05"` | `"1975"` |
| Year + Month only | `<Year>1975</Year><Month>Jun</Month>` | `"1975-06"` | `"1975"` |
| Year only | `<Year>1976</Year>` | `"1976"` | `"1976"` |
| Year + Season | `<Year>1975</Year><Season>Summer</Season>` | `"1975-06"` | `"1975"` |

#### Category 2: MedlineDate Patterns

| Test Case | Input XML | Expected `date` | Expected `year` |
|-----------|-----------|-----------------|-----------------|
| Month range | `<MedlineDate>1975 Jul-Aug</MedlineDate>` | `"1975-07"` | `"1975"` |
| Month range (uppercase) | `<MedlineDate>1975 MAR-APR</MedlineDate>` | `"1975-03"` | `"1975"` |
| Day range | `<MedlineDate>1977 Jul 4-7</MedlineDate>` | `"1977-07-04"` | `"1977"` |
| Year range | `<MedlineDate>1975-1976</MedlineDate>` | `"1975"` | `"1975"` |
| Cross-year range | `<MedlineDate>1975 Dec-1976 Jan</MedlineDate>` | `"1975-12"` | `"1975"` |
| Year range + season | `<MedlineDate>1976-1977 Winter</MedlineDate>` | `"1976"` | `"1976"` |
| Cross-month day range | `<MedlineDate>1976 Sep 30-Oct 2</MedlineDate>` | `"1976-09-30"` | `"1976"` |
| Quarter range | `<MedlineDate>1976 Apr-Jun</MedlineDate>` | `"1976-04"` | `"1976"` |

#### Category 3: Edge Cases

| Test Case | Input XML | Expected `date` | Expected `year` |
|-----------|-----------|-----------------|-----------------|
| Numeric month (leading zero) | `<Year>1975</Year><Month>09</Month><Day>15</Day>` | `"1975-09-15"` | `"1975"` |
| Day with leading zero | `<Year>1975</Year><Month>Oct</Month><Day>01</Day>` | `"1975-10-01"` | `"1975"` |
| Missing day (month present) | `<Year>1975</Year><Month>Dec</Month>` | `"1975-12"` | `"1975"` |
| Mixed case month | `<Year>1975</Year><Month>DEC</Month>` | `"1975-12"` | `"1975"` |

#### Category 4: Backwards Compatibility

| Test Case | Assertion |
|-----------|-----------|
| `year` field unchanged | Output still contains `"year": "XXXX"` field |
| All existing tests pass | No regression in existing pm parse.bats tests |
| 30k baseline output | All 30,000 records parse without error |

### 4.2 Fixture Files to Create

```
fixtures/edge-cases/dates/
├── full-date.xml               # Year + Month + Day (text month)
├── year-month.xml              # Year + Month only
├── year-only.xml               # Year only (already exists as pmid-3341.xml)
├── year-season.xml             # Year + Season
├── medlinedate-month-range.xml # 1975 Jul-Aug
├── medlinedate-day-range.xml   # 1977 Jul 4-7
├── medlinedate-year-range.xml  # 1975-1976
├── medlinedate-cross-year.xml  # 1975 Dec-1976 Jan
├── medlinedate-season.xml      # 1976-1977 Winter
└── medlinedate-uppercase.xml   # 1975 MAR-APR
```

### 4.3 Test File Structure

New file: `test/pm parse-dates.bats`

```bash
#!/usr/bin/env bats

load test_helper

# Category 1: Structured Dates
@test "pm parse: full date (Year+Month+Day) produces ISO date" {
    run bash -c 'cat fixtures/edge-cases/dates/full-date.xml | pm parse'
    [ "$status" -eq 0 ]
    result=$(echo "$output" | jq -r '.date')
    [ "$result" = "1975-10-27" ]
}

@test "pm parse: year+month produces YYYY-MM format" {
    run bash -c 'cat fixtures/edge-cases/dates/year-month.xml | pm parse'
    [ "$status" -eq 0 ]
    result=$(echo "$output" | jq -r '.date')
    [ "$result" = "1975-06" ]
}

@test "pm parse: year only produces YYYY format" {
    run bash -c 'cat fixtures/edge-cases/dates/year-only.xml | pm parse'
    [ "$status" -eq 0 ]
    result=$(echo "$output" | jq -r '.date')
    [ "$result" = "1976" ]
}

@test "pm parse: year+season maps to quarter start" {
    run bash -c 'cat fixtures/edge-cases/dates/year-season.xml | pm parse'
    [ "$status" -eq 0 ]
    result=$(echo "$output" | jq -r '.date')
    [ "$result" = "1975-06" ]  # Summer -> June
}

# Category 2: MedlineDate
@test "pm parse: MedlineDate month range extracts start month" {
    run bash -c 'cat fixtures/edge-cases/dates/medlinedate-month-range.xml | pm parse'
    [ "$status" -eq 0 ]
    result=$(echo "$output" | jq -r '.date')
    [ "$result" = "1975-07" ]  # Jul-Aug -> July
}

@test "pm parse: MedlineDate day range extracts start date" {
    run bash -c 'cat fixtures/edge-cases/dates/medlinedate-day-range.xml | pm parse'
    [ "$status" -eq 0 ]
    result=$(echo "$output" | jq -r '.date')
    [ "$result" = "1977-07-04" ]  # Jul 4-7 -> July 4
}

@test "pm parse: MedlineDate year range extracts start year" {
    run bash -c 'cat fixtures/edge-cases/dates/medlinedate-year-range.xml | pm parse'
    [ "$status" -eq 0 ]
    result=$(echo "$output" | jq -r '.date')
    [ "$result" = "1975" ]
}

@test "pm parse: MedlineDate with uppercase months" {
    run bash -c 'cat fixtures/edge-cases/dates/medlinedate-uppercase.xml | pm parse'
    [ "$status" -eq 0 ]
    result=$(echo "$output" | jq -r '.date')
    [ "$result" = "1975-03" ]  # MAR-APR -> March
}

# Category 3: Backwards Compatibility
@test "pm parse: year field still present for backwards compatibility" {
    run bash -c 'cat fixtures/edge-cases/dates/full-date.xml | pm parse'
    [ "$status" -eq 0 ]
    year=$(echo "$output" | jq -r '.year')
    [ "$year" = "1975" ]
}

@test "pm parse: date and year fields both present" {
    run bash -c 'cat fixtures/edge-cases/dates/full-date.xml | pm parse'
    [ "$status" -eq 0 ]
    date=$(echo "$output" | jq -r '.date')
    year=$(echo "$output" | jq -r '.year')
    [ "$date" = "1975-10-27" ]
    [ "$year" = "1975" ]
}
```

---

## 5. Implementation Plan

### Phase 1: Create Test Fixtures (TDD - Red)

1. Create `fixtures/edge-cases/dates/` directory
2. Extract sample articles from baseline for each date format
3. Create synthetic fixtures for edge cases not found in baseline
4. Write `test/pm parse-dates.bats` with all test cases
5. Verify all tests FAIL (Red phase)

### Phase 2: Implement Date Parsing (TDD - Green)

1. Add new variables to pm parse awk script:
   ```awk
   month = ""
   day = ""
   season = ""
   medline_date = ""
   ```

2. Add extraction rules for Month, Day, Season:
   ```awk
   /\/PubDate\/Month=/ {
       if (month == "") {
           month = substr($0, index($0, "=") + 1)
       }
       next
   }

   /\/PubDate\/Day=/ {
       if (day == "") {
           day = substr($0, index($0, "=") + 1)
       }
       next
   }

   /\/PubDate\/Season=/ {
       if (season == "") {
           season = substr($0, index($0, "=") + 1)
       }
       next
   }
   ```

3. Add month conversion function
4. Add date assembly function:
   ```awk
   function build_date() {
       if (year == "") return ""

       # Handle MedlineDate
       if (medline_date != "") {
           return parse_medline_date(medline_date)
       }

       # Handle Season
       if (season != "") {
           m = season_to_month(season)
           if (m != "") return year "-" m
           return year
       }

       # Handle structured date
       if (month != "") {
           m = normalize_month(month)
           if (day != "") {
               d = sprintf("%02d", day)
               return year "-" m "-" d
           }
           return year "-" m
       }

       return year
   }
   ```

5. Add date field to JSON output:
   ```awk
   if (date != "") printf ",\"date\":\"%s\"", json_escape(date)
   ```

6. Run tests - all should PASS

### Phase 3: Refactor and Optimize (TDD - Refactor)

1. Extract date functions to make code more readable
2. Optimize regex matching for MedlineDate parsing
3. Add comments documenting format variations
4. Run tests - ensure all still PASS

### Phase 4: Baseline Validation

1. Run pm parse on full baseline
2. Verify all 30,000 records parse without error
3. Validate date field format for sample records
4. Update performance benchmarks

### Phase 5: Documentation

1. Update spec.md with new `date` field documentation
2. Update plan.md to mark this enhancement as complete
3. Update README examples if applicable

---

## 6. Risks and Mitigations

### Risk 1: MedlineDate Pattern Not Covered
**Risk:** Unknown MedlineDate format causes parsing error
**Mitigation:** Fallback to year-only extraction; log warning in verbose mode

### Risk 2: Performance Regression
**Risk:** Additional parsing slows down pm parse below 1000 articles/sec threshold
**Mitigation:**
- Benchmark after implementation
- Optimize regex patterns if needed
- Month lookup uses simple if-else (O(1) average)

### Risk 3: Backwards Compatibility Break
**Risk:** Existing scripts rely on current output format
**Mitigation:**
- Keep `year` field unchanged
- Add `date` field as new field (additive change)
- Document in changelog

---

## 7. Success Criteria

1. All tests in `test/pm parse-dates.bats` pass
2. All existing tests in `test/pm parse.bats` still pass
3. Full baseline (30,000 articles) parses without error
4. Performance remains above 1000 articles/sec
5. `date` field correctly formatted per ISO 8601 for all format types

---

## Appendix A: Sample Fixture Content

### full-date.xml
```xml
<PubmedArticle>
  <MedlineCitation Status="MEDLINE" Owner="NLM">
    <PMID Version="1">99999</PMID>
    <Article>
      <Journal>
        <JournalIssue CitedMedium="Print">
          <PubDate>
            <Year>1975</Year>
            <Month>Oct</Month>
            <Day>27</Day>
          </PubDate>
        </JournalIssue>
        <Title>Test Journal</Title>
      </Journal>
      <ArticleTitle>Test Article</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
```

### year-season.xml
```xml
<PubmedArticle>
  <MedlineCitation Status="MEDLINE" Owner="NLM">
    <PMID Version="1">99998</PMID>
    <Article>
      <Journal>
        <JournalIssue CitedMedium="Print">
          <PubDate>
            <Year>1975</Year>
            <Season>Summer</Season>
          </PubDate>
        </JournalIssue>
        <Title>Test Journal</Title>
      </Journal>
      <ArticleTitle>Test Article</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
```

### medlinedate-month-range.xml
```xml
<PubmedArticle>
  <MedlineCitation Status="MEDLINE" Owner="NLM">
    <PMID Version="1">99997</PMID>
    <Article>
      <Journal>
        <JournalIssue CitedMedium="Print">
          <PubDate>
            <MedlineDate>1975 Jul-Aug</MedlineDate>
          </PubDate>
        </JournalIssue>
        <Title>Test Journal</Title>
      </Journal>
      <ArticleTitle>Test Article</ArticleTitle>
    </Article>
  </MedlineCitation>
</PubmedArticle>
```

---

## Appendix B: Complete MedlineDate Regex Patterns

```awk
# Pattern matching for MedlineDate parsing
# Returns: array with [year, month, day] or partial

function parse_medline_date(md,    parts, year, month, day) {
    # Pattern 1: YYYY only
    if (match(md, /^[0-9]{4}$/)) {
        return md
    }

    # Pattern 2: YYYY-YYYY (year range)
    if (match(md, /^([0-9]{4})-[0-9]{4}/)) {
        return substr(md, 1, 4)
    }

    # Pattern 3: YYYY Mon-Mon or YYYY Mon
    if (match(md, /^([0-9]{4}) ([A-Za-z]{3})/)) {
        year = substr(md, 1, 4)
        # Extract month after year and space
        month_str = substr(md, 6, 3)
        month = month_to_num(month_str)
        if (month != "") {
            # Check for day: YYYY Mon D or YYYY Mon DD
            if (match(md, /^[0-9]{4} [A-Za-z]{3} ([0-9]{1,2})/)) {
                # Extract day number
                rest = substr(md, 10)
                if (match(rest, /^([0-9]{1,2})/)) {
                    day = substr(rest, RSTART, RLENGTH)
                    return year "-" month "-" sprintf("%02d", day)
                }
            }
            return year "-" month
        }
        return year
    }

    # Fallback: extract first 4-digit year
    if (match(md, /[0-9]{4}/)) {
        return substr(md, RSTART, 4)
    }

    return ""
}
```
