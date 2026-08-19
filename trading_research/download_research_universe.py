"""CLI for one-shot acquisition of the frozen broader research universe."""

from __future__ import annotations

import argparse

from .dukascopy_history import DukascopyClient, download_universe

DEFAULT_START = "2010-01-01T00:00:00+00:00"
DEFAULT_END = "2025-12-31T23:59:59+00:00"
DEFAULT_OUTPUT = "data/research/universe_v2"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and verify Nova's frozen trading research universe.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    args = parser.parse_args()
    client = DukascopyClient()

    def progress(message: str) -> None:
        print(message, flush=True)

    manifests = download_universe(
        output_dir=args.output,
        start_utc=args.start,
        end_utc=args.end,
        client=client,
        progress=progress,
    )
    print(f"verified_datasets={len(manifests)}", flush=True)
    print(f"manifest={args.output}/manifest.json", flush=True)


if __name__ == "__main__":
    main()
