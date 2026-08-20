"""Dependency-free market data primitives for the research gate.

The first research harness deliberately avoids pandas/MT5 dependencies so that
we can prove data validation and chronological splitting independently from
the trading terminal environment.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def timestamp_utc(self) -> str:
        """Canonical ISO-8601 UTC timestamp used by the recovery validator."""
        return self.timestamp.astimezone(timezone.utc).isoformat()

    def validate(self) -> None:
        values = (self.open, self.high, self.low, self.close, self.volume)
        if any(value != value for value in values):
            raise ValueError("bar contains NaN")
        if self.high < max(self.open, self.close):
            raise ValueError("high must be >= open and close")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be <= open and close")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")


@dataclass(frozen=True)
class DatasetSplit:
    train: Sequence[Bar]
    validation: Sequence[Bar]
    test: Sequence[Bar]


@dataclass(frozen=True)
class OHLCVValidationReport:
    """Deterministic validation result for already-normalized OHLCV rows."""

    ok: bool
    reasons: Sequence[str] = ()


def _parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError("timestamp is required")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_ohlcv_rows(rows: Sequence[dict[str, Any]]) -> OHLCVValidationReport:
    """Validate normalized OHLCV dictionaries without requiring pandas or MT5."""
    reasons: list[str] = []
    previous_timestamp: datetime | None = None

    if not rows:
        return OHLCVValidationReport(False, ("dataset is empty",))

    for index, row in enumerate(rows, start=1):
        missing = [column for column in REQUIRED_COLUMNS if column not in row]
        if missing:
            reasons.append(f"row_{index}:missing_columns:{','.join(missing)}")
            continue

        try:
            timestamp = _parse_timestamp(str(row["timestamp"]))
            bar = Bar(
                timestamp=timestamp,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            bar.validate()
        except (TypeError, ValueError) as exc:
            reasons.append(f"row_{index}:invalid:{exc}")
            continue

        if previous_timestamp is not None and timestamp <= previous_timestamp:
            reasons.append(f"row_{index}:timestamps_not_strictly_increasing")
        previous_timestamp = timestamp

    return OHLCVValidationReport(not reasons, tuple(reasons))


def load_csv(path: str | Path) -> list[Bar]:
    """Load and validate chronological OHLCV data from a CSV file."""
    rows: list[Bar] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header")
        missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise ValueError("CSV missing required columns: " + ", ".join(missing))

        for line_number, row in enumerate(reader, start=2):
            try:
                bar = Bar(
                    timestamp=_parse_timestamp(row["timestamp"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
                bar.validate()
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid OHLCV row {line_number}: {exc}") from exc
            rows.append(bar)

    if not rows:
        raise ValueError("dataset is empty")
    timestamps = [bar.timestamp for bar in rows]
    if timestamps != sorted(timestamps):
        raise ValueError("dataset timestamps must be chronological")
    return rows


def chronological_split(
    bars: Sequence[Bar],
    *,
    train_ratio: float = 0.60,
    validation_ratio: float = 0.20,
) -> DatasetSplit:
    """Split bars chronologically; never shuffle financial time series."""
    if not bars:
        raise ValueError("cannot split an empty dataset")
    if not 0.0 < train_ratio < 1.0:
        raise ValueError("train_ratio must be between 0 and 1")
    if not 0.0 < validation_ratio < 1.0:
        raise ValueError("validation_ratio must be between 0 and 1")
    if train_ratio + validation_ratio >= 1.0:
        raise ValueError("train_ratio + validation_ratio must be < 1")

    n = len(bars)
    train_end = max(1, int(n * train_ratio))
    validation_end = max(train_end + 1, int(n * (train_ratio + validation_ratio)))
    if validation_end >= n:
        validation_end = n - 1
    if train_end >= validation_end:
        raise ValueError("dataset is too small for the requested split")

    return DatasetSplit(
        train=tuple(bars[:train_end]),
        validation=tuple(bars[train_end:validation_end]),
        test=tuple(bars[validation_end:]),
    )
