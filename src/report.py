"""Formatting helpers for a simple test report."""


def format_report(title: str, passed: int, total: int) -> str:
    """Format a deterministic one-line result summary."""
    if not title.strip():
        raise ValueError("title must not be empty")
    if passed < 0 or total < 0 or passed > total:
        raise ValueError("expected 0 <= passed <= total")
    return f"{title}: {passed}/{total} checks passed"
