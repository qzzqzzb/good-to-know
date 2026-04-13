from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_ALLOWED = {
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "6h": 6 * 60 * 60,
    "12h": 12 * 60 * 60,
    "1d": 24 * 60 * 60,
}

DEFAULT_ANCHOR_HOUR = 8
DEFAULT_CATCHUP_THRESHOLD_SECONDS = 2 * 60 * 60
DEFAULT_SLOT_GRACE_SECONDS = 10 * 60


@dataclass(frozen=True)
class ScheduledRunDecision:
    should_run: bool
    reason: str
    previous_slot_epoch: float
    next_slot_epoch: float


def parse_cadence(value: str) -> tuple[str, int]:
    normalized = value.strip().lower()
    if normalized not in _ALLOWED:
        allowed = ", ".join(_ALLOWED)
        raise ValueError(f"Unsupported cadence '{value}'. Allowed values: {allowed}")
    return normalized, _ALLOWED[normalized]


def anchor_start_epoch(now_epoch: float, anchor_hour: int = DEFAULT_ANCHOR_HOUR) -> float:
    current = datetime.fromtimestamp(now_epoch, tz=timezone.utc).astimezone()
    anchor = current.replace(hour=anchor_hour, minute=0, second=0, microsecond=0)
    if anchor.timestamp() > now_epoch:
        anchor -= timedelta(days=1)
    return anchor.timestamp()


def scheduled_slot_window(
    now_epoch: float,
    cadence_seconds: int,
    anchor_hour: int = DEFAULT_ANCHOR_HOUR,
) -> tuple[float, float]:
    base_epoch = anchor_start_epoch(now_epoch, anchor_hour=anchor_hour)
    steps = int((now_epoch - base_epoch) // cadence_seconds)
    previous_slot = base_epoch + (steps * cadence_seconds)
    if previous_slot > now_epoch:
        previous_slot -= cadence_seconds
    next_slot = previous_slot + cadence_seconds
    return previous_slot, next_slot


def next_run_epoch(
    last_started_epoch: float | None,
    cadence_seconds: int,
    *,
    now_epoch: float | None = None,
    anchor_hour: int = DEFAULT_ANCHOR_HOUR,
) -> float | None:
    reference = now_epoch
    if reference is None:
        reference = datetime.now(timezone.utc).astimezone().timestamp()
    _, next_slot = scheduled_slot_window(reference, cadence_seconds, anchor_hour=anchor_hour)
    return next_slot


def start_calendar_intervals(
    cadence_seconds: int,
    anchor_hour: int = DEFAULT_ANCHOR_HOUR,
) -> list[dict[str, int]]:
    intervals: list[dict[str, int]] = []
    current_epoch = datetime(2026, 1, 1, anchor_hour, 0, tzinfo=timezone.utc).timestamp()
    end_epoch = current_epoch + (24 * 60 * 60)
    seen: set[tuple[int, int]] = set()
    while current_epoch < end_epoch:
        current = datetime.fromtimestamp(current_epoch, tz=timezone.utc)
        pair = (current.hour, current.minute)
        if pair not in seen:
            intervals.append({"Hour": current.hour, "Minute": current.minute})
            seen.add(pair)
        current_epoch += cadence_seconds
    intervals.sort(key=lambda item: (item["Hour"], item["Minute"]))
    return intervals


def should_run_scheduled_now(
    now_epoch: float,
    cadence_seconds: int,
    last_success_epoch: float | None,
    *,
    anchor_hour: int = DEFAULT_ANCHOR_HOUR,
    catchup_threshold_seconds: int = DEFAULT_CATCHUP_THRESHOLD_SECONDS,
    slot_grace_seconds: int = DEFAULT_SLOT_GRACE_SECONDS,
) -> ScheduledRunDecision:
    previous_slot, next_slot = scheduled_slot_window(now_epoch, cadence_seconds, anchor_hour=anchor_hour)
    if now_epoch - previous_slot <= slot_grace_seconds:
        return ScheduledRunDecision(True, "scheduled_slot", previous_slot, next_slot)
    if next_slot - now_epoch < catchup_threshold_seconds:
        return ScheduledRunDecision(False, "next_slot_soon", previous_slot, next_slot)
    if last_success_epoch is not None and last_success_epoch >= previous_slot:
        return ScheduledRunDecision(False, "previous_slot_already_satisfied", previous_slot, next_slot)
    return ScheduledRunDecision(True, "catchup_missed_slot", previous_slot, next_slot)
