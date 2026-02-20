# E2E Agent Test Report — pm CLI Usage by Haiku Agents

## Test Setup

- **Model**: Claude Haiku 4.5
- **Agents**: 3, running in parallel
- **Prompt**: Simple instructions to use `pm --help`, search PubMed, and save results
- **Spy mechanism**: Python wrapper logging every pm invocation to per-agent JSONL files

### Research Topics

| Agent | Topic | Articles Found |
|-------|-------|---------------|
| agent1 | FES PET imaging in lobular breast cancer | 29 |
| agent2 | Metabolic tumor volume (MTV) in PSMA PET for prostate cancer | 100 |
| agent3 | Personalized dosimetry for Lu-PSMA radioligand therapy | 100 |

---

## Summary Metrics

| Metric | agent1 | agent2 | agent3 |
|--------|--------|--------|--------|
| Total commands | 23 | 26 | 21 |
| Help consultations | 8 | 10 | 7 |
| Unique subcommands used | 8 | 6 | 7 |
| Errors (exit≠0) | 0 | 0 | 1 |
| Duplicate commands | 8 | 11 | 5 |
| Invalid flags attempted | 0 | 4 | 3 |
| Used `pm quick` | No | No | No |

---

## Key Findings

### 1. `pm quick` was NEVER discovered

All 3 agents built the pipeline manually (`search | fetch | parse`) instead of using `pm quick`. This is the single biggest efficiency win we're missing.

**Root cause**: `pm quick` appears in `pm --help` but without enough context. Agents see the examples section showing the pipe pattern first and adopt it.

**Recommendation**:
- Add a **"Recommended for AI agents"** hint next to `pm quick` in the main help
- Add a hint at the end of `pm search --help`: *"Tip: Use `pm quick` to run the full pipeline in one command"*

### 2. Agents try verbose/debug flags that don't exist

All 3 agents tried `--verbose`, `-v`, or `-v 2` on `fetch` and `parse`. These flags are silently accepted (exit=0) but do nothing.

**Attempts observed**:
- `pm fetch --verbose` (agent2)
- `pm fetch -v` (agent3)
- `pm fetch -v 2` (agent2, agent3)
- `pm parse --verbose` (agent2)
- `pm parse -v 2` (agent3)
- `pm filter -v` (agent1)

**Recommendation**:
- Add `--verbose` / `-v` flag to commands (especially `fetch` which is slow and benefits from progress feedback)
- OR reject unknown flags with a clear error message

### 3. Excessive command duplication (search re-runs)

Agents re-ran the same `pm search` command 2-5x. This is wasteful and suggests confusion about how to reuse results.

| Agent | Same search repeated |
|-------|---------------------|
| agent1 | `pm search ... --max 100` — 5x |
| agent2 | Same search — 4x + reformulated search — 3x |
| agent3 | Same search — 2x + reformulated search — 2x |

**Root cause**: Agents pipe search results directly and lose them. When they need the PMIDs again (for a different pipeline), they re-search.

**Recommendation**:
- Add a hint in `pm search --help`: *"Tip: Save PMIDs to a file for reuse: `pm search ... > pmids.txt`"*
- The caching in `.pm/` should help, but agents don't realize results are cached
- Consider adding `pm search --output pmids.txt` convenience flag

### 4. Help was re-consulted mid-session (memory loss)

All agents consulted `pm --help` at least twice. Agent2 re-read all 4 helps (search, fetch, parse, --help) a second time mid-session.

**Recommendation**:
- Keep help text concise (already good)
- Consider adding a cheat sheet command: `pm examples` or `pm cheatsheet` showing common workflows

### 5. Discovery order: `parse` before `fetch` (agent1)

Agent1 discovered commands in order: `search → parse → fetch`, meaning it tried to parse before fetching. This is because it ran a pipe `search | fetch | parse` but in the logs, parse finished before fetch (parallel pipe processes).

This is actually correct behavior (pipes work), but agent1 also ran `pm filter` with stdin from search output (PMIDs) instead of JSONL, which would produce wrong results silently.

**Recommendation**:
- `pm filter` should validate that stdin is JSONL and show a helpful error if it gets PMIDs instead
- `pm parse` should error clearly if it receives non-XML input

### 6. `pm init` confusion

Agent3 ran `pm init` twice (second time failed with exit=1). Agent1 ran it once mid-session.

**Recommendation**:
- `pm init` on already-initialized directory should be idempotent (exit 0, print "already initialized")
- Make it clearer in help that `pm init` is optional (caching works without it)

### 7. Agents never used `pm diff` or `pm download`

No agent attempted these commands, which is expected given the research-focused prompts. But it validates that the help text doesn't confuse agents into thinking they need these commands.

---

## Ideal vs Actual Command Sequences

### Ideal sequence (what we want agents to do)
```
pm --help                           # 1 cmd
pm quick "query" --max 100 > results.jsonl  # 1 cmd (replaces search|fetch|parse)
pm filter --year 2024 < results.jsonl       # 1 cmd
pm cite < pmids.txt                         # 1 cmd
```
**Total: 4 commands**

### What agents actually did
```
pm --help                          # discover commands
pm search --help                   # learn search syntax
pm search "query" --max 100        # search
pm search "query" --max 100 | pm fetch | pm parse > results.jsonl  # re-search + pipeline
pm filter --help                   # learn filter
pm filter --year 2024 < results.jsonl  # filter
pm search "query" --max 100        # re-search AGAIN for cite
pm cite --help                     # learn cite
pm cite < pmids.txt                # cite
```
**Total: ~15-25 commands** (3-6x more than optimal)

---

## Priority Recommendations

### High Priority (biggest impact)

1. **Promote `pm quick` aggressively** — Add "RECOMMENDED" label in main help, add tips in search/fetch/parse help
2. **Reject unknown flags** — `--verbose`, `-v`, `-v 2` should produce a clear error, not silent success
3. **Add "save results" hint** — Tell agents to save PMIDs/JSONL to files for reuse

### Medium Priority

4. **Add `--verbose`/`-v` for real** — Agents expect it, so implement progress output on fetch
5. **Make `pm init` idempotent** — Don't error on re-init
6. **Input validation** — `pm filter` should reject non-JSONL input, `pm parse` should reject non-XML

### Low Priority

7. **Add `pm examples`** — Quick reference of common workflows
8. **Consider `pm search --save`** — Auto-save PMIDs to file for reuse
