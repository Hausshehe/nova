"""Reproducible Dukascopy native-candle acquisition and validation."""

from __future__ import annotations

import csv
import hashlib
import json
import lzma
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import requests

DATAFEED_BASE_URL = "https://datafeed.dukascopy.com/datafeed"
INSTRUMENTS = (
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "US500", "NAS100", "US30", "XAUUSD", "XAGUSD", "WTI",
)
INSTRUMENT_DATAFEED = {
    "US500": "USA500IDXUSD",
    "NAS100": "USATECHIDXUSD",
    "US30": "USA30IDXUSD",
    "WTI": "LIGHTCMDUSD",
}
TIMEFRAMES = ("1D", "4H")
MAX_429_RETRIES = 5
MAX_5XX_RETRIES = 4
MAX_NETWORK_RETRIES = 3
DEFAULT_429_BACKOFF_SECONDS = 2.0
MAX_429_BACKOFF_SECONDS = 120.0
CANDLE_RECORD_SIZE = 24
CANDLE_STRUCT = struct.Struct(">IIIIIf")


@dataclass(frozen=True)
class Candle:
    timestamp_utc: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class DatasetManifest:
    instrument: str
    timeframe: str
    start_utc: str
    end_utc: str
    sha256: str
    bars: int
    source: str
    price_units: str = "native_feed_units"


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _feed_symbol(instrument: str) -> str:
    return INSTRUMENT_DATAFEED.get(instrument, instrument)


def _month_zero_based(month: int) -> str:
    if not 1 <= month <= 12:
        raise ValueError("month_out_of_range")
    return f"{month - 1:02d}"


def _native_url(instrument: str, timeframe: str, year: int, month: int | None = None) -> str:
    symbol = _feed_symbol(instrument)
    if timeframe == "1D":
        return f"{DATAFEED_BASE_URL}/{symbol}/{year}/BID_candles_day_1.bi5"
    if timeframe == "1H":
        if month is None:
            raise ValueError("month_required_for_1H")
        return f"{DATAFEED_BASE_URL}/{symbol}/{year}/{_month_zero_based(month)}/BID_candles_hour_1.bi5"
    raise ValueError(f"unsupported_native_timeframe:{timeframe}")


