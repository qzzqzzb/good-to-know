from __future__ import annotations

_ALLOWED = {
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h": 60 * 60,
    "6h": 6 * 60 * 60,
    "12h": 12 * 60 * 60,
    "1d": 24 * 60 * 60,
}


def parse_cadence(value: str) -> tuple[str, int]:
    normalized = value.strip().lower()
    if normalized not in _ALLOWED:
        allowed = ", ".join(_ALLOWED)
        raise ValueError(f"Unsupported cadence '{value}'. Allowed values: {allowed}")
    return normalized, _ALLOWED[normalized]


def next_run_epoch(last_started_epoch: float | None, cadence_seconds: int) -> float | None:
    if last_started_epoch is None:
        return None
    return last_started_epoch + cadence_seconds
