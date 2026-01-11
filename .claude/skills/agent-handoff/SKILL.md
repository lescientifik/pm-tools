---
name: agent-handoff
description: Enables communication between subagents without polluting orchestrator context. Use when implementing multi-agent workflows where agents need to exchange information.
---

# Agent Handoff

Communication system for multi-agent workflows. Agents exchange messages via a shared handoff file using role-based markers, without the orchestrator needing to read full contents.

## Architecture

```
Orchestrator
    │
    ├── launches Agent A (e.g., Coder)
    │       └── reads from other agents: read_last.sh AGENT_B
    │       └── writes its output: write_message.sh AGENT_A
    │
    └── launches Agent B (e.g., Reviewer)
            └── reads from other agents: read_last.sh AGENT_A
            └── writes its output: write_message.sh AGENT_B
            └── returns status to orchestrator
```

## Scripts

Located in `.claude/skills/agent-handoff/scripts/`:

| Script | Purpose |
|--------|---------|
| `write_message.sh ROLE` | Append message with role markers (stdin) |
| `read_last.sh ROLE` | Read last message from a role |

## Usage

### Writing a Message

```bash
cat << 'EOF' | .claude/skills/agent-handoff/scripts/write_message.sh MY_ROLE
Your message content here.
Can be multiline.
EOF
```

### Reading the Last Message from Another Agent

```bash
.claude/skills/agent-handoff/scripts/read_last.sh OTHER_ROLE
```

## Handoff File Format

File: `.claude/handoff.md`

```markdown
<<<CODER>>>
function hello() {
  return "world"
}
<<<END>>>

<<<REVIEWER>>>
- Add TypeScript types
- Missing error handling

STATUS: needs_revision
<<<END>>>

<<<CODER>>>
function hello(): string {
  return "world"
}
<<<END>>>

<<<REVIEWER>>>
LGTM

STATUS: approved
<<<END>>>
```

## Role Naming Convention

Use uppercase identifiers that match your agent's role:
- `CODER` - for coding agents
- `REVIEWER` - for review agents
- `PLANNER` - for planning agents
- `TESTER` - for testing agents
- Custom roles as needed

## Example: Coder/Reviewer Loop

```
Orchestrator workflow:
1. Launch Coder with task description
2. Launch Reviewer
3. If Reviewer returns "needs_revision" → go to step 1
4. If Reviewer returns "approved" → done
```

## Key Benefits

1. **Context isolation**: Orchestrator never reads full exchanges between agents
2. **No file deletion**: Append-only, safe operations
3. **Fresh agent context**: Each subagent starts clean, reads only what it needs
4. **Auditable**: Full history preserved in handoff file
5. **Flexible**: Any number of agents with any role names
