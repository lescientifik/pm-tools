# Designing CLIs for AI Agents — Synthesis

Reference document combining insights from [kumak.dev/self-documenting-cli-design-for-llms](https://kumak.dev/self-documenting-cli-design-for-llms/) and [clig.dev](https://clig.dev/), distilled for building agent-friendly command-line tools.

---

## 1. Progressive Disclosure over Documentation Dumps

Agents start fresh every session. Front-loading thousands of tokens of documentation is wasteful. Instead, design the CLI so agents can **discover capabilities incrementally**:

```
tool --help              → top-level overview (brief)
tool <command> --help    → command-specific details
tool <domain> --list     → enumerate available operations
tool <method> --describe → parameter schema for one operation
```

Each interaction reveals only what's needed for the next step. Five queries costing ~500 tokens beats a 5000-token documentation preamble.

**The tool itself is the documentation.** External docs drift from reality; the tool never lies about its own capabilities.

## 2. Errors That Teach

Every failed interaction must answer "what now?" — this is critical for agents that cannot visually browse docs.

### Suggestions on typos / unknown input
```
err: unknown command 'navigat'
Did you mean: navigate
```

### Guidance on empty results
```
No element matching "article h2"
Suggestions:
  Verify: tool eval "document.querySelector('article h2')"
  List:   tool snapshot --selector "article"
```

### Next steps after success
```
Navigated to https://example.com (loaded in 2.3s)
hint: use 'snapshot' to inspect content, 'eval' to extract data
```

Principle: **every output is a conversation turn**, not a dead end.

## 3. Semantic Exit Codes

Agents branch on exit codes, not by parsing error text. Use meaningful ranges:

| Range | Meaning | Agent action |
|-------|---------|-------------|
| 0 | Success | Continue |
| 1 | Command-level error (site not found, element missing) | Adjust input, retry |
| 2 | Usage error (bad args, unknown command) | Fix invocation |
| 3+ | Specific recoverable errors | Contextual retry/backoff |

Avoid: returning 1 for everything. The more semantic the exit code, the less text parsing the agent needs.

## 4. Output Design

### stdout vs stderr separation
- **stdout**: Data output only (the result). This is what gets piped or captured.
- **stderr**: Hints, warnings, progress, errors. Agents can ignore stderr when piping.

### Human-readable by default, machine-readable on demand

Default to concise, readable text. Provide `--json` when structured data is needed.

**On JSON vs condensed text** — the real question is: when does JSON help an agent?

- **JSON is better when**: output has nested structure, multiple fields per record, or will be processed programmatically (piped to `jq`, consumed by another tool). Example: a list of tabs with id, url, title — JSON avoids fragile column-position parsing.
- **Condensed text is better when**: output is a single value, a short status, or a human-readable blob that the agent will interpret semantically (like a scraping procedure). An LLM doesn't need `{"status": "ok", "message": "navigated"}` — it understands `navigated to https://...` just fine.
- **Rule of thumb**: if the output is **data** (records, lists, structured results), offer JSON. If the output is **narrative** (status, procedures, errors), plain text wins on token efficiency.

For a CLI primarily used by LLM agents: `--json` is a nice-to-have for data commands (tabs, console, capture), but not critical for action commands (navigate, click, fill) where the output is a simple confirmation or error.

### Keep output terse
Agents pay per token. Avoid:
- Decorative banners, ASCII art logos
- Redundant labels ("Result: success" → just "ok" or the data itself)
- Verbose formatting when a single line suffices

## 5. Help Text Design

### Concise default help
When invoked without args, show:
- One-line description
- 2-3 example invocations
- Available subcommands grouped by category
- Pointer to `--help` for details

### Subcommand help
Each subcommand's `--help` should include:
- What it does (one sentence)
- Required vs optional arguments
- One example with realistic values

### Searchability
If the tool has many commands/domains, provide search:
```
tool --search cookie    → lists commands related to cookies
```

This lets agents find capabilities without enumerating everything.

## 6. Input Design

### Prefer explicit flags over positional args for complex commands
`tool click --selector "button.submit" --dbl` is clearer than `tool click "button.submit" --dbl`, especially for agents generating commands.

Exception: when a command has a single obvious argument (`navigate <url>`, `eval <expr>`), positional is fine.

### Sensible defaults
Minimize required flags. An agent shouldn't need to specify `--timeout 30000` on every call if 30s is almost always right.

### stdin support
Support `-` for stdin on data-heavy inputs (JS code, JSON bodies). Agents generate multi-line content more easily via stdin than via shell quoting.

### Subcommand consistency
Same flag name = same meaning everywhere. `--timeout` should always mean the same thing in every subcommand.

## 7. Robustness

### Respond fast
Print something within 100ms. If a network call is needed, indicate it:
```
connecting to browser...
```
Silence makes agents (and humans) wonder if the tool hung.

### Idempotency where possible
Running the same command twice should not cause errors. `navigate` to an already-loaded URL, `stop` on an already-stopped browser — these should succeed silently, not fail.

### Crash-only design
Don't require cleanup. If the daemon dies, the next command should detect it and recover (or report clearly), not leave stale state.

### Timeouts
Always have timeouts. Never hang forever. Make timeouts configurable with sane defaults.

## 8. Composability

### Pipe-friendly
stdout should be pipeable: `tool html | grep "price"` should work.

### Exit codes for scripting
Scripts chain commands with `&&`. Correct exit codes make this reliable:
```bash
tool navigate "$URL" && sleep 2 && tool eval "$EXPR"
```

### No interactive prompts in non-TTY mode
If stdin is not a terminal, never prompt. Fail with a clear message about which flag to pass instead.

## 9. Future-Proofing

- **Additive changes only**: add new subcommands/flags, don't change existing behavior.
- **No arbitrary abbreviations**: if `n` means `navigate` today, you can't add `new` later. Use explicit aliases.
- **Deprecation warnings**: warn in output before removing features. Give users time to adapt.
- **Stable machine output**: human-readable output can change; `--json` output is a contract.

## 10. Agent-Specific Considerations

Things clig.dev doesn't cover but matter for LLM agents:

### Token budget awareness
- Keep outputs short. An agent processing 50 commands in a session accumulates context fast.
- Offer truncation/pagination flags: `--limit`, `--offset`, `--max-depth`.

### Predictable output format
- Agents parse output with pattern matching. Consistent formatting matters more than pretty formatting.
- If a command outputs "navigated to X" today, don't change it to "Successfully navigated to URL: X" tomorrow.

### Hints on stderr, not stdout
- Hints ("prefer snapshot over screenshot") belong on stderr so they don't pollute captured output.
- Agents can learn from hints without them breaking data pipelines.

### Stateless where possible
- Commands that don't require daemon state (like `sites`) are more robust — no "is the browser running?" failure mode.
- When state is required, make state inspection easy (`status` command).
