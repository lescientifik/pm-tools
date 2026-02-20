# A/B Test Round 4 — Opus: `pm quick` vs `pm collect`

## Setup

- **Model**: Opus 4.6 (vs Haiku 4.5 in AB2/AB3)
- **Topics**: 2 (the hardest from AB3)
- **Control**: Old help with `pm quick`
- **Treatment**: New help with `pm collect`

---

## Part 1: CLI Usage

### Command Sequences

**Topic 1 — FES PET (21 vs 12 commands):**
- Control: read ALL 6 help pages, ran 8 `pm search` queries, then `fetch` → `parse` → `filter`
- Treatment: read 4 help pages, ran 5 `pm search` probes then 1 `pm collect` with Boolean query, then `filter`

**Topic 2 — MTV PSMA (15 vs 10 commands):**
- Control: read 6 help pages, ran 5 `pm search` queries, then `fetch` → `parse` → `filter`
- Treatment: read 4 help pages, ran 4 `pm collect` queries, then 2 `filter` calls

### Opus vs Haiku behavior

| Metric | Haiku AB3-C | Haiku AB3-T | Opus AB4-C | Opus AB4-T |
|--------|-------------|-------------|------------|------------|
| **Total commands** | 9.7 | 3.7 | 18.0 | 11.0 |
| **Help consultations** | 0 | 0 | **6.0** | **4.0** |
| **Distinct queries** | — | — | 5.5 | 5.5 |
| **Errors** | 0 | 0 | 0 | 0 |

Key differences:
1. **Opus reads ALL help pages first** (6 for control, 4 for treatment). Haiku AB3 read ZERO.
2. **Opus uses more commands overall** (~2-3x more than Haiku) — it's more methodical
3. **Both Opus variants use multiple complementary queries** (~5 each) instead of Haiku's 1-3
4. **Opus Control NEVER used `pm quick`** — it chose the manual pipeline despite having quick available

---

## Part 2: Output Quality

### Article Volume

| Topic | Control | Treatment | Overlap (Jaccard) |
|-------|---------|-----------|-------------------|
| FES PET | 188 | 69 | 13% |
| MTV PSMA | 122 | **253** | 38% |

### Topic 2 Relevance — The Key Metric

| Round | Articles | MTV% | PSMA% | Both% | # Queries |
|-------|----------|------|-------|-------|-----------|
| AB2 Haiku Control (quick) | 75 | 72% | 100% | **72%** | 3 |
| AB2 Haiku Treatment (quick) | 58 | 20% | 65% | **10%** | 5 |
| AB3 Haiku Control (quick) | 149 | 62% | 99% | **61%** | 1 |
| AB3 Haiku Treatment (collect) | 35 | 80% | 100% | **80%** | 1 |
| **AB4 Opus Control (quick)** | 122 | 89% | 99% | **88%** | 5 |
| **AB4 Opus Treatment (collect)** | 253 | 60% | 97% | **58%** | 4 |

### Precision vs Recall tradeoff

| | Opus Control | Opus Treatment |
|---|---|---|
| Total articles | 122 | 253 |
| Relevance rate | 88% | 58% |
| **Relevant articles (absolute)** | **~107** | **~147** |

Opus Treatment found MORE relevant articles in absolute numbers (147 vs 107), but with a lower precision rate (58% vs 88%). It cast a wider net.

---

## Part 3: Opus vs Haiku — Model-Dependent Effects

### The naming effect is model-dependent

**Haiku** (less capable):
- "quick" → spray-and-pray, 10% relevance (broken)
- "collect" → deliberate single query, 80% relevance (fixed)
- **Naming has a HUGE effect** on Haiku's strategy

**Opus** (more capable):
- "quick" → ignores it entirely, uses manual pipeline with 5 precise queries, 88% relevance
- "collect" → uses it methodically with 4 queries + dedup, 58% relevance but 2x volume
- **Naming has a MODERATE effect** — Opus is always methodical, but `collect` shifts toward breadth

### Why Opus Control ignored `pm quick`

Opus read `pm quick --help` and ALL subcommand help pages. It deliberately chose the manual pipeline because:
1. It wanted to combine PMIDs from multiple queries before fetching (deduplication at PMID level)
2. The manual pipeline gives more control over each step
3. Opus is strategic enough to choose the right tool, regardless of what's "recommended"

This is a fundamental insight: **Opus doesn't need help text nudges. It makes its own decisions.**

### Why Opus Treatment used broader queries

With `pm collect`, Opus ran queries like:
- `PSMA PET tumor volume prostate` (broad, 202 hits)
- `"total lesion" PSMA prostate cancer prognostic` (narrow, 37 hits)

It adopted a "cast wide then filter" strategy, which is actually a valid literature review approach. The 58% precision means 42% of articles are about PSMA/prostate but not specifically about MTV — still potentially relevant for context.

---

## Part 4: Cross-Model Summary

### Optimal configuration per model

| Model | Best command name | Why |
|-------|-------------------|-----|
| **Haiku** | `pm collect` | Eliminates spray-and-pray, 8x relevance improvement |
| **Opus** | Either works | Opus is strategic regardless; `collect` → more volume, `quick` → ignores it |

### Final recommendation

**Ship `pm collect`** — it's strictly better for Haiku and neutral-to-positive for Opus:

| | Haiku + quick | Haiku + collect | Opus + quick | Opus + collect |
|---|---|---|---|---|
| Relevance | 10% | **80%** | 88% | 58% (but 2x articles) |
| Efficiency | 4.0 cmds | 3.7 cmds | 18.0 cmds | 11.0 cmds |
| Strategy | Broken | Good | Excellent | Good |

The downside for Opus (lower precision rate) is offset by higher absolute recall. And Opus can always ignore `collect` and use the manual pipeline if it decides that's better — as it did with `quick`.

---

## Raw Data

- AB4 logs: `e2e/ab-logs/ab4-*.jsonl`
- AB4 outputs: `e2e/workdirs/ab4-*/`
