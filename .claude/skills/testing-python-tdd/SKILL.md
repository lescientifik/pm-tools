---
name: testing-python-tdd
description: Implements Python TDD with pytest. Use when writing unit tests, debugging failing tests, creating e2e tests (Textual TUI, FastAPI, etc.), or implementing features test-first with given-when-then structure.
---

# Testing with TDD

Follows strict Red-Green-Refactor methodology.

## First Step

Load `running-python` skill if not already loaded.

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

## Test Quality Criteria

**Good tests are**: Deterministic, Isolated, Fast, Readable, Focused

**Bad tests are**: Flaky, Tightly coupled, Over-mocked, Unclear, Brittle

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
4. **Only modify tests if genuinely bad** (incorrect behavior, flaky, testing implementation details)

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

## Workflow Summary

1. Understand requirement completely
2. Write failing test (Red)
3. Implement minimum code to pass (Green)
4. Refactor while keeping tests green
5. Add edge case tests
6. Ensure types, docstrings, meaningful comments

## Inter-Agent Communication

When in multi-agent workflow, use handoff scripts:

```bash
# Read feedback from Reviewer
.claude/skills/agent-handoff/scripts/read_last.sh REVIEWER

# Submit work for review
cat << 'EOF' | .claude/skills/agent-handoff/scripts/write_message.sh CODER
## Changes Made
[Description]

## Files Modified
- path/to/file.py

## Tests Added
- test_feature.py
EOF
```

Never read `.claude/handoff.md` directly.