def _retry_delay(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    try:
        return float(retry_after) if retry_after is not None else DEFAULT_429_BACKOFF_SECONDS * (2**attempt)
    except (TypeError, ValueError):
        return DEFAULT_429_BACKOFF_SECONDS * (2**attempt)


def _request_bytes(session: requests.Session, url: str) -> bytes | None:
    headers = {
        "User-Agent": "Nova-TradingResearch/1.0",
        "Referer": "https://freeserv.dukascopy.com/",
        "Accept": "*/*",
    }
    network_attempts = 0
    rate_attempts = 0
    server_attempts = 0
    while True:
        try:
            response = session.get(url, timeout=45, headers=headers)
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            if network_attempts >= MAX_NETWORK_RETRIES:
                raise
            time.sleep(min(DEFAULT_429_BACKOFF_SECONDS * (2**network_attempts), MAX_429_BACKOFF_SECONDS))
            network_attempts += 1
            continue
        network_attempts = 0
        if response.status_code == 404:
            return None
        if response.status_code == 429:
            if rate_attempts >= MAX_429_RETRIES:
                response.raise_for_status()
            time.sleep(min(_retry_delay(response, rate_attempts), MAX_429_BACKOFF_SECONDS))
            rate_attempts += 1
            continue
        if 500 <= response.status_code < 600:
            if server_attempts >= MAX_5XX_RETRIES:
                response.raise_for_status()
            time.sleep(min(_retry_delay(response, server_attempts), MAX_429_BACKOFF_SECONDS))
            server_attempts += 1
            continue
        response.raise_for_status()
        if not response.content:
            return None
        return response.content


def _decode_candle_file(payload: bytes, base_time: datetime) -> list[Candle]:
    try:
        raw = lzma.decompress(payload)
    except lzma.LZMAError as exc:
        raise ValueError("candle_file_lzma_error") from exc
    if len(raw) % CANDLE_RECORD_SIZE != 0:
        raise ValueError(f"candle_file_bad_record_length:{len(raw)}")
    candles: list[Candle] = []
    for offset in range(0, len(raw), CANDLE_RECORD_SIZE):
        seconds_from_base, open_raw, close_raw, low_raw, high_raw, volume = CANDLE_STRUCT.unpack_from(raw, offset)
        timestamp = base_time + timedelta(seconds=int(seconds_from_base))
        candles.append(
            Candle(
                timestamp_utc=timestamp.isoformat(),
                open=float(open_raw),
                high=float(high_raw),
                low=float(low_raw),
                close=float(close_raw),
                volume=float(volume),
            )
        )
    candles.sort(key=lambda candle: candle.timestamp_utc)
    return candles


def _deduplicate_and_validate(candles: list[Candle]) -> list[Candle]:
    by_timestamp: dict[str, Candle] = {}
    for candle in candles:
        by_timestamp[candle.timestamp_utc] = candle
    ordered = [by_timestamp[key] for key in sorted(by_timestamp)]
    for index, candle in enumerate(ordered):
        if not (candle.low <= candle.open <= candle.high and candle.low <= candle.close <= candle.high):
            raise ValueError(
                "candle_ohlc_invalid:"
                f"timestamp={candle.timestamp_utc}:"
                f"open={candle.open}:high={candle.high}:"
                f"low={candle.low}:close={candle.close}:"
                f"index={index}"
            )
        if index and candle.timestamp_utc <= ordered[index - 1].timestamp_utc:
            raise ValueError("candle_timestamps_not_strictly_increasing")
    return ordered


def _aggregate_4h(hourly: list[Candle]) -> list[Candle]:
    buckets: dict[datetime, list[Candle]] = {}
    for candle in hourly:
        ts = _parse_time(candle.timestamp_utc)
        bucket = ts.replace(hour=(ts.hour // 4) * 4, minute=0, second=0, microsecond=0)
        buckets.setdefault(bucket, []).append(candle)
    result: list[Candle] = []
    for bucket in sorted(buckets):
        rows = sorted(buckets[bucket], key=lambda row: row.timestamp_utc)
        expected = [bucket + timedelta(hours=i) for i in range(4)]
        actual = [_parse_time(row.timestamp_utc) for row in rows]
        if actual != expected:
            continue
        result.append(
            Candle(
                timestamp_utc=bucket.isoformat(),
                open=rows[0].open,
                high=max(row.high for row in rows),
                low=min(row.low for row in rows),
                close=rows[-1].close,
                volume=sum(row.volume for row in rows),
            )
        )
    return _deduplicate_and_validate(result)


class DukascopyClient:
    """Native candle feed client; no instrument-list API dependency."""

    def __init__(self, *, session: requests.Session | None = None):
        self.session = session or requests.Session()

    def historical_prices(
        self,
        *,
        instrument: str,
        timeframe: str,
        start_utc: str,
        end_utc: str,
        progress: Callable[[str], None] | None = None,
    ) -> list[Candle]:
        start = _parse_time(start_utc)
        end = _parse_time(end_utc)
        if end <= start:
            raise ValueError("end_must_be_after_start")
        if instrument not in INSTRUMENTS:
            raise ValueError(f"unsupported_instrument:{instrument}")
        if timeframe == "1D":
            candles: list[Candle] = []
            for year in range(start.year, end.year + 1):
                url = _native_url(instrument, "1D", year)
                if progress:
                    progress(f"request {instrument} 1D {year}")
                payload = _request_bytes(self.session, url)
                if not payload:
                    if progress:
                        progress(f"empty {instrument} 1D {year}")
                    continue
                decoded = _decode_candle_file(payload, datetime(year, 1, 1, tzinfo=timezone.utc))
                candles.extend(decoded)
                if progress:
                    progress(f"received {instrument} 1D {year}: bars={len(decoded)}")
            result = [c for c in _deduplicate_and_validate(candles) if start <= _parse_time(c.timestamp_utc) < end]
            if progress:
                progress(f"validated {instrument} 1D: bars={len(result)}")
            return result
        if timeframe == "4H":
            hourly: list[Candle] = []
            month = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
            last_month = datetime(end.year, end.month, 1, tzinfo=timezone.utc)
            while month <= last_month:
                url = _native_url(instrument, "1H", month.year, month.month)
                if progress:
                    progress(f"request {instrument} 1H {month.year}-{month.month:02d}")
                payload = _request_bytes(self.session, url)
                if payload:
                    decoded = _decode_candle_file(payload, month)
                    hourly.extend(decoded)
                    if progress:
                        progress(
                            f"received {instrument} 1H {month.year}-{month.month:02d}: bars={len(decoded)}"
                        )
                elif progress:
                    progress(f"empty {instrument} 1H {month.year}-{month.month:02d}")
                if month.month == 12:
                    month = datetime(month.year + 1, 1, 1, tzinfo=timezone.utc)
                else:
                    month = datetime(month.year, month.month + 1, 1, tzinfo=timezone.utc)
            four_hour = _aggregate_4h(_deduplicate_and_validate(hourly))
            result = [c for c in four_hour if start <= _parse_time(c.timestamp_utc) < end]
            if progress:
                progress(f"validated {instrument} 4H: bars={len(result)}")
            return result
        raise ValueError(f"unsupported_timeframe:{timeframe}")


def write_csv(candles: list[Candle], path: str | Path) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for candle in candles:
            writer.writerow([
                candle.timestamp_utc,
                f"{candle.open:.12g}",
                f"{candle.high:.12g}",
                f"{candle.low:.12g}",
                f"{candle.close:.12g}",
                f"{candle.volume:.12g}",
            ])
    return hashlib.sha256(target.read_bytes()).hexdigest()


def save_manifest(manifests: list[DatasetManifest], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [manifest.__dict__ for manifest in manifests]
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def download_universe(
    *,
    output_dir: str | Path,
    start_utc: str,
    end_utc: str,
    client: DukascopyClient,
    progress: Callable[[str], None] | None = None,
) -> list[DatasetManifest]:
    start = _parse_time(start_utc)
    end = _parse_time(end_utc)
    if end <= start:
        raise ValueError("end_must_be_after_start")
    manifests: list[DatasetManifest] = []
    out = Path(output_dir)
    total = len(INSTRUMENTS) * len(TIMEFRAMES)
    completed = 0
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            if progress:
                progress(f"START dataset {completed + 1}/{total}: {instrument} {timeframe}")
            candles = client.historical_prices(
                instrument=instrument,
                timeframe=timeframe,
                start_utc=start_utc,
                end_utc=end_utc,
                progress=progress,
            )
            if len(candles) < 100:
                raise ValueError(f"insufficient_bars:{instrument}:{timeframe}:{len(candles)}")
            filename = f"{instrument}_{timeframe}.csv"
            digest = write_csv(candles, out / filename)
            manifests.append(DatasetManifest(
                instrument=instrument,
                timeframe=timeframe,
                start_utc=candles[0].timestamp_utc,
                end_utc=candles[-1].timestamp_utc,
                sha256=digest,
                bars=len(candles),
                source=DATAFEED_BASE_URL,
            ))
            completed += 1
            if progress:
                progress(
                    f"DONE dataset {completed}/{total}: {instrument} {timeframe} bars={len(candles)} sha256={digest}"
                )
    save_manifest(manifests, out / "manifest.json")
    if progress:
        progress(f"UNIVERSE COMPLETE: datasets={len(manifests)} manifest={out / 'manifest.json'}")
    return manifests
