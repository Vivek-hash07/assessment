from datetime import datetime, timezone


def iso(dt: datetime | None) -> str | None:
    """Format a datetime as UTC ISO-8601 (e.g. 2024-01-15T10:30:00Z)."""
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
