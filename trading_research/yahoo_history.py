"""Frozen independent Yahoo Finance source for Experiment 2 WTI 1D."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from .dukascopy_history import Candle, _deduplicate_and_validate

YAHOO_WTI_SYMBOL = "CL=F"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/CL=F"
YAHOO_WTI_SOURCE = "yahoo_finance:CL=F:chart_api:raw_ohlcv"


def _utc_day(timestamp: int) -> datetime:
    value = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def fetch_wti_1d(
    *,
    start_utc: str,
    end_utc: str,
    session: requests.Session | None = None,
) -> list[Candle]:
    """Fetch raw Yahoo CL=F daily OHLCV and normalize timestamps to UTC days."""
    start = datetime.fromisoformat(start_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    end = datetime.fromisoformat(end_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    if end <= start:
        raise ValueError("end_must_be_after_start")

    client = session or requests.Session()
    response = client.get(
        YAHOO_CHART_URL,
        params={
            "period1": int(start.timestamp()),
            "period2": int(end.timestamp()),
            "interval": "1d",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        },
        headers={"User-Agent": "Nova-TradingResearch/1.0"},
        timeout=(20, 90),
    )
    response.raise_for_status()
    result = response.json().get("chart", {}).get("result")
    if not result:
        raise ValueError("yahoo_wti_missing_chart_result")
    payload: dict[str, Any] = result[0]
    timestamps = payload.get("timestamp") or []
    quote = (payload.get("indicators", {}).get("quote") or [{}])[0]
    required = ("open", "high", "low", "close", "volume")
    if any(key not in quote for key in required):
        raise ValueError("yahoo_wti_missing_ohlcv_fields")

    candles: list[Candle] = []
    for index, timestamp in enumerate(timestamps):
        values = {key: quote[key][index] for key in required}
        if any(values[key] is None for key in ("open", "high", "low", "close")):
            continue
        day = _utc_day(int(timestamp))
        if not (start.date() <= day.date() < end.date()):
            continue
        candles.append(
            Candle(
                timestamp_utc=day.isoformat(),
                open=float(values["open"]),
                high=float(values["high"]),
                low=float(values["low"]),
                close=float(values["close"]),
                volume=float(values["volume"] or 0.0),
            )
        )

    return _deduplicate_and_validate(candles)
