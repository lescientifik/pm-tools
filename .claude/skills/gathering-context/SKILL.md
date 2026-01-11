---
name: gathering-context
description: Gathers essential project context. MUST be loaded as the first step by any agent before starting work. Provides project overview, folder structure, git state, and task requirements.
---

# Gathering Context

Load this skill before doing anything else.

## Steps

1. Read `project_overview.md` (project root)
2. Read `task.md` (current directory)
3. Run `tree -L 2 -d --noreport`
4. If `.git` exists:
   - `git branch --show-current`
   - `git status --short`
