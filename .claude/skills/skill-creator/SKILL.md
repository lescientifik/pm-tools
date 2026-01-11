---
name: skill-creator
description: Creates properly formatted Claude Code skills following Anthropic best practices. Use when creating a new skill, defining slash commands, or setting up project-specific instructions.
---

# Skill Creator

## Structure

```
.claude/skills/<skill-name>/
├── SKILL.md          # Required - main instructions (<500 lines)
├── REFERENCE.md      # Optional - detailed docs (loaded on-demand)
└── scripts/          # Optional - utility scripts (executed, not read)
```

## SKILL.md Format

```yaml
---
name: processing-pdfs
description: Extracts text from PDFs and fills forms. Use when working with PDF files or document extraction.
---

# Processing PDFs

Instructions here...
```

## Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Lowercase, numbers, hyphens only. Max 64 chars. No "anthropic" or "claude". |
| `description` | Yes | Max 1024 chars. Third person. What it does + when to use it. |
| `allowed-tools` | No | Tools without permission: `Read, Grep, Glob, Bash, Edit, Write` |
| `context` | No | Set to `fork` for isolated sub-agent |
| `agent` | No | Agent type if forked: `Explore`, `Plan`, `general-purpose` |

## Naming Convention

Prefer **gerund form** (verb + -ing):
- `processing-pdfs`
- `analyzing-spreadsheets`
- `testing-code`

Acceptable alternatives: `pdf-processing`, `process-pdfs`

Avoid: `helper`, `utils`, `tools`, `documents`

## Description Best Practices

**Always third person** (injected into system prompt):
- Good: "Processes Excel files and generates reports"
- Bad: "I can help you process Excel files"

**Be specific with triggers**:
```yaml
# Bad
description: Helps with documents

# Good
description: Extracts text and tables from PDF files, fills forms, merges documents. Use when working with PDF files or when user mentions PDFs, forms, or document extraction.
```

## Core Principles

### Be Concise

Claude is smart. Only add context Claude doesn't have.

```markdown
# Bad (~150 tokens)
PDF files are a common format containing text and images.
To extract text, you need a library. We recommend pdfplumber...

# Good (~50 tokens)
Use pdfplumber for text extraction:
import pdfplumber
with pdfplumber.open("file.pdf") as pdf:
    text = pdf.pages[0].extract_text()
```

### Set Appropriate Freedom

**High freedom** (multiple valid approaches):
```markdown
## Code review
1. Analyze structure
2. Check for bugs
3. Suggest improvements
```

**Low freedom** (fragile operations):
```markdown
## Database migration
Run exactly: python scripts/migrate.py --verify --backup
Do not modify flags.
```

## Progressive Disclosure

Keep SKILL.md under 500 lines. Reference separate files for details:

```markdown
## Quick start
[Essential content here]

## Advanced
- Form filling: See [FORMS.md](FORMS.md)
- API reference: See [REFERENCE.md](REFERENCE.md)
```

**One level deep only** - don't nest references (SKILL.md → file.md → other.md).

For files >100 lines, add a table of contents at the top.

## Workflows & Feedback Loops

For complex tasks, provide a checklist:

```markdown
## Form filling workflow

Task Progress:
- [ ] Step 1: Analyze form (run analyze_form.py)
- [ ] Step 2: Create mapping (edit fields.json)
- [ ] Step 3: Validate (run validate.py)
- [ ] Step 4: Fill form (run fill_form.py)
```

Implement validation loops: Run validator → fix errors → repeat.

## Common Patterns

### Template Pattern
```markdown
## Report structure
ALWAYS use this template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

### Examples Pattern
```markdown
## Commit messages

Input: Added JWT auth
Output: feat(auth): implement JWT-based authentication
```

### Conditional Workflow
```markdown
**Creating new?** → See "Creation workflow"
**Editing existing?** → See "Editing workflow"
```

## Anti-Patterns

- **Windows paths**: Use `scripts/helper.py`, not `scripts\helper.py`
- **Too many options**: Provide one default, mention alternatives only when needed
- **Time-sensitive info**: Use "Old patterns" section for deprecated content
- **Inconsistent terms**: Pick one term and use it throughout

## Scripts Best Practices

Scripts should **solve, not punt**:

```python
# Good: Handle errors
except FileNotFoundError:
    print(f"Creating {path}")
    with open(path, 'w') as f:
        f.write('')

# Bad: Let it fail
return open(path).read()
```

Document constants:
```python
# 30s timeout accounts for slow connections
REQUEST_TIMEOUT = 30
```

## Locations

| Type | Path |
|------|------|
| Personal | `~/.claude/skills/<name>/SKILL.md` |
| Project | `.claude/skills/<name>/SKILL.md` |

## Checklist

- [ ] Description: third person, specific, includes triggers
- [ ] Name: gerund form, lowercase, hyphens
- [ ] SKILL.md < 500 lines
- [ ] References one level deep
- [ ] No time-sensitive content
- [ ] Consistent terminology
- [ ] Forward slashes in paths
