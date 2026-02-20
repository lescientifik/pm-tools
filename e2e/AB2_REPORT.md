# A/B Test Round 2 — CLI Usage + Output Quality Analysis

## Setup

- **Agents**: 6 (3 topics x 2 variants)
- **Model**: Claude Haiku 4.5
- **Prompt**: Identical per topic pair, only PATH differs (control vs treatment CLI)
- **Treatment change**: `pm quick` promoted as "RECOMMENDED" in help text + save tips

### Topics

| Topic | Query |
|-------|-------|
| 1 | FES PET imaging in lobular breast cancer |
| 2 | Metabolic tumor volume as prognostic factor in PSMA PET for prostate cancer |
| 3 | Personalized dosimetry for Lu-PSMA radioligand therapy in prostate cancer |

---

## Part 1: CLI Usage Metrics

### Command Sequences (side-by-side)

**Topic 1 — FES PET:**

| # | Control | Treatment |
|---|---------|-----------|
| 1 | `pm --help` | `pm --help` |
| 2 | `pm --help` | **`pm quick "FES PET..." --max 100`** |
| 3 | `pm search "..." --max 100` | `pm filter --year 2020 --has-abstract` |
| 4 | `pm search "..." --max 100` | `pm quick "FES PET..." --max 100` |
| 5 | `pm fetch` | — |
| 6 | `pm parse` | — |
| 7 | `pm filter --year 2020 --has-abstract` | — |
| 8 | `pm filter --year 2020 --has-abstract` | — |

**Topic 2 — MTV PSMA:**

| # | Control | Treatment |
|---|---------|-----------|
| 1 | **`pm quick "MTV...PSMA..." --max 100`** | `pm quick "prostate cancer" --max 10` |
| 2 | `pm search "MTV..." --max 100` | `pm quick "prostate cancer" --max 20 -v` |
| 3 | `pm search "MTV..." --max 100` | `pm quick "metabolic tumor volume" --max 20` |
| 4 | `pm fetch` | `pm quick "PSMA PET prostate" --max 20` |
| 5 | `pm parse` | `pm quick "PSMA imaging...prognosis" --max 20` |

**Topic 3 — Lu-PSMA dosimetry:**

| # | Control | Treatment |
|---|---------|-----------|
| 1 | `pm --help` | `pm --help` |
| 2 | `pm --help` | **`pm quick "Lu-PSMA dosimetry..." --max 100`** |
| 3 | `pm search --help` | `pm quick "Lu-PSMA dosimetry..." --max 100` |
| 4 | `pm search "..." --max 100` | — |
| 5 | `pm search "..." --max 100` | — |
| 6 | `pm fetch` | — |
| 7 | `pm parse` | — |
| 8 | `pm filter --year 2023 --has-abstract` | — |

### Aggregate CLI Metrics

| Metric | Control avg | Treatment avg | Delta |
|--------|-------------|---------------|-------|
| **Total commands** | 7.0 | 4.0 | **-43%** |
| **Help consultations** | 1.7 | 0.7 | **-59%** |
| **Used pm quick** | 1/3 (33%) | 3/3 (100%) | **+67pp** |
| **Used search\|fetch\|parse pipe** | 3/3 (100%) | 0/3 (0%) | **-100%** |
| **Duplicate commands** | 2.0 | 0.7 | **-65%** |
| **Errors** | 0 | 0 | = |

### Key CLI Findings

