from datetime import UTC, datetime


def utcnow() -> datetime:
    """DB 컬럼(naive UTC)과 맞춘 현재 시각."""
    return datetime.now(UTC).replace(tzinfo=None)
