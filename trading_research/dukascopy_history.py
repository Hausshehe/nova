"""Reproducible Dukascopy historical-candle acquisition and validation."""

from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

BASE_URL = "https://freeserv.dukascopy.com/2.0/index.php"
INSTRUMENTS = (
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
    "US500", "NAS100", "US30", "XAUUSD", "XAGUSD", "WTI",
)
TIMEFRAMES = ("1D", "4H")
TIMEFRAME_API = {"1D": "1day", "4H": "4hour"}
MAX_COUNT = 5000
MAX_429_RETRIES = 5
DEFAULT_429_BACKOFF_SECONDS = 2.0
MAX_429_BACKOFF_SECONDS = 120.0


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


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _unix_ms(value: str) -> int:
    return int(_parse_time(value).timestamp() * 1000)


def _item_timestamp(item: dict[str, Any]) -> datetime:
    ts = item.get("timestamp", item.get("time"))
    if ts is None:
        raise ValueError("candle_timestamp_missing")
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(float(ts) / (1000 if ts > 10**12 else 1), tz=timezone.utc)
    if isinstance(ts, str):
        return _parse_time(ts)
    raise ValueError("candle_timestamp_invalid")


def _instrument_name(item: dict[str, Any]) -> str:
    for key in ("name", "symbol", "nameLong"):
        value = item.get(key)
        if isinstance(value, str):
            return value.replace("/", "").replace("_", "").upper()
    return ""


class DukascopyClient:
    def __init__(self, *, session: requests.Session | None = None, key: str | None = None):
        self.session = session or requests.Session()
        self.key = key

    def _get(self, params: dict[str, Any]) -> Any:
        query = dict(params)
        if self.key:
            query["key"] = self.key
        headers = {
            "User-Agent": "Nova-TradingResearch/1.0",
            "Referer": "https://freeserv.dukascopy.com/",
            "Accept": "application/json, text/plain, */*",
        }
        for attempt in range(MAX_429_RETRIES + 1):
            response = self.session.get(BASE_URL, params=query, timeout=30, headers=headers)
            if response.status_code == 429:
                if attempt >= MAX_429_RETRIES:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after is not None else DEFAULT_429_BACKOFF_SECONDS * (2**attempt)
                except ValueError:
                    delay = DEFAULT_429_BACKOFF_SECONDS * (2**attempt)
                time.sleep(min(delay, MAX_429_BACKOFF_SECONDS))
                continue
            response.raise_for_status()
            try:
                return response.json()
            except requests.exceptions.JSONDecodeError as exc:
                preview = response.text[:200].replace("\n", " ")
                raise ValueError(
                    f"dukascopy_invalid_json:status={response.status_code}:content_type={response.headers.get('Content-Type')}:body={preview!r}"
                ) from exc
        raise RuntimeError("unreachable")

    def resolve_instruments(self) -> dict[str, int]:
        payload = self._get({"path": "api/instrumentList", "fields": "id,name,pipValue,nameLong"})
        if not isinstance(payload, list):
            raise ValueError("instrument_list_not_array")
        result: dict[str, int] = {}
        for item in payload:
            if not isinstance(item, dict) or "id" not in item:
                continue
            name = _instrument_name(item)
            if name:
                result[name] = int(item["id"])
        missing = sorted(set(INSTRUMENTS) - set(result))
        if missing:
            raise ValueError(f"missing_instruments:{','.join(missing)}")
        return {name: result[name] for name in INSTRUMENTS}

    def historical_prices(
        self,
        *,
        instrument_id: int,
        timeframe: str,
        start_utc: str,
        end_utc: str,
        offer_side: str = "B",
    ) -> list[dict[str, Any]]:
        if timeframe not in TIMEFRAME_API:
            raise ValueError(f"unsupported_timeframe:{timeframe}")
        if offer_side not in {"B", "A"}:
            raise ValueError("offer_side_must_be_B_or_A")
        start_ms = _unix_ms(start_utc)
        end_ms = _unix_ms(end_utc)
        all_rows: list[dict[str, Any]] = []
        while start_ms <= end_ms:
            payload = self._get({
                "path": "api/historicalPrices",
                "instrument": instrument_id,
                "timeFrame": TIMEFRAME_API[timeframe],
                "count": MAX_COUNT,
                "start": start_ms,
                "end": end_ms,
                "dayStartTime": "UTC",
                "offerSide": offer_side,
            })
            if not isinstance(payload, list):
                raise ValueError("historical_prices_not_array")
            if not payload:
                break
            all_rows.extend(payload)
            if len(payload) < MAX_COUNT:
                break
            last_time = max(_item_timestamp(item) for item in payload)
            next_ms = int(last_time.timestamp() * 1000) + 1
            if next_ms <= start_ms:
                raise ValueError("historical_pagination_stalled")
            start_ms = next_ms
        return all_rows


def normalize_candles(raw: list[dict[str, Any]]) -> list[Candle]:
    candles: list[Candle] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("candle_not_object")
        timestamp = _item_timestamp(item)
        try:
            values = {name: float(item[name]) for name in ("open", "high", "low", "close", "volume")}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("candle_numeric_field_missing") from exc
        if not (values["low"] <= values["open"] <= values["high"] and values["low"] <= values["close"] <= values["high"]):
            raise ValueError("candle_ohlc_invalid")
        candles.append(Candle(timestamp.isoformat(), **values))
    candles.sort(key=lambda candle: candle.timestamp_utc)
    for previous, current in zip(candles, candles[1:]):
        if current.timestamp_utc <= previous.timestamp_utc:
            raise ValueError("candle_timestamps_not_strictly_increasing")
    return candles


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
    ids = client.resolve_instruments()
    manifests: list[DatasetManifest] = []
    out = Path(output_dir)
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            if progress:
                progress(f"downloading {instrument} {timeframe}")
            raw = client.historical_prices(
                instrument_id=ids[instrument],
                timeframe=timeframe,
                start_utc=start_utc,
                end_utc=end_utc,
            )
            candles = normalize_candles(raw)
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
            ))
    save_manifest(manifests, out / "manifest.json")
    return manifests