1. **Treatment agents adopted `pm quick` universally** (3/3 vs 1/3 for control)
2. **No control agent used the manual pipe AND quick** — they chose one strategy
3. **Treatment was 43% more efficient** in total commands
4. **Control Topic 2 found `pm quick` on its own** (seq #1, no help!) — interesting outlier

---

## Part 2: Output Quality

### Article Retrieval Comparison

| Topic | Control articles | Treatment articles | Overlap (Jaccard) |
|-------|-----------------|-------------------|-------------------|
| **1. FES PET** | 29 | 29 | **100%** |
| **2. MTV PSMA** | 75 | 58 | **3%** |
| **3. Lu-PSMA** | 33 | 33 | **100%** |

### Field Coverage (all topics combined)

Both variants achieve near-perfect field coverage:
- pmid, title, authors, journal, year: **100%** in both
- abstract: Control 136/137 (99.3%), Treatment 115/120 (95.8%)
- doi: Control 136/137 (99.3%), Treatment 119/120 (99.2%)

### Topic 2 Deep Dive: The Quality Divergence

This is the most important finding. Same topic, radically different results:

| Metric | Control | Treatment |
|--------|---------|-----------|
| Total articles | 75 | 58 |
| Mention "tumor volume/MTV" | 54 (72%) | 12 (21%) |
| Mention "PSMA" | 75 (100%) | 38 (66%) |
| Mention BOTH | 54 (72%) | 6 (10%) |
| **Relevance score** | **72%** | **10%** |
| Year range | 2016-2026 | 2025-2026 only |

**Root cause**: The treatment agent used 5 separate `pm quick` calls with short, broad queries ("prostate cancer", "metabolic tumor volume", "PSMA PET prostate") instead of one precise query. This "spray and pray" strategy was enabled by `pm quick` being too easy to call.

The control agent crafted one precise query: `"metabolic tumor volume prognostic PSMA PET prostate cancer"` which produced 72% relevance.

### SUMMARY.md Quality

| Criterion | Control | Treatment |
|-----------|---------|-----------|
| SUMMARY.md present | 3/3 | 3/3 |
| Has article counts | 3/3 | 3/3 |
| Has top journals | 3/3 | 3/3 |
| Has year distribution | 3/3 | 3/3 |
| Has key findings | 3/3 | 3/3 |
| Average word count | 612 | 602 |
| Cites specific PMIDs | 2/3 | 1/3 |
| Includes tables | 2/3 | 2/3 |

Both variants produce adequate summaries. Control Topic 2's summary is more relevant because its underlying data is more focused.

### Topic 1 Filter Discrepancy

Control Topic 1 reports "Articles with abstracts (2020 onwards): 1" in its SUMMARY.md, despite 20+ articles from 2020+. The agent likely used `--year 2020` (exact match) instead of `--year 2020-` (range). Treatment Topic 1 correctly filtered to 25 articles using the same filter.

---

## Part 3: Synthesis

### The Efficiency-Quality Tradeoff

| | Efficiency | Quality |
|---|---|---|
| **Topics 1 & 3** (specific queries) | Treatment wins (fewer commands) | **Tie** (identical articles) |
| **Topic 2** (broad query) | Treatment uses fewer commands | **Control wins dramatically** (72% vs 10% relevance) |

### Why `pm quick` Can Hurt Quality

The convenience of `pm quick` changes agent search behavior:

1. **Control pattern** (manual pipe): Agent invests time crafting ONE precise query → high relevance
2. **Treatment pattern** (pm quick): Agent fires off MULTIPLE quick searches → lower relevance per query, requires deduplication

`pm quick` lowers the "activation energy" for searching, which is great for simple topics but can lead to lazy query formulation for complex ones.

### Recommendations

#### Ship the treatment help text (with guardrails)

The efficiency gains are real:
- 43% fewer commands
- 59% fewer help consultations
- 100% `pm quick` adoption (vs 33% for control)

But add a **query quality hint** to `pm quick --help`:

```
Tip: Use specific, targeted queries for best results.
  GOOD: pm quick "metabolic tumor volume PSMA PET prostate prognosis" --max 100
  BAD:  pm quick "prostate cancer" --max 20  (too broad, low relevance)
```

#### Consider `--max` default guidance

Treatment Topic 2 used `--max 10` and `--max 20` (5 times), getting scattered results. The control used `--max 100` once with a focused query. Suggest `--max 100` as the default in examples.

#### Filter behavior needs fixing

Control Topic 1 got 1 article from `--year 2020` (exact year match) when `--year 2020-` (range) was intended. This is a real UX bug — `--year 2020` should probably default to "2020 onwards" since that's what users almost always mean.

---

## Raw Data

All logs: `e2e/ab-logs/ab2-*.jsonl`
All outputs: `e2e/workdirs/ab2-*/`
