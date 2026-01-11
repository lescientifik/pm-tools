---
name: running-python
description: Manages Python projects using uv, ruff, and pyright. Use when installing packages, running scripts, tests, linting, formatting, or type checking Python code.
---

# Running Python

Use `uv` for all operations. Never use `pip` or run `python` directly.

## Package Management

```bash
uv add <package>           # Add dependency
uv add --dev <package>     # Add dev dependency
uv sync                    # Install all dependencies
```

## Running Code

```bash
uv run python script.py    # Run script
uv run pytest              # Run tests
uv run ruff check .        # Lint
uv run ruff format .       # Format
uv run pyright             # Type check
```

## Project Setup

```bash
uv init
uv add --dev pytest ruff pyright
```
