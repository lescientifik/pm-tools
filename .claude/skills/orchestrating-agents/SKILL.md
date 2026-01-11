---
name: orchestrating-agents
description: Orchestrates multi-agent workflows with Coder/Reviewer loops. Use when implementing features that require code review cycles, TDD workflows, or any task benefiting from iterative agent collaboration.
---

# Orchestrating Agents

Coordinate Coder and Reviewer agents in an iterative loop until approval. Agents communicate via `handoff.md` to minimize token usage.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              TASK 1                                     │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                                                                   │  │
│  │    ┌──────────┐                             ┌──────────┐          │  │
│  │    │          │  ── 1. write_message ─────▶ │          │          │  │
│  │    │  CODER   │         (CODER)             │ REVIEWER │          │  │
│  │    │          │  ◀───── 2. read_last ────── │          │          │  │
│  │    └──────────┘         (CODER)             └────┬─────┘          │  │
│  │         ▲                                        │                │  │
│  │         │         ┌────────────────┐             │                │  │
│  │         │         │ handoff.md     │             │                │  │
│  │  4. read_last     │ <<<CODER>>>    │      3. write_message        │  │
│  │    (REVIEWER)     │ ...            │         (REVIEWER)           │  │
│  │         │         │ <<<REVIEWER>>> │             │                │  │
│  │         │         └────────────────┘             │                │  │
│  │         └────────────────────────────────────────┘                │  │
│  │                    (loop jusqu'à STATUS: approved)                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                 │ approved                              │
└─────────────────────────────────┼───────────────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              TASK 2                                     │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │    ┌──────────┐                             ┌──────────┐          │  │
│  │    │  CODER   │  ◀─────── handoff ────────▶ │ REVIEWER │          │  │
│  │    │  (new)   │                             │  (new)   │          │  │
│  │    └──────────┘                             └────┬─────┘          │  │
│  │         ▲                                        │                │  │
│  │         └────────────────────────────────────────┘                │  │
│  │                    (loop jusqu'à STATUS: approved)                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                 │ approved                              │
└─────────────────────────────────┼───────────────────────────────────────┘
                                  ▼
                                . . .
```

**Principe clé** : Au sein d'une tâche, les agents collaborent via `handoff.md`. Entre les tâches, on lance de **nouveaux agents** avec un contexte frais.

## Token Efficiency

| Sans handoff | Avec handoff |
|--------------|--------------|
| 4x tokens/message | 2x tokens/message |

L'orchestrateur ne voit que "Done" et "STATUS: x". Les détails restent dans `handoff.md`.

## Workflow

### Step 1: Initialize Handoff

```bash
mkdir -p .claude && echo "" > .claude/handoff.md
```

### Step 2: Launch Coder

Load `testing-python-tdd` skill (or similar coding skill):

```
Tu es l'agent CODER. Ta tâche : [DESCRIPTION]

Communication inter-agent :
1. Lis le feedback du reviewer (s'il y en a) :
   .claude/skills/agent-handoff/scripts/read_last.sh REVIEWER

2. Fais ton travail (code + tests)

3. Soumets ton récapitulatif :
   cat << 'EOF' | .claude/skills/agent-handoff/scripts/write_message.sh CODER
   ## Résumé
   [ce que tu as fait]

   ## Fichiers modifiés
   - [liste]
   EOF

4. Retourne juste "Done" à l'orchestrateur.
```

**Expected response**: `Done`

### Step 3: Launch Reviewer

Load `reviewing-code` skill:

```
Tu es l'agent REVIEWER. Examine le travail du Coder.

Communication inter-agent :
1. Lis le récapitulatif du coder :
   .claude/skills/agent-handoff/scripts/read_last.sh CODER

2. Examine les fichiers mentionnés

3. Soumets ton feedback :
   cat << 'EOF' | .claude/skills/agent-handoff/scripts/write_message.sh REVIEWER
   ## Review
   [ton assessment]

   ## Issues
   - [liste ou "Aucune"]

   STATUS: approved|needs_revision
   EOF

4. Retourne juste "STATUS: approved" ou "STATUS: needs_revision".
```

**Expected response**: `STATUS: approved` or `STATUS: needs_revision`

### Step 4: Loop Decision

```
if response == "STATUS: approved":
    → Task complete, move to next task
else:
    → Go back to Step 2 (Coder reads feedback via handoff)
```

## Complete Example

```
tasks = [task1, task2, task3, ...]

for task in tasks:
    ┌─────────────────────────────────────────────────────┐
    │ NOUVELLE PAIRE D'AGENTS (contexte frais)            │
    │                                                     │
    │   status = "needs_revision"                         │
    │                                                     │
    │   while status != "approved":                       │
    │       │                                             │
    │       ├── Coder travaille                           │
    │       │   └── lit feedback: read_last.sh REVIEWER   │
    │       │   └── code dans les fichiers                │
    │       │   └── écrit récap: write_message.sh CODER   │
    │       │   └── retourne "Done"                       │
    │       │                                             │
    │       └── Reviewer examine                          │
    │           └── lit récap: read_last.sh CODER         │
    │           └── examine les fichiers                  │
    │           └── écrit review: write_message.sh REV.   │
    │           └── retourne "STATUS: approved|needs_rev" │
    │                                                     │
    │       status = parse(reviewer_response)             │
    │                                                     │
    │   # Loop continue jusqu'à approved                  │
    └─────────────────────────────────────────────────────┘

    # Tâche terminée → passer à la suivante avec nouveaux agents
```

**Points clés** :
- Au sein d'une tâche : les agents itèrent via `handoff.md` (continuité)
- Entre les tâches : nouveaux agents avec contexte frais (isolation)

## Key Rules

1. **Never read handoff.md yourself** — let agents handle their communication
2. **Keep prompts consistent** — always include the handoff script instructions
3. **Trust minimal responses** — "Done" and "STATUS: x" are sufficient
4. **Fresh agents per iteration** — each subagent launch has clean context
5. **Handoff persists** — agents read previous messages via `read_last.sh`

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Agent doesn't use handoff | Ensure scripts path is correct: `.claude/skills/agent-handoff/scripts/` |
| Agent returns verbose response | Reinforce "Retourne juste X" in prompt |
| Loop never exits | Check Reviewer prompt includes STATUS instruction |
| Agent can't read feedback | Verify previous agent wrote to handoff with correct ROLE |

## Skills Reference

| Skill | Role | Returns |
|-------|------|---------|
| `testing-python-tdd` | Coder (TDD, pytest) | `Done` |
| `reviewing-code` | Reviewer (quality, tests) | `STATUS: approved\|needs_revision` |

## Files

| Path | Purpose |
|------|---------|
| `.claude/handoff.md` | Agent communication (append-only) |
| `.claude/skills/agent-handoff/scripts/write_message.sh` | Write to handoff |
| `.claude/skills/agent-handoff/scripts/read_last.sh` | Read from handoff |
