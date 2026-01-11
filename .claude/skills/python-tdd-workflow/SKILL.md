---
name: python-tdd-workflow
description: Complete Python TDD workflow using uv, pytest, ruff, and pyright. Use when developing Python features test-first, running tests, linting, formatting, or type checking with TDD methodology.
---

# Python TDD Workflow

Combines environment management (uv) with strict Red-Green-Refactor methodology.

## Running Commands

Use `uv` for all operations. Never use `pip` or run `python` directly.

```bash
uv run pytest              # Run tests
uv run pytest -x           # Stop on first failure
uv run pytest -v           # Verbose output
uv run ruff check .        # Lint
uv run ruff format .       # Format
uv run pyright             # Type check
```

## Package Management

```bash
uv add <package>           # Add dependency
uv add --dev <package>     # Add dev dependency
uv sync                    # Install all dependencies
```

## Project Setup

```bash
uv init
uv add --dev pytest ruff pyright
```

## Test Structure: Given-When-Then

```python
def test_descriptive_behavior_name():
    # Given: Set up initial state
    user = User(name="Alice", role="admin")
    resource = ProtectedResource(owner=user)

    # When: Perform the action
    result = resource.grant_access(requesting_user=user)

    # Then: Assert outcomes
    assert result.is_granted is True
    assert result.access_level == AccessLevel.FULL
```

## TDD Cycle

1. **Red**: Write failing test first
2. **Green**: Implement minimum code to pass
3. **Refactor**: Clean up while keeping tests green

## Test Quality

**Good tests**: Deterministic, Isolated, Fast, Readable, Focused

**Bad tests**: Flaky, Tightly coupled, Over-mocked, Unclear, Brittle

## Framework Selection

| Context | Framework |
|---------|-----------|
| Unit tests | pytest with fixtures |
| Textual TUI | `textual.testing` with `pilot` |
| FastAPI/Starlette | `httpx.AsyncClient` / `TestClient` |
| Django | pytest-django |
| CLI apps | `click.testing.CliRunner` |

## When Tests Fail

1. **Read the error carefully** - full stack trace
2. **Identify failure type**: Assertion, Exception, Timeout, Setup
3. **Determine root cause BEFORE changing anything**:
   - Test wrong? → Fix test
   - Code wrong? → Fix code
4. **Only modify tests if genuinely bad**

## Debugging Protocol

1. **Never guess** - no random changes
2. **Gather context first** - read errors completely
3. **Add strategic prints if needed**:
   ```python
   print(f"DEBUG: {variable_name=!r}, {type(variable_name)=}")
   ```
4. **Form hypothesis** before changing
5. **One change at a time**

## Code Standards

### Type Annotations - Required

```python
def process_items(
    items: List[str],
    transformer: Callable[[str], T],
    default: Optional[T] = None
) -> Dict[str, T]:
    ...
```

### Docstrings - Google Format

```python
def calculate_discount(
    original_price: float,
    discount_percentage: float,
    max_discount: Optional[float] = None
) -> float:
    """Calculate discounted price.

    Args:
        original_price: Price before discount.
        discount_percentage: Discount as percentage (0-100).
        max_discount: Optional maximum discount cap.

    Returns:
        Final price after discount.

    Raises:
        ValueError: If discount_percentage invalid.
    """
```

## Complete Workflow

1. Understand requirement completely
2. Write failing test (Red)
3. Run `uv run pytest -x` - verify it fails
4. Implement minimum code to pass (Green)
5. Run `uv run pytest` - verify it passes
6. Refactor while keeping tests green
7. Run `uv run ruff check . && uv run ruff format .`
8. Run `uv run pyright` - fix type errors
9. Add edge case tests, repeat cycle
